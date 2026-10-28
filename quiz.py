# quiz.py
import os
import sys
import json
import random
import pickle
import hashlib
import logging
import traceback
import time
import signal
import re
import shutil
import textwrap
import zipfile
import csv
import tempfile
from datetime import datetime
from pathlib import Path

from core.ui import (ask,
    ExitHandler, KeyReader, bold, clear_screen, cyan, dim, green,
    paint, progress_bar, red, yellow, USE_COLOR,
)
from quiz_parser.quiz_parser import QuizImportParser
from quiz_parser.models import Question, QuestionType, Option
from quiz_parser.validator import dedupe_questions, validate

# ================= 路径与目录配置 =================
# 控制台编码不可写 emoji 时不要崩：保留编码，坏字符降级为 ?
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

from views.practice import PracticeMixin
from views.exam import ExamMixin
from views.banks import BanksMixin
from views.backup import BackupMixin
from views.records import RecordsMixin
from views.dashboard import DashboardMixin
from core.menu import MenuRegistry
from core.state import StateMixin
APP_VERSION = "0.12.1"



def _check_portable_root():
    """记录项目上次所在路径；换盘/搬家时提示（不阻止启动）。"""
    from core.paths import BASE_DIR
    marker = BASE_DIR / ".portable-root"
    current = str(BASE_DIR.resolve())
    try:
        if marker.exists():
            previous = marker.read_text(encoding="utf-8").strip()
            if previous and previous.lower() != current.lower():
                print(f"ℹ️ 项目位置变化：{previous} → {current}")
                if Path(previous).exists():
                    print("   旧位置仍存在，可能是复制出来的副本，注意别改错目录。")
        marker.write_text(current, encoding="utf-8")
    except Exception:
        pass


def _portable_selfcheck():
    """启动自检：密码档位、配置路径、题库 key、缓存体积，写 logs/selfcheck.log。"""
    from core.paths import BASE_DIR, CACHE_DIR, DATA_DIR, SECRET_FILE
    from core import config
    lines = []
    try:
        cfg = config.load()
        url = (cfg.get("cloud") or {}).get("url") or ""
        if url and "://" not in url:
            lines.append("配置异常：cloud.url 不是合法 URL")
        secret = SECRET_FILE
        if secret.exists():
            mode = secret.read_text(encoding="utf-8").strip()[:6]
            lines.append(f"密码保存方式：{'DPAPI 加密' if mode.startswith('dpapi') else '明文（便携档）'}")
        state = DATA_DIR / "state.json"
        if state.exists():
            import json
            data = json.loads(state.read_text(encoding="utf-8"))
            abs_keys = [k for k in (data.get("banks") or {}) if ":" in k or k.startswith("\\")]
            if abs_keys:
                lines.append(f"题库 key 含绝对路径：{len(abs_keys)} 个（会被迁移）")
        if CACHE_DIR.exists():
            size = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
            if size > 20 * 1024 * 1024:
                lines.append(f"解析缓存偏大：{size / 1024 / 1024:.1f} MB（可删 cache 目录重建）")
    except Exception as exc:
        lines.append(f"自检异常：{exc}")
    if not lines:
        lines.append("未发现问题")
    try:
        logs = DATA_DIR / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with open(logs / "selfcheck.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n")
            for line in lines:
                fh.write(f"  - {line}\n")
    except Exception:
        pass
    return lines


def _cleanup_tmp():
    """清理 quiz_parser.data/tmp 下超过 1 小时的残留文件。"""
    import time
    from core.paths import DATA_DIR
    tmp = DATA_DIR / "tmp"
    if not tmp.exists():
        return
    cutoff = time.time() - 3600
    for f in tmp.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass


def install_crash_hook():
    """未捕获异常写入 logs/crash.log（1MB 轮转，最多 5 份）。"""
    import sys as _sys
    import traceback
    from core.paths import DATA_DIR

    def hook(exc_type, exc, tb):
        logs = DATA_DIR / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
            target = logs / "crash.log"
            if target.exists() and target.stat().st_size > 1024 * 1024:
                for i in range(4, 0, -1):
                    src = logs / (f"crash.{i}.log")
                    if src.exists():
                        src.replace(logs / f"crash.{i + 1}.log")
                target.replace(logs / "crash.1.log")
            with open(target, "a", encoding="utf-8") as fh:
                fh.write("\n===== crash =====\n")
                traceback.print_exception(exc_type, exc, tb, file=fh)
        except Exception:
            pass
        _sys.__excepthook__(exc_type, exc, tb)

    _sys.excepthook = hook


from core.paths import (
    bank_rel_key, bank_abs_path, normalize_bank_key,
    BASE_DIR, DATA_DIR, CACHE_DIR, LOG_DIR, BANKS_DIR,
    STATE_FILE, HISTORY_FILE, STATE_VERSION, CLOUD_CONFIG, BANK_COUNTS_FILE,
)


# ========== 便携化：库里一律存「相对 BASE_DIR 的路径」 ==========











# ==================================================

log_filename = LOG_DIR / f"quiz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logger = logging.getLogger("ShirohaQuiz")
logger.setLevel(logging.DEBUG)
if logger.hasHandlers():
    logger.handlers.clear()
file_handler = logging.FileHandler(log_filename, mode='w', encoding="utf-8", delay=False)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(console_handler)


# ========== 终端表现 ==========


















exit_handler = ExitHandler()



class ShirohaQuiz(PracticeMixin, ExamMixin, BanksMixin, RecordsMixin, DashboardMixin, BackupMixin, StateMixin):
    def __init__(self):
        self.questions = []
        self.wrong_book = []
        self.wrong_counts = {}
        self.wrong_status = {}
        self.wrong_last = {}
        self.right_counts = {}
        self.srs = {}
        self.srs_day = {}
        self.srs_log = []
        self.prefs = {"global": {}, "banks": {}}
        self.favorites = []
        self.current_idx = 0
        self.bank_name = ""
        self.bank_path = ""
        self.bank_key = ""
        self.banks_state = {}
        self.auto_next = True
        self.load_state()
        self._fix_progress()

    # ---------------- 状态 ----------------







    # ---------------- 导入 ----------------






    SAMPLE_TEXT = """1. 计算机的核心部件是()。
A. 内存
B. CPU
C. 硬盘
D. 显示器
答案：B

2. 下列属于输入设备的是()。
A. 打印机
B. 显示器
C. 键盘
D. 音箱
答案：C

3. 判断题：Python 是解释型语言。
答案：正确
"""



    DUAL_QUESTIONS = """1. 计算机的核心部件是（）
A. 内存
B. CPU
C. 硬盘
D. 显示器

2. 下列属于输入设备的是（）
A. 打印机
B. 显示器
C. 键盘
D. 音箱

3. 判断题：Python 是解释型语言。
"""

    DUAL_ANSWERS = """1.B
2.C
3.正确
"""



    # ---------------- 答题界面 ----------------










    # ---------------- 练习 ----------------


    # ---------------- 题目浏览 / 编辑 ----------------



    # ---------------- 题库管理 ----------------


    # ---------------- 备份 ----------------
    # ---------------- 云端同步（预留） ----------------




    # ---------------- 历史与搜索 ----------------



    # ---------------- 判分 ----------------
    def check_answer(self, q, user_ans):
        if not q.answer:
            return False
        if q.type in (QuestionType.SHORT, QuestionType.BLANK):
            def clean_text(t):
                return re.sub(r'[\s\u3000（）()【】\[\]{}。？?！!，,、：:；;\.\*]', '', str(t)).lower()
            user_clean = clean_text(user_ans)
            if not user_clean:
                return False
            for ans in q.answer:
                ans_clean = clean_text(ans)
                if ans_clean == user_clean or (q.type == QuestionType.BLANK and len(ans_clean) > 1 and ans_clean in user_clean):
                    return True
            return False
        user_list = list(user_ans.replace(",", "").replace(" ", "").replace("，", "").upper())
        if q.type == QuestionType.JUDGE:
            if user_ans in ("A", "T", "TRUE", "正确", "对", "1", "是", "√"):
                user_list = ["正确"]
            elif user_ans in ("B", "F", "FALSE", "错误", "错", "0", "否", "×"):
                user_list = ["错误"]
        return sorted(user_list) == sorted(q.answer)

    # ---------------- 主菜单 ----------------

    # ---------------- 统计总览 ----------------



    def _build_menu(self):
        menu = MenuRegistry()
        menu.add("1", "导入题库", self.load_bank)
        menu.add("2", "自定义练习", self.practice_settings)
        menu.add("3", "模拟考试", self.start_exam)
        menu.add("4", "错题回顾", self.review_wrong)
        menu.add("5", "收藏回顾", self.review_favorites)
        menu.add("6", "题库管理", self.manage_banks)
        menu.add("7", "历史战绩", self.show_history)
        menu.add("8", "备份与恢复", self.backup_data)
        menu.add("9", "搜索题目", self.search_questions)
        menu.add("10", "统计总览", self.show_dashboard)
        menu.add("11", "间隔复习", self.review_due)
        menu.add("12", "复习管理", self.srs_manage)
        menu.add("s", "保存数据", self._menu_save)
        menu.add("0", "退出", self._menu_quit)
        try:
            from plugins import load_plugins
            loaded, failed = load_plugins(self, menu)
            if loaded:
                self.plugins_loaded = loaded
        except Exception as exc:
            print(f"[plugin] 插件系统不可用：{exc}")
        return menu

    def _menu_save(self):
        self.save_state()
        cfg = {}
        try:
            cfg = self._auto_cfg()
        except Exception:
            pass
        if cfg.get("url") and cfg.get("save_sync", False):
            print(green("✅ 已保存，正在同步云端..."))
            try:
                self._auto_sync("手动保存", force=True)
            except Exception:
                pass
        else:
            print(green("✅ 已保存（错题/收藏/进度/记录都在 quiz_parser.data）"))
        ask()

    def _menu_quit(self):
        try:
            self._auto_sync("退出")
        except Exception:
            pass
        if self._confirm("确定退出？"):
            self.save_state()
            print("再见！")
            sys.exit(0)

    def run(self):
        install_crash_hook()
        _cleanup_tmp()
        _check_portable_root()
        _portable_selfcheck()
        try:
            self._auto_pull()
        except Exception:
            pass
        self.menu = self._build_menu()
        while True:
            clear_screen()
            print("=" * 46)
            print(f"           🌸 Shiroha Quiz 终端版 v{APP_VERSION}")
            print("=" * 46)
            status = f"{self.bank_name} ({len(self.questions)}题)" if self.questions else "未加载"
            print(f"📦 {status}")
            if self.questions:
                pos = f"{min(self.current_idx + 1, len(self.questions))}/{len(self.questions)}"
            else:
                pos = "—"
            print(f"❌ 错题:{len(self.wrong_book)}   ⭐ 收藏:{len(self.favorites)}   📍 进度:{pos}")
            try:
                from core.cloudpack import seven_zip_path
                _exe = seven_zip_path()
                if _exe:
                    print(dim(f"🗜️  7-Zip: 可用（{Path(_exe).name}）"))
                else:
                    print(dim("🗜️  7-Zip: 未找到（压缩/解压走标准库 xz）"))
            except Exception:
                pass
            print("-" * 46)
            print(self.menu.render())
            print("=" * 46)

            try:
                choice = input("请选择功能 > ").strip()
            except (EOFError, KeyboardInterrupt):
                self.save_state()
                sys.exit(0)

            if not choice:
                continue
            handler = self.menu.handler(choice)
            if handler is None:
                continue
            try:
                handler()
            except SystemExit:
                raise


def _cli():
    """最小命令行：--dump-json 给 GUI/脚本取数，--version 打印版本。"""
    import sys as _sys

    args = _sys.argv[1:]
    if "--version" in args:
        print(APP_VERSION)
        return True
    if "--web" in args:
        from gui.server import serve
        port = 0
        if "--port" in args:
            try:
                port = int(args[args.index("--port") + 1])
            except (ValueError, IndexError):
                port = 0
        # 局域网访问：--lan 等价于 --host 0.0.0.0；显式 --host 优先于 --lan
        host = "0.0.0.0" if "--lan" in args else ("127.0.0.1" if "--local" in args else "")
        if "--host" in args:
            _i = args.index("--host")
            if _i + 1 < len(args) and not args[_i + 1].startswith("--"):
                host = args[_i + 1]
        # 可选访问口令：不传 = 不校验（默认行为不变）
        token = ""
        if "--token" in args:
            _i = args.index("--token")
            if _i + 1 < len(args) and not args[_i + 1].startswith("--"):
                token = args[_i + 1]
        serve(port=port, host=host, open_browser="--no-browser" not in args, token=token)
        return True
    if "--dump-json" in args:
        import json as _json
        from services.banks import dump
        print(_json.dumps(dump(), ensure_ascii=False, indent=2))
        return True
    return False


if __name__ == "__main__":
    if _cli():
        raise SystemExit(0)
    app = ShirohaQuiz()
    exit_handler.app = app
    signal.signal(signal.SIGINT, exit_handler.signal_handler)
    app.run()
