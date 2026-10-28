# -*- coding: utf-8 -*-
"""清理 `backups/` 下的旧备份，只保留最近 N 份。

删除策略：默认送 Windows 回收站（可还原）；只有大文件才直接删除，避免撑爆回收站。

用法：
    python tools/prune_backups.py                    # 预览（keep=3）
    python tools/prune_backups.py --apply            # 执行：送回收站
    python tools/prune_backups.py --keep 5 --apply
    python tools/prune_backups.py --apply --purge    # 直接永久删除
    python tools/prune_backups.py --apply --big-mb 512
"""
import argparse
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "backups"

FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", ctypes.c_bool),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def recycle(path: Path) -> bool:
    """把文件/目录移到回收站；成功返回 True。"""
    if sys.platform != "win32":
        return False
    try:
        op = SHFILEOPSTRUCTW()
        op.wFunc = 3          # FO_DELETE
        op.pFrom = str(path.resolve()) + "\0"
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    except Exception:
        return False


def dispose(path: Path, big_mb: int = 200, purge: bool = False) -> str:
    """按策略删除：小文件/目录进回收站，大文件直接删。返回动作说明。"""
    if path.is_file() and path.stat().st_size > big_mb * 1024 * 1024:
        path.unlink()
        return "永久删除(大文件)"
    if purge:
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()
        return "永久删除"
    if recycle(path):
        return "已送回收站"
    import shutil
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return "回收站不可用，已直接删除"


def backups():
    if not BACKUP_DIR.is_dir():
        return []
    return sorted((d for d in BACKUP_DIR.iterdir()
                   if d.is_dir() and d.name.startswith("bak-")),
                  key=lambda d: d.name, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=3)
    ap.add_argument("--apply", action="store_true", help="真正执行；不加只预览")
    ap.add_argument("--purge", action="store_true", help="永久删除，不进回收站")
    ap.add_argument("--big-mb", type=int, default=200, help="超过该大小(MB)直接删，不进回收站")
    args = ap.parse_args()

    items = backups()
    print(f"backups/ 共 {len(items)} 份 bak-*，保留 {args.keep} 份")
    for d in items[:args.keep]:
        print(f"  保留 {d.name}")
    for d in items[args.keep:]:
        if not args.apply:
            print(f"  将清理 {d.name}（送回收站）")
            continue
        print(f"  {d.name}: {dispose(d, args.big_mb, args.purge)}")
    if not args.apply and len(items) > args.keep:
        print("加 --apply 执行清理")


if __name__ == "__main__":
    sys.exit(main())
