# -*- coding: utf-8 -*-
"""备份 / 恢复 / 清除数据 / 云端入口（占位）。"""
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from core.paths import (
    BANKS_DIR, BASE_DIR, CACHE_DIR, CLOUD_CONFIG, DATA_DIR, HISTORY_FILE, STATE_FILE,
    SECRET_FILE, SYNC_CACHE_FILE,
)
from core.ui import ask, clear_screen, cyan, dim, green, red, yellow


def _load_cloud_config():
    """读取可选的 cloud.json；不存在或坏掉都返回 None，不影响主流程。"""
    if not CLOUD_CONFIG.exists():
        return None
    try:
        return json.loads(CLOUD_CONFIG.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


class BackupMixin:
    """备份与数据清理相关方法。"""

    # ---------------- 云端同步（WebDAV） ----------------
    def _cloud_cfg(self):
        from core.config import cloud as cloud_cfg
        c = cloud_cfg()
        url = str(c.get("url") or "").strip()
        user = str(c.get("user") or "").strip()
        remote = str(c.get("remote_dir") or "quiz_py").strip("/")
        return url, user, remote

    def _cloud_password(self, user):
        import getpass
        from core.secret import load_password
        from core.secret import secret_status
        status = secret_status(SECRET_FILE)
        if status == "dpapi-locked":
            print(dim("⚠️ 已保存的密码绑定在另一台设备/账户上（DPAPI），本机需要重新输入。"))
        saved = load_password(SECRET_FILE)
        if saved:
            return saved
        if not user:
            return ""
        try:
            return getpass.getpass(f"{user} 的密码（回车=不保存）: ")
        except Exception:
            return ""

    def _cloud_password_setup(self):
        import getpass
        from core.secret import save_password, clear_password, secret_status
        clear_screen()
        print("=" * 46)
        print("            ☁️  WebDAV 密码")
        print("=" * 46)
        status = secret_status(SECRET_FILE)
        label = {
            "dpapi": "已保存（加密，仅本机可用）",
            "plain": "已保存（明文，换设备可用）",
            "dpapi-locked": "已保存但本机解不开（来自其它设备），请重新设置",
            "missing": "未保存",
        }.get(status, status)
        print("当前：" + label)
        print("1. 加密保存（仅本机，换设备要重输）")
        print("2. 明文保存（便携，换设备直接可用）")
        print("3. 清除密码")
        print("0. 返回")
        c = ask("请选择: ").strip()
        if c == "3":
            clear_password(SECRET_FILE)
            print(green("✅ 已清除"))
            ask()
            return
        if c not in ("1", "2"):
            return
        try:
            pwd = getpass.getpass("密码: ")
        except Exception:
            pwd = ""
        if not pwd:
            return
        mode = save_password(SECRET_FILE, pwd, mode=("dpapi" if c == "1" else "plain"))
        if mode == "dpapi":
            print(green("✅ 已加密保存（仅本机可用）"))
        else:
            print(green("✅ 已明文保存（便携，换设备可直接用）"))
        ask()

    def _cloud_client(self):
        from core.webdav import WebDAVClient, WebDAVError
        url, user, remote = self._cloud_cfg()
        if not url:
            print("⚠️ 还没有配置 WebDAV 地址，先选 [4] 配置")
            ask()
            return None
        return WebDAVClient(url, user, self._cloud_password(user)), remote

    def _cloud_pack(self):
        """打包并极限压缩（tar.xz），返回 (字节, 原始大小)。"""
        from core.cloudpack import pack_backup
        from core.config import cloud as cloud_cfg
        level = cloud_cfg().get("compression", "standard")
        return pack_backup(BANKS_DIR, STATE_FILE, HISTORY_FILE, level=level)

    def _cloud_upload(self):
        client_info = self._cloud_client()
        if not client_info:
            return
        client, remote = client_info
        from core.webdav import WebDAVError
        try:
            raw, plain = self._cloud_pack()
            from core.cloudpack import suffix_for
            import hashlib as _hash
            h = _hash.sha256(raw).hexdigest()
            side = DATA_DIR / "snapshot.sha256"
            if side.exists() and side.read_text(encoding="utf-8").strip() == h:
                print(dim("内容与上次快照一致，跳过上传（省流量）"))
                ask()
                return
            name = f"quiz_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix_for(raw)}"
            client.ensure_dir(remote)
            remote_path = f"{remote}/{name}" if remote else name
            ratio = (1 - len(raw) / plain) * 100 if plain else 0
            print(f"原始 {plain/1024:.0f} KB → 压缩 {len(raw)/1024:.0f} KB（省 {ratio:.0f}%）")
            print(f"正在上传 {name} ...")
            client.put(remote_path, raw)
            try:
                side.write_text(h, encoding="utf-8")
            except Exception:
                pass
            print(green(f"✅ 已上传：{remote_path}"))
        except WebDAVError as exc:
            print(red(f"❌ 上传失败：{exc}"))
        ask()

    def _cloud_list(self):
        client_info = self._cloud_client()
        if not client_info:
            return
        client, remote = client_info
        from core.webdav import WebDAVError
        try:
            from core.cloudpack import is_backup_name
            entries = [e for e in client.list_dir(remote) if not e["is_dir"] and is_backup_name(e["name"])]
        except WebDAVError as exc:
            print(red(f"❌ 列表失败：{exc}"))
            ask()
            return
        clear_screen()
        print("=" * 46)
        print(f"            ☁️  远端文件（{remote or '/'}）")
        print("=" * 46)
        if not entries:
            print("  （空）")
        for i, e in enumerate(entries, 1):
            print(f"  [{i}] {e['name']}   {e['size']/1024:.1f} KB")
        ask("按回车返回...")

    def _cloud_download(self):
        client_info = self._cloud_client()
        if not client_info:
            return
        client, remote = client_info
        from core.webdav import WebDAVError
        try:
            from core.cloudpack import is_backup_name
            entries = sorted([e for e in client.list_dir(remote) if is_backup_name(e["name"])],
                             key=lambda e: e["name"], reverse=True)
        except WebDAVError as exc:
            print(red(f"❌ 列表失败：{exc}"))
            ask()
            return
        if not entries:
            print("远端没有 zip 备份")
            ask()
            return
        for i, e in enumerate(entries[:15], 1):
            print(f"  [{i}] {e['name']}   {e['size']/1024:.1f} KB")
        idx = ask("下载哪个 (0=返回): ").strip()
        if not idx.isdigit() or not (1 <= int(idx) <= min(15, len(entries))):
            return
        entry = entries[int(idx) - 1]
        path = f"{remote}/{entry['name']}" if remote else entry["name"]
        try:
            print("正在下载...")
            data = client.get(path)
        except WebDAVError as exc:
            print(red(f"❌ 下载失败：{exc}"))
            ask()
            return
        out_dir = BASE_DIR / "backups" / "remote"
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / entry["name"]
        target.write_bytes(data)
        print(green(f"✅ 已保存：{target}"))
        if self._confirm("现在就恢复这个备份？"):
            try:
                from core.cloudpack import unpack_backup
                files = unpack_backup(target.read_bytes())
                restored = 0
                for name, content in files.items():
                    if name.startswith("banks/"):
                        (BANKS_DIR / Path(name).name).write_bytes(content)
                        restored += 1
                for name, content in files.items():
                    if name.endswith("quiz_parser.data/state.json"):
                        STATE_FILE.write_bytes(content)
                print(green(f"✅ 已恢复 {restored} 个题库（状态已覆盖）"))
            except Exception as exc:
                print(red(f"❌ 恢复失败：{exc}"))
        ask()

    def _cloud_config(self):
        url, user, remote = self._cloud_cfg()
        clear_screen()
        print("=" * 46)
        print("            ☁️  WebDAV 配置")
        print("=" * 46)
        print(f"地址：{url or '(未填)'}")
        print(f"账号：{user or '(未填)'}")
        print(f"远程目录：{remote or '(根)'}")
        print("密码：保存在 config/cloud.secret（菜单 9 设置）")
        if self._confirm("要修改配置吗？"):
            new_url = ask(f"地址 (回车={url or '空'}): ").strip() or url
            new_user = ask(f"账号 (回车={user or '空'}): ").strip() or user
            new_remote = ask(f"远程目录 (回车={remote or 'quiz_py'}): ").strip() or remote
            try:
                from core import config as app_config
                cfg = app_config.load()
                cfg["cloud"].update({"url": new_url, "user": new_user,
                                     "remote_dir": new_remote})
                path = app_config.save(cfg)
                print(green(f"✅ 已保存到 {path.name}"))
            except Exception as exc:
                print(red(f"❌ 保存失败：{exc}"))
        ask()

    # ---------------- 自动同步 ----------------
    def _auto_cfg(self):
        from core.config import cloud as cloud_cfg
        c = cloud_cfg()
        return {
            "url": str(c.get("url") or "").strip(),
            "user": str(c.get("user") or "").strip(),
            "remote": str(c.get("remote_dir") or "quiz_py").strip("/"),
            "auto_sync": bool(c.get("auto_sync", False)),
            "auto_pull": bool(c.get("auto_pull", False)),
            "save_sync": bool(c.get("save_sync", False)),
            "ignore": list(c.get("ignore") or []),
            "sync_deletes": bool(c.get("sync_deletes", False)),
        }

    def _auto_data_sync(self, reason=""):
        """保存后立即把答题数据传到云端（数据包只有几 KB，20 秒内最多一次）。"""
        import time as _time
        now = _time.time()
        if now - getattr(self, "_auto_data_at", 0.0) < 20:
            return
        cfg = self._auto_cfg()
        if not cfg["url"] or not cfg["auto_sync"]:
            return
        from core.secret import load_password
        pw = load_password(SECRET_FILE)
        if cfg["user"] and not pw:
            return
        self._auto_data_at = now
        try:
            from core import cloudsync
            from core.webdav import WebDAVClient
            client = WebDAVClient(cfg["url"], cfg["user"], pw)
            cloudsync.push_data(client, cfg["remote"], STATE_FILE, HISTORY_FILE,
                                log_path=DATA_DIR / "cloud_sync.log")
        except Exception:
            pass            # 自动模式永远不打断答题

    def _auto_sync(self, reason="", force=False):
        """静默增量上传：只在配置了地址且开启自动同步时执行。"""
        cfg = self._auto_cfg()
        if not cfg["url"] or not cfg["auto_sync"]:
            return
        from core.secret import load_password
        pwd = load_password(SECRET_FILE)
        if cfg["user"] and not pwd:
            return                      # 自动模式不弹密码
        try:
            from core import cloudsync
            from core.webdav import WebDAVClient
            client = WebDAVClient(cfg["url"], cfg["user"], pwd)
            local = cloudsync.collect_local(BANKS_DIR, STATE_FILE, HISTORY_FILE,
                                            ignore=cfg.get("ignore"))
            import threading
            box = {}

            def _run():
                try:
                    box["stats"] = cloudsync.push(
                        client, cfg["remote"], local,
                        cache_path=SYNC_CACHE_FILE,
                        log_path=DATA_DIR / "cloud_sync.log",
                        force=bool(force or reason == "退出"), min_interval=600)
                except Exception as exc:  # 后台线程不抛出
                    box["error"] = exc

            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(5)
            if worker.is_alive():
                print(dim("☁️  同步超时（5s），已跳过；可稍后手动同步"))
                return
            if "error" in box:
                return
            stats = box.get("stats") or {}
            if stats["uploaded"]:
                tag = f"（{reason}）" if reason else ""
                print(dim(f"☁️  自动同步{tag}：上传 {stats['uploaded']} 个文件，{stats['sent']/1024:.1f} KB"))
        except Exception:
            pass                        # 网络问题不打扰使用

    def _cloud_log(self):
        clear_screen()
        print("=" * 46)
        print("            ☁️  同步日志")
        print("=" * 46)
        log = DATA_DIR / "cloud_sync.log"
        if not log.exists():
            print("  （还没有同步记录）")
        else:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            for line in lines:
                print("  " + line)
        ask("按回车返回...")

    def _auto_settings(self):
        cfg = self._auto_cfg()
        clear_screen()
        print("=" * 46)
        print("            ☁️  自动同步设置")
        print("=" * 46)
        print(f"1. 自动上传：{'开启' if cfg['auto_sync'] else '关闭'}")
        print(f"2. 启动时自动拉取：{'开启' if cfg['auto_pull'] else '关闭'}")
        print(f"3. 保存后自动上传：{'开启' if cfg['save_sync'] else '关闭（默认）'}")
        from core import config as _app_config
        _color = _app_config.ui().get("color")
        print(f"4. 彩色输出：{'开启' if _color is not False else '关闭'}")
        _level = _app_config.cloud().get("compression", "standard")
        print(f"5. 压缩档位：{_level}（fast / standard / extreme）")
        print("0. 返回")
        c = ask("请选择: ").strip()
        if c == "4":
            full = _app_config.load()
            current = full["ui"].get("color")
            full["ui"]["color"] = False if current is not False else True
            try:
                _app_config.save(full)
                print(green("✅ 已保存（重启或重进界面生效）"))
            except Exception as exc:
                print(red(f"❌ 保存失败：{exc}"))
            ask()
            return
        if c == "5":
            order = ["fast", "standard", "extreme"]
            full = _app_config.load()
            current = full["cloud"].get("compression", "standard")
            nxt = order[(order.index(current) + 1) % len(order)] if current in order else "standard"
            full["cloud"]["compression"] = nxt
            try:
                _app_config.save(full)
                print(green(f"✅ 压缩档位：{nxt}"))
            except Exception as exc:
                print(red(f"❌ 保存失败：{exc}"))
            ask()
            return
        if c in ("1", "2", "3"):
            from core import config as app_config
            key = {"1": "auto_sync", "2": "auto_pull", "3": "save_sync"}[c]
            full = app_config.load()
            full["cloud"][key] = not bool(full["cloud"].get(key, False))
            try:
                app_config.save(full)
                print(green("✅ 已保存"))
            except Exception as exc:
                print(red(f"❌ 保存失败：{exc}"))
            ask()

    def _auto_pull(self):
        """启动时静默拉取远端更新（需在配置里开启）。"""
        cfg = self._auto_cfg()
        if not cfg["url"] or not cfg["auto_pull"]:
            return
        from core.secret import load_password
        pwd = load_password(SECRET_FILE)
        if cfg["user"] and not pwd:
            return
        try:
            from core import cloudsync
            from core.webdav import WebDAVClient
            client = WebDAVClient(cfg["url"], cfg["user"], pwd)
            stats = cloudsync.pull(client, cfg["remote"], BANKS_DIR, STATE_FILE, HISTORY_FILE,
                               cache_path=SYNC_CACHE_FILE,
                               log_path=DATA_DIR / "cloud_sync.log")
            if stats["downloaded"]:
                self.load_state()
                if self.bank_path:
                    self._parse_bank(bank_abs_path(self.bank_path), silent=True)
                print(dim(f"☁️  已从云端拉取 {stats['downloaded']} 个文件（{stats['got']/1024:.1f} KB）"))
        except Exception:
            pass

    def _cloud_push(self):
        info = self._cloud_client()
        if not info:
            return
        client, remote = info
        from core import cloudsync
        from core.webdav import WebDAVError
        local = cloudsync.collect_local(BANKS_DIR, STATE_FILE, HISTORY_FILE,
                                        ignore=self._auto_cfg().get("ignore"))
        try:
            stats = cloudsync.push(client, remote, local,
                               cache_path=SYNC_CACHE_FILE,
                               log_path=DATA_DIR / "cloud_sync.log", force=True)
        except WebDAVError as exc:
            print(red(f"❌ 同步失败：{exc}"))
            ask()
            return
        print(green(f"✅ 已上传 {stats['uploaded']} 个文件，跳过 {stats['skipped']} 个未变化"))
        print(f"流量：发送 {stats['sent']/1024:.1f} KB（原始 {stats['plain']/1024:.1f} KB）")
        ask()

    def _cloud_pull(self):
        info = self._cloud_client()
        if not info:
            return
        client, remote = info
        from core import cloudsync
        from core.webdav import WebDAVError
        try:
            stats = cloudsync.pull(client, remote, BANKS_DIR, STATE_FILE, HISTORY_FILE,
                               cache_path=SYNC_CACHE_FILE,
                               log_path=DATA_DIR / "cloud_sync.log")
        except WebDAVError as exc:
            print(red(f"❌ 拉取失败：{exc}"))
            ask()
            return
        print(green(f"✅ 已下载 {stats['downloaded']} 个文件，跳过 {stats['skipped']} 个相同"))
        print(f"流量：接收 {stats['got']/1024:.1f} KB（原始 {stats['plain']/1024:.1f} KB）")
        self.load_state()
        print("状态已重新加载，建议重新进入题库以刷新题目。")
        ask()

    def _cloud_purge(self):
        """删除远端所有备份文件（保留目录），需要输入 DELETE 确认。"""
        info = self._cloud_client()
        if not info:
            return
        client, remote = info
        clear_screen()
        print("=" * 46)
        print("            ☁️  清除远端数据")
        print("=" * 46)
        print(f"将删除 {remote or '/'} 下的所有备份文件（题库、状态、快照）")
        print("目录会保留，此操作不可恢复！")
        if not self._confirm("清除远端全部备份？此操作不可恢复 (y/N)"):
            print("已取消")
            ask()
            return
        if ask("再次确认：直接回车执行，其它任意键取消 > ").strip() != "":
            print("已取消")
            ask()
            return

        def wipe(path, depth=0):
            removed = 0
            if depth > 4:
                return removed
            try:
                entries = client.list_dir(path)
            except Exception:
                return removed
            for e in entries:
                sub = f"{path}/{e['name']}" if path else e["name"]
                if e["is_dir"]:
                    removed += wipe(sub, depth + 1)
                else:
                    try:
                        client.delete(sub)
                        removed += 1
                    except Exception:
                        pass
            return removed

        try:
            from core.cloudpack import is_backup_name
            n = wipe(remote)
            print(green(f"✅ 已删除 {n} 个远端文件"))
            self._reset_sync_cache()
        except Exception as exc:
            print(red(f"❌ 清除失败：{exc}"))
        ask()

    def _reset_sync_cache(self):
        try:
            from core.paths import DATA_DIR, SYNC_CACHE_FILE
            for p in (SYNC_CACHE_FILE, DATA_DIR / "snapshot.sha256"):
                if p.exists():
                    p.unlink()
        except Exception:
            pass

    def _backup_project_cloud(self):
        """把整个项目打包上传到远端 quiz_py_backup/。"""
        info = self._cloud_client()
        if not info:
            return
        client, _remote = info
        from core.cloudpack import pack_project
        from core.config import cloud as cloud_cfg
        print("正在打包项目（排除缓存与密码）...")
        try:
            packed, plain, count = pack_project(BASE_DIR, level="extreme")
        except Exception as exc:
            print(red(f"❌ 打包失败：{exc}"))
            ask()
            return
        print(f"文件 {count} 个：{plain/1024/1024:.2f} MB → {len(packed)/1024/1024:.2f} MB")
        if not self._confirm("上传项目备份到云端？"):
            print("已取消")
            ask()
            return
        from core.cloudpack import suffix_for
        name = f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix_for(packed)}"
        target = f"quiz_py_backup/{name}"
        try:
            client.ensure_dir("quiz_py_backup")
            client.put(target, packed)
            print(green(f"✅ 已上传：{target}"))
        except Exception as exc:
            print(red(f"❌ 上传失败：{exc}"))
        ask()

    def _cloud_placeholder(self):
        """云端同步菜单（WebDAV）。"""
        while True:
            url, user, remote = self._cloud_cfg()
            clear_screen()
            print("=" * 46)
            print("            ☁️  云端同步（WebDAV）")
            print("=" * 46)
            print(f"状态：{'已配置' if url else '未配置'}   {url or ''}")
            print(f"目录：{remote or '(根)'}   凭据：cloud.secret")
            print("-" * 46)
            print("1. 上传快照（tar.xz）     2. 查看远端列表")
            print("3. 下载快照并恢复         4. 增量同步 → 云端")
            print("5. 增量同步 ← 云端       6. 修改配置")
            print("7. 自动同步设置           8. 同步日志")
            print("9. 设置密码（加密/明文） 10. 清除远端数据")
            print("0. 返回")
            print(dim("提示：答题结束与退出程序时会自动增量上传（可在 7 里关闭）"))
            try:
                import json as _json
                _cache = _json.loads(SYNC_CACHE_FILE.read_text(encoding="utf-8"))
                if _cache.get("last_sync"):
                    _when = datetime.fromtimestamp(_cache["last_sync"]).strftime("%m-%d %H:%M")
                    print(dim(f"上次同步：{_when} · 已跟踪 {len(_cache.get('files') or {})} 个文件"))
            except Exception:
                pass
            c = ask("请选择: ").strip()
            if c == "1":
                self._cloud_upload()
            elif c == "2":
                self._cloud_list()
            elif c == "3":
                self._cloud_download()
            elif c == "4":
                self._cloud_push()
            elif c == "5":
                self._cloud_pull()
            elif c == "6":
                self._cloud_config()
            elif c == "7":
                self._auto_settings()
            elif c == "8":
                self._cloud_log()
            elif c == "9":
                self._cloud_password_setup()
            elif c == "10":
                self._cloud_purge()
            else:
                return

    def _clear_local_data(self):
        clear_screen()
        print("=" * 46)
        print("            🧹 清除本地数据")
        print("=" * 46)
        print("1. 只清学习数据（错题/收藏/进度/记录），题库保留")
        print("2. 全部清除（题库、缓存、备份、记录一并删除）")
        print("0. 取消")
        scope = ask("请选择: ").strip()
        if scope not in ("1", "2"):
            return
        label = "清除全部数据" if scope == "2" else "清除学习数据"
        if not self._confirm(f"{label}？此操作不可恢复 (y/N)"):
            print("已取消")
            ask()
            return
        if ask("再次确认：直接回车执行，其它任意键取消 > ").strip() != "":
            print("已取消")
            ask()
            return
        removed = []
        if scope == "2":
            for f in BANKS_DIR.glob("*"):
                if f.is_file():
                    f.unlink()
                    removed.append(f.name)
            for f in BASE_DIR.glob("backup_*.zip"):
                f.unlink()
                removed.append(f.name)
            if CACHE_DIR.exists():
                for f in CACHE_DIR.glob("*"):
                    f.unlink()
                removed.append("缓存")
        for path in (STATE_FILE, HISTORY_FILE):
            if path.exists():
                path.unlink()
                removed.append(path.name)
        self.questions = []
        self.bank_key = ""
        self.bank_path = ""
        self.bank_name = ""
        self.wrong_book = []
        self.wrong_counts = {}
        self.favorites = []
        self.banks_state = {}
        self.current_idx = 0
        self.save_state()
        print(green(f"✅ 已清除：{', '.join(removed) or '无'}"))
        ask()

    def backup_data(self):
        while True:
            clear_screen()
            print("=" * 46)
            print("              💾 备份与恢复")
            print("=" * 46)
            print("1. 导出备份 (banks + 状态打包 zip)")
            print("2. 从备份恢复")
            print("3. 云端同步（WebDAV 上传/下载）")
            print("4. 清除本地数据")
            print("5. 备份整个项目到云端")
            print("0. 返回")
            choice = ask("请选择: ").strip()

            if choice == "1":
                name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.make_archive(str(BASE_DIR / name), 'zip', BASE_DIR, 'banks')
                # 状态也带上
                with zipfile.ZipFile(str(BASE_DIR / f"{name}.zip"), 'a') as z:
                    if STATE_FILE.exists():
                        z.write(STATE_FILE, "quiz_parser.data/state.json")
                    if HISTORY_FILE.exists():
                        z.write(HISTORY_FILE, "quiz_parser.data/history.json")
                print(f"✅ 已导出 {name}.zip")
                ask()
            elif choice == "2":
                self._restore_backup()
            elif choice == "3":
                self._cloud_placeholder()
            elif choice == "4":
                self._clear_local_data()
            elif choice == "5":
                self._backup_project_cloud()
            else:
                return

    def _restore_backup(self):
        zips = sorted(BASE_DIR.glob("backup_*.zip"))
        if not zips:
            print("📭 没有找到备份文件"); ask(); return
        for i, z in enumerate(zips, 1):
            print(f"  [{i}] {z.name}")
        idx = ask("选择要恢复的备份 (0=返回): ").strip()
        if not idx.isdigit() or int(idx) == 0 or int(idx) > len(zips):
            return
        archive = zips[int(idx) - 1]

        try:
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                bank_entries = [n for n in names if n.startswith("banks/") and not n.endswith("/")]
                if not bank_entries:
                    print("❌ 该备份里没有 banks/ 内容"); ask(); return

                print("\n备份内的题库：")
                for i, entry in enumerate(bank_entries, 1):
                    print(f"  [{i}] {Path(entry).name}")
                print("  [a] 全部")
                sel = ask("恢复哪个？(a=全部，序号=单个，0=返回): ").strip().lower()
                if sel in ("0", ""):
                    return
                if sel != "a":
                    if not sel.isdigit() or not (1 <= int(sel) <= len(bank_entries)):
                        return
                    bank_entries = [bank_entries[int(sel) - 1]]

                overwrite = ask("同名文件：[1]跳过 [2]覆盖 (默认1): ").strip() or "1"
                # 恢复前先自动备份当前状态
                auto = f"backup_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.make_archive(str(BASE_DIR / auto), 'zip', BASE_DIR, 'banks')
                print(f"（已自动备份当前题库为 {auto}.zip）")

                restored = 0
                skipped = 0
                for entry in bank_entries:
                    target = BANKS_DIR / Path(entry).name
                    if target.exists() and overwrite == "1":
                        skipped += 1
                        continue
                    with z.open(entry) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    restored += 1

                state_entry = next((n for n in names if n.endswith("state.json")), None)
                if state_entry and overwrite == "2" and sel == "a":
                    with z.open(state_entry) as src:
                        data = json.loads(src.read().decode("utf-8"))
                    with open(STATE_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print("（状态文件已一并恢复）")

            print(f"✅ 恢复完成：写入 {restored} 个题库，跳过 {skipped} 个")
            ask()
        except Exception as e:
            print(f"❌ 恢复失败: {e}")
            ask()

def _load_cloud_config():
    """读取可选的 cloud.json；不存在或坏掉都返回 None，不影响主流程。"""
    if not CLOUD_CONFIG.exists():
        return None
    try:
        return json.loads(CLOUD_CONFIG.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
