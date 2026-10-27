# -*- coding: utf-8 -*-
"""把整个项目打包上传到坚果云（不含密码、缓存、旧备份）。

用法：
    python tools/backup_project.py            # 打包并上传
    python tools/backup_project.py --dry-run  # 只打包看大小
"""
import argparse
import io
import json
import lzma
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXCLUDE_DIRS = {"backups", "__pycache__", ".git", "exports", "cache", "logs"}
EXCLUDE_FILES = {"cloud.secret", "cloud_sync.json", "cloud_sync.log",
                 "snapshot.sha256", ".lock"}
PRESET = 9 | getattr(lzma, "PRESET_EXTREME", 0)


def build_archive(project: Path):
    from core.cloudpack import pack_project
    return pack_project(project)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remote", default="quiz_py_backup")
    args = ap.parse_args()

    packed, plain, count = build_archive(ROOT)
    print(f"文件 {count} 个，原始 {plain/1024/1024:.2f} MB → 压缩 {len(packed)/1024/1024:.2f} MB")
    if args.dry_run:
        return

    from core.paths import CLOUD_CONFIG, SECRET_FILE
    from core.secret import load_password
    from core.webdav import WebDAVClient

    cfg = json.loads(CLOUD_CONFIG.read_text(encoding="utf-8"))
    client = WebDAVClient(cfg["url"], cfg["user"], load_password(SECRET_FILE), timeout=60)
    client.ensure_dir(args.remote)
    name = f"project_{time.strftime('%Y%m%d_%H%M%S')}.tar.xz"
    target = f"{args.remote}/{name}"
    print("上传:", target)
    client.put(target, packed)
    print("完成。远端现有：")
    for e in client.list_dir(args.remote):
        print(f"  {e['name']}  {e['size']/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
