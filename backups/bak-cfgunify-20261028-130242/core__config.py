# -*- coding: utf-8 -*-
"""统一配置：项目目录下的 config.json（带旧文件回退，零依赖）。"""
import copy
import json
from pathlib import Path

from core.paths import BASE_DIR, CLOUD_CONFIG, DATA_DIR

CONFIG_FILE = BASE_DIR / "config.json"
UI_FILE = DATA_DIR / "ui.json"

DEFAULTS = {
    "ui": {"color": None},
    "cloud": {
        "url": "",
        "user": "",
        "remote_dir": "quiz_py",
        "auto_sync": False,
        "auto_pull": False,
        "save_sync": False,
        "sync_deletes": False,
        "ignore": ["*.tmp", "~$*"],
        "compression": "standard",
        "migrated_save_sync_off": False,
    },
    "advanced": {"low_write": False, "decompressor": "auto"},
    "srs": {"new_per_day": 20, "review_per_day": 200,
            "steps": [1, 10], "leech": 8,
            "day_start": 4, "fuzz": 0.05, "learn_ahead": 20},
}


def _read_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return {}


def load():
    """读取配置；config.json 优先，旧 cloud.json / ui.json 作为回退。"""
    cfg = copy.deepcopy(DEFAULTS)
    legacy_cloud = _read_json(CLOUD_CONFIG) or {}
    for key, value in legacy_cloud.items():
        if key in cfg["cloud"]:
            cfg["cloud"][key] = value
    legacy_ui = _read_json(UI_FILE) or {}
    if "color" in legacy_ui:
        cfg["ui"]["color"] = legacy_ui["color"]

    current = _read_json(CONFIG_FILE) or {}
    for section, values in current.items():
        if isinstance(values, dict) and isinstance(cfg.get(section), dict):
            cfg[section].update(values)
        else:
            cfg[section] = values

    # 一次性迁移：旧的默认值是「保存即上传」，按要求改成默认不上传；
    # 迁移只做一次，之后用户手动开启不会被再次覆盖。
    if cfg["cloud"].get("save_sync") and not cfg["cloud"].get("migrated_save_sync_off"):
        cfg["cloud"]["save_sync"] = False
        cfg["cloud"]["migrated_save_sync_off"] = True
        try:
            save(cfg)
        except Exception:
            pass
    return cfg


def save(cfg):
    from core.safe_io import atomic_write_json
    atomic_write_json(CONFIG_FILE, cfg)
    return CONFIG_FILE


def cloud():
    return load()["cloud"]


def ui():
    return load()["ui"]


def set_option(section, key, value):
    cfg = load()
    cfg.setdefault(section, {})[key] = value
    save(cfg)
    return cfg
