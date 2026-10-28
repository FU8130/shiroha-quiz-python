# -*- coding: utf-8 -*-
"""集中定义目录与文件路径（供各模块共用）。"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "quiz_parser.data"
DATA_DIR.mkdir(exist_ok=True)

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

BANKS_DIR = BASE_DIR / "banks"
BANKS_DIR.mkdir(exist_ok=True)

STATE_FILE = DATA_DIR / "state.json"
HISTORY_FILE = DATA_DIR / "history.json"
STATE_VERSION = 2

CLOUD_CONFIG = BASE_DIR / "cloud.json"
SECRET_FILE = DATA_DIR / "cloud.secret"
BANK_COUNTS_FILE = DATA_DIR / "bank_counts.json"


def bank_rel_key(path_obj) -> str:
    """题库标识：在 BASE_DIR 内就用相对路径，搬走整个目录也不失效。"""
    p = Path(path_obj).resolve()
    try:
        return p.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(p)

def bank_abs_path(key: str) -> Path:
    p = Path(key)
    return p if p.is_absolute() else (BASE_DIR / p)

def normalize_bank_key(key: str) -> str:
    """旧版本存的是绝对路径：能落到当前目录下的就改写成相对路径。"""
    if not key:
        return key
    p = Path(key)
    if not p.is_absolute():
        return p.as_posix()
    if p.exists():
        return bank_rel_key(p)
    cand = BANKS_DIR / p.name
    if cand.exists():
        return bank_rel_key(cand)
    return bank_rel_key(p)
