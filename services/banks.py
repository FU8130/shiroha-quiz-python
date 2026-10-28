# -*- coding: utf-8 -*-
"""给 GUI / HTTP 层用的纯函数：不依赖 TUI、不打印。"""
import json
from pathlib import Path

from core.paths import BANKS_DIR, DATA_DIR, STATE_FILE, BANK_COUNTS_FILE


def _counts():
    try:
        return json.loads(BANK_COUNTS_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def list_banks():
    """题库列表：key（相对路径）、名称、题量（可能为 0 未知）、修改时间、大小。"""
    counts = _counts()
    out = []
    for f in sorted(BANKS_DIR.glob("*")):
        if not f.is_file():
            continue
        key = f"banks/{f.name}"
        try:
            stat = f.stat()
        except OSError:
            continue
        out.append({
            "key": key,
            "name": f.stem,
            "file": f.name,
            "count": int(counts.get(key, 0)),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })
    return out


def read_state():
    """读取 state.json（不存在或损坏时返回空结构）。"""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def state_summary():
    """首页/侧边栏需要的最小状态。"""
    state = read_state()
    banks = state.get("banks") or {}
    active = state.get("bank_path") or ""
    slot = banks.get(active) or {}
    return {
        "version": state.get("version"),
        "active_bank": active,
        "active_bank_name": Path(active).stem if active else "",
        "current_idx": state.get("current_idx", 0),
        "wrong": len(slot.get("wrong") or []),
        "favorites": len(slot.get("favorites") or []),
        "banks": [
            {
                "key": key,
                "wrong": len(slot_.get("wrong") or []),
                "favorites": len(slot_.get("favorites") or []),
                "progress": slot_.get("progress", 0),
            }
            for key, slot_ in banks.items()
        ],
        "prefs": state.get("prefs") or {},
    }


def dump():
    """一次性 JSON，供 GUI 初始化 / 冒烟测试。"""
    return {"banks": list_banks(), "state": state_summary()}
