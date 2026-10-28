# -*- coding: utf-8 -*-
"""集中定义目录与文件路径（供各模块共用）。"""
import json
import time
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

CLOUD_CONFIG = BASE_DIR / "cloud.json"  # 仅旧版回退
# ---- 配置统一：全部收进项目内的 config/ 目录 ----
# 配置类：设置、云密码、同步记录、设备标识、题库计数 —— 都在 config/
# 数据类：进度 state.json、历史、日志、解析缓存 —— 仍在 quiz_parser.data/
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"
SECRET_FILE = CONFIG_DIR / "cloud.secret"
BANK_COUNTS_FILE = CONFIG_DIR / "bank_counts.json"
SYNC_CACHE_FILE = CONFIG_DIR / "cloud_sync.json"
SYNC_DEVICE_FILE = CONFIG_DIR / "sync_device.json"
GUI_KV_FILE = CONFIG_DIR / "gui_kv.json"
SYNC_LOG_FILE = DATA_DIR / "cloud_sync.log"

# 旧位置 → 新位置；启动时自动搬家，冲突的旧文件进 config/legacy/ 留档。
LEGACY_CONFIG_FILES = (
    (BASE_DIR / "config.json", CONFIG_FILE),
    (BASE_DIR / "config.json.bak", None),
    (BASE_DIR / "cloud.example.json", None),
    (BASE_DIR / "cloud.json", None),
    (DATA_DIR / "ui.json", None),
    (DATA_DIR / "cloud.secret", SECRET_FILE),
    (DATA_DIR / "bank_counts.json", BANK_COUNTS_FILE),
    (DATA_DIR / "cloud_sync.json", SYNC_CACHE_FILE),
    (DATA_DIR / "sync_device.json", SYNC_DEVICE_FILE),
    (DATA_DIR / "gui_kv.json", GUI_KV_FILE),
    (DATA_DIR / "webdav.secret", None),
)


def migrate_legacy_config(verbose=False):
    """把散落在项目根 / quiz_parser.data 的配置收进 config/；可反复调用。"""
    moved = []
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        legacy_dir = CONFIG_DIR / "legacy"
        for src, dst in LEGACY_CONFIG_FILES:
            if not src.exists():
                continue
            target = dst
            if target is None or target.exists():
                legacy_dir.mkdir(exist_ok=True)
                target = legacy_dir / (src.name + ".old")
                if target.exists():
                    target = legacy_dir / ("%s.%d.old" % (src.name, int(time.time())))
            target.parent.mkdir(parents=True, exist_ok=True)
            src.replace(target)
            moved.append(target.name)
    except OSError:
        pass
    if verbose and moved:
        print("配置已整理到 config/：", "、".join(moved))
    return moved


migrate_legacy_config()


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
