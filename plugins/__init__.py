# -*- coding: utf-8 -*-
"""插件目录：放一个 .py，实现 register(app, menu) 即可挂到主菜单。

约定：
  PLUGIN_API = 1
  def register(app, menu):
      menu.add("p", "我的功能", handler)

- PLUGIN_API 不匹配的插件会被跳过并提示。
- 插件加载失败只打印警告，不影响主程序。
- key 建议用字母，避免和数字菜单冲突。
"""
import importlib
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent

# 插件 API 版本：新增/变更钩子时 +1
PLUGIN_API = 1


def load_plugins(app, menu):
    """扫描本目录的 .py（跳过 _ 开头与 __init__），逐个调用 register。"""
    loaded, failed = [], []
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        name = path.stem
        if name.startswith("_") or name == "__init__":
            continue
        try:
            module = importlib.import_module(f"plugins.{name}")
            importlib.reload(module)
            api = getattr(module, "PLUGIN_API", None)
            if api != PLUGIN_API:
                print(f"⚠️ 插件 {name} 的 PLUGIN_API={api}，与当前 {PLUGIN_API} 不匹配，已跳过")
                continue
            register = getattr(module, "register", None)
            if register is None:
                failed.append((name, "缺少 register(app, menu)"))
                continue
            register(app, menu)
            loaded.append(name)
        except Exception as exc:  # 插件坏了不能拖垮主程序
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"[plugin] {name} 加载失败：{exc}", file=sys.stderr)
    return loaded, failed
