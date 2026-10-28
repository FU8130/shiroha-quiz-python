# -*- coding: utf-8 -*-
"""把整个项目打包上传到坚果云（不含密码、缓存、旧备份）。

用法：
    python tools/backup_project.py            # 打包并上传
    python tools/backup_project.py --dry-run  # 只打包看大小

配置读 `config.json` 的 `cloud` 段，密码读 `quiz_parser.data/cloud.secret`
（明文或 DPAPI 均可）；远端目录默认 `quiz_py_backup`。
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remote", default="quiz_py_backup")
    args = ap.parse_args()

    from core.cloudpack import pack_project, suffix_for
    packed, plain, count = pack_project(ROOT, level="extreme")
    print(f"文件 {count} 个，原始 {plain/1024/1024:.2f} MB → 压缩 {len(packed)/1024/1024:.2f} MB")
    if args.dry_run:
        return 0

    from core.config import cloud as cloud_cfg
    from core.paths import SECRET_FILE
    from core.secret import load_password
    from core.webdav import WebDAVClient

    cfg = cloud_cfg()
    url = (cfg.get("url") or "").strip()
    user = (cfg.get("user") or "").strip()
    if not url or not user:
        print("❌ 云端未配置：请先在程序「备份 / 云端同步」里填地址与账号")
        return 2
    password = load_password(SECRET_FILE)
    if not password:
        print("❌ 没有可用的密码：请先在程序里保存 WebDAV 密码")
        return 2

    client = WebDAVClient(url, user, password, timeout=120)
    client.ensure_dir(args.remote)
    name = f"project_{time.strftime('%Y%m%d_%H%M%S')}{suffix_for(packed)}"
    target = f"{args.remote}/{name}"
    print("上传:", target)
    client.put(target, packed)
    print("✅ 完成。远端现有：")
    for e in client.list_dir(args.remote):
        print(f"  {e['name']}  {e['size']/1024/1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
