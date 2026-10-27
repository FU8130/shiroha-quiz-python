# -*- coding: utf-8 -*-
"""终端表现层：颜色、清屏、进度条、单键读取、退出保存。"""
import os
import sys


def _enable_vt_mode():
    """Windows 控制台开启 ANSI 转义（失败就算了，只是没颜色）。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        ctypes.windll.kernel32.SetConsoleMode(handle, 7)
    except Exception:
        pass

_enable_vt_mode()

def _color_enabled():
    """颜色开关：config.json 的 ui.color，缺省按终端能力判断。"""
    try:
        from core.config import ui as ui_cfg
        value = ui_cfg().get("color")
        if value is not None:
            return bool(value)
    except Exception:
        pass
    return sys.stdout.isatty()


USE_COLOR = _color_enabled()

def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else str(text)

def green(t): return paint(t, "32")

def red(t): return paint(t, "31")

def yellow(t): return paint(t, "33")

def cyan(t): return paint(t, "36")

def dim(t): return paint(t, "2")

def bold(t): return paint(t, "1")

def clear_screen():
    if sys.stdout.isatty():
        os.system('cls' if os.name == 'nt' else 'clear')

def progress_bar(done, total, width=20):
    total = max(1, total)
    filled = int(width * min(done, total) / total)
    return "█" * filled + "░" * (width - filled)

# Windows 控制台扫描码 -> 键名
SCAN = {
    "\x3b": "F1", "\x3c": "F2", "\x3d": "F3", "\x3e": "F4",
    "\x3f": "F5", "\x40": "F6", "\x41": "F7", "\x42": "F8",
    "\x43": "F9", "\x44": "F10", "\x85": "F11", "\x86": "F12",
    "\x48": "UP", "\x50": "DOWN", "\x4b": "LEFT", "\x4d": "RIGHT",
}

class KeyReader:
    """交互式终端里读单键（不用回车）；非终端（管道/测试）自动退回整行输入。"""

    @staticmethod
    def available():
        try:
            return bool(sys.stdin) and sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False

    @staticmethod
    def getch():
        if os.name == "nt":
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):      # 功能键：解码第二个字节
                code = msvcrt.getwch()
                return SCAN.get(code, "")
            if ch == "\x03":                # Ctrl+C
                raise KeyboardInterrupt
            return ch
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

class ExitHandler:
    def __init__(self):
        self.app = None

    def signal_handler(self, signum, frame):
        print("\n\n⚠️ 检测到中断，正在保存进度...")
        if self.app:
            try:
                self.app.save_state()
            except Exception:
                pass
        print("✅ 进度已保存，再见！")
        sys.exit(0)


def ask(prompt=""):
    """统一的输入入口。

    测试会把 quiz.input 替换成脚本化输入；这里动态取 quiz 模块上的 input，
    这样搬到 views/ 里的代码也能被测试驱动。
    """
    import builtins
    import sys
    mod = sys.modules.get("quiz")
    fn = getattr(mod, "input", None) if mod else None
    return (fn or builtins.input)(prompt)

def danger_confirm(confirm_fn, action):
    """高危操作：两次确认，第二次直接按回车执行。"""
    if not confirm_fn(f"{action}？此操作不可恢复 (y/N)"):
        return False
    try:
        return ask("再次确认：直接回车执行，其它任意键取消 > ").strip() == ""
    except (EOFError, KeyboardInterrupt):
        return False
