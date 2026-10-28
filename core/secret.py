# -*- coding: utf-8 -*-
"""密码存储：Windows 用 DPAPI 加密（仅当前用户可解密），其它平台退化为明文文件。"""
import base64
import ctypes
import ctypes.wintypes as wt
import os
import sys
from pathlib import Path

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _from_blob(blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _dpapi(data: bytes, protect=True):
    if sys.platform != "win32":
        raise OSError("DPAPI 仅在 Windows 可用")
    blob_in, _keep = _to_blob(data)
    blob_out = _BLOB()
    if protect:
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    else:
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f"DPAPI 调用失败（{ctypes.GetLastError()}）")
    return _from_blob(blob_out)


def save_password(path: Path, password: str, mode: str = "dpapi") -> str:
    """保存密码；mode=dpapi 本机加密（换设备失效），mode=plain 明文（便携）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "plain":
        path.write_text("plain:" + base64.b64encode(password.encode("utf-8")).decode(),
                        encoding="utf-8")
        return "plain"
    try:
        blob = _dpapi(password.encode("utf-8"), protect=True)
        path.write_text("dpapi:" + base64.b64encode(blob).decode(), encoding="utf-8")
        return "dpapi"
    except Exception:
        path.write_text("plain:" + base64.b64encode(password.encode("utf-8")).decode(),
                        encoding="utf-8")
        return "plain"


def load_password(path: Path):
    """读取密码；不存在或解密失败返回 ''。"""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if raw.startswith("dpapi:"):
        try:
            return _dpapi(base64.b64decode(raw[6:]), protect=False).decode("utf-8")
        except Exception:
            return ""
    if raw.startswith("plain:"):
        try:
            return base64.b64decode(raw[6:]).decode("utf-8")
        except Exception:
            return ""
    return ""


def clear_password(path: Path):
    try:
        path.unlink()
    except Exception:
        pass


def secret_status(path: Path) -> str:
    """返回 missing / dpapi / plain / dpapi-locked（文件在但本机解不开）。"""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return "missing"
    if raw.startswith("dpapi:"):
        try:
            _dpapi(base64.b64decode(raw[6:]), protect=False)
            return "dpapi"
        except Exception:
            return "dpapi-locked"
    if raw.startswith("plain:"):
        return "plain"
    return "missing"
