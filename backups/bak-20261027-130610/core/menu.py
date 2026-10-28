# -*- coding: utf-8 -*-
"""菜单注册表：新增一个菜单项只需 menu.add(...) 一行。"""
import unicodedata


def display_width(text):
    """终端显示宽度（中文按 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


class MenuRegistry:
    def __init__(self):
        self._items = []

    def add(self, key, label, handler):
        """注册一项；重复 key 覆盖旧的。"""
        self._items = [it for it in self._items if it[0] != key]
        self._items.append((str(key), label, handler))
        return self

    def handler(self, key):
        for k, _label, fn in self._items:
            if k == str(key):
                return fn
        return None

    def keys(self):
        return [k for k, _l, _f in self._items]

    def render(self, columns=2):
        """多列排版，按显示宽度对齐。"""
        items = self._items
        if not items:
            return ""
        rows = (len(items) + columns - 1) // columns
        cell_w = max((display_width(f"{k}. {label}") for k, label, _f in items), default=10) + 2
        out = []
        for r in range(rows):
            line = ""
            for c in range(columns):
                i = r + c * rows
                if i < len(items):
                    k, label, _ = items[i]
                    cell = f"{k}. {label}"
                    line += cell + " " * (cell_w - display_width(cell))
            out.append(line.rstrip())
        return "\n".join(out)
