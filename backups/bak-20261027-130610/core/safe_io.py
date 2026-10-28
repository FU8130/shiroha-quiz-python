# -*- coding: utf-8 -*-
"""原子写入：同目录临时文件 + fsync + os.replace，附带写前标记与恢复。"""
import json
import os
import shutil
import time
from pathlib import Path


def _marker(path: Path) -> Path:
    return path.with_name(path.name + ".writing")


def _backup(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def recover(path: Path) -> bool:
    """上次写入未完成（有 .writing 标记）时，用 .bak 回滚。返回是否发生回滚。"""
    marker = _marker(path)
    if not marker.exists():
        return False
    backup = _backup(path)
    try:
        if backup.exists():
            shutil.copy2(backup, path)
    finally:
        marker.unlink(missing_ok=True)
    return True


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(path)
    marker = _marker(path)
    tmp = path.with_name(path.name + ".tmp")
    if path.exists():
        try:
            shutil.copy2(path, backup)
        except Exception:
            pass
    marker.write_text(str(int(time.time())), encoding="utf-8")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    marker.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload) -> None:
    atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
