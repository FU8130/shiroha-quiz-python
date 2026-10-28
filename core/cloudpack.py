# -*- coding: utf-8 -*-
"""云端备份打包：文本内容用 xz 极限压缩，减小 WebDAV 流量。"""
from pathlib import Path
import io
import lzma
import os
import shutil
import subprocess
import tempfile
import tarfile
import zipfile

LEVELS = {"fast": 3, "standard": 6, "extreme": 9 | getattr(lzma, "PRESET_EXTREME", 0)}
PRESET = LEVELS["extreme"]  # 兼容旧调用


def _preset(level):
    return LEVELS.get(str(level or "standard"), LEVELS["standard"])


Z7_MAGIC = b"7z\xbc\xaf"
MX = {"fast": "1", "standard": "5", "extreme": "9"}


def seven_zip_path():
    """查找 7-Zip：只认项目内置与 PATH，不写死任何本机路径。

    顺序：tools/7z/7z.exe → tools/7zr.exe → PATH 中的 7zr/7z
    """
    base = Path(__file__).resolve().parent.parent
    for candidate in (base / "tools" / "7z" / "7z.exe", base / "tools" / "7zr.exe"):
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue
    return shutil.which("7zr") or shutil.which("7z") or ""


def suffix_for(packed: bytes) -> str:
    return ".7z" if packed[:2] == Z7_MAGIC[:2] else ".tar.xz"


def work_temp_dir():
    """压缩/解压用的中转目录：优先系统临时目录，不可用时退回项目内 tmp。"""
    import os
    base = tempfile.gettempdir()
    try:
        probe = Path(base) / "quiz_py_probe"
        probe.mkdir(parents=True, exist_ok=True)
        probe.rmdir()
        return base
    except Exception:
        from core.paths import DATA_DIR
        fallback = DATA_DIR / "tmp"
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)

def compress_bytes(data: bytes, level="standard", compressor="auto") -> bytes:
    """把 tar 字节压成 7z（有 7zr 时）或 xz。"""
    exe = seven_zip_path()
    if compressor in ("auto", "7z") and exe:
        tmp = work_temp_dir()
        with tempfile.TemporaryDirectory(dir=tmp) as td:
            src = Path(td) / "data.tar"
            out = Path(td) / "out.7z"
            src.write_bytes(data)
            subprocess.run([exe, "a", "-t7z", f"-mx={MX.get(level, '5')}", "-mmt=on",
                            str(out), str(src)], check=True,
                           capture_output=True, timeout=600,
                           env={**os.environ, "TEMP": str(tmp), "TMP": str(tmp),
                                "TMPDIR": str(tmp)})
            return out.read_bytes()
    return lzma.compress(data, format=lzma.FORMAT_XZ, preset=_preset(level))


def _decompress_policy():
    try:
        from core.config import load
        return str(load().get("advanced", {}).get("decompressor", "auto"))
    except Exception:
        return "auto"


def decompress_bytes(packed: bytes) -> bytes:
    """解压。

    策略（config.json advanced.decompressor）：
      7z    - 优先 7-Zip（默认），失败回退标准库
      auto  - .7z 用 7-Zip；.xz 用标准库（更省进程开销）
      xz    - 一律用标准库（.7z 会失败）
    """
    is_7z = packed[:2] == Z7_MAGIC[:2]
    policy = _decompress_policy()
    exe = seven_zip_path()

    if exe and (is_7z or policy == "7z"):
        try:
            tmp = work_temp_dir()
            with tempfile.TemporaryDirectory(dir=tmp) as td:
                arc = Path(td) / ("in.7z" if is_7z else "in.xz")
                arc.write_bytes(packed)
                res = subprocess.run([exe, "x", "-so", str(arc)], check=True,
                                     capture_output=True, timeout=600,
                                     env={**os.environ, "TEMP": str(tmp),
                                          "TMP": str(tmp), "TMPDIR": str(tmp)})
                return res.stdout
        except Exception:
            if is_7z:
                raise RuntimeError("7-Zip 解压失败，且标准库不支持 .7z")
    if is_7z:
        raise RuntimeError("备份是 7z 格式，需要 7-Zip")
    return lzma.decompress(packed)


def pack_backup(banks_dir, state_file=None, history_file=None, level="standard"):
    """把题库与状态打成 tar.xz，返回 (压缩后字节, 原始字节数)。"""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for f in sorted(banks_dir.glob("*")):
            if f.is_file():
                tf.add(f, arcname=f"banks/{f.name}")
        for src, name in ((state_file, "quiz_parser.data/state.json"),
                          (history_file, "quiz_parser.data/history.json")):
            if src is not None and src.exists():
                tf.add(src, arcname=name)
    plain = raw.getvalue()
    packed = compress_bytes(plain, level=level)
    return packed, len(plain)


def unpack_backup(data: bytes):
    """支持 .tar.xz 与旧 .zip，返回 {归档内路径: 内容}。"""
    if data[:2] == Z7_MAGIC[:2]:
        plain = decompress_bytes(data)
        out = {}
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:") as tf:
            for member in tf.getmembers():
                if member.isfile():
                    f = tf.extractfile(member)
                    if f is not None:
                        out[member.name] = f.read()
        return out
    if data[:4] == b"PK\x03\x04":
        out = {}
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if not name.endswith("/"):
                    out[name] = zf.read(name)
        return out
    plain = decompress_bytes(data)
    out = {}
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:") as tf:
        for member in tf.getmembers():
            if member.isfile():
                f = tf.extractfile(member)
                if f is not None:
                    out[member.name] = f.read()
    return out


def is_backup_name(name: str) -> bool:
    return name.endswith(".tar.xz") or name.endswith(".zip")


PROJECT_EXCLUDE_DIRS = {"backups", "__pycache__", ".git", "exports", "cache", "logs", "7z"}
PROJECT_EXCLUDE_FILES = {"cloud.secret", "cloud_sync.json", "cloud_sync.log",
                         "snapshot.sha256", ".lock", ".portable-root",
                         "7zr.exe", "7z.exe", "7z.dll", "7zG.exe", "7zFM.exe"}
PROJECT_EXCLUDE_SUFFIX = (".pyc", ".tmp", ".bak", ".writing", ".pyo")


def pack_project(project_root, level="extreme", compressor="xz"):
    """把整个项目打包为 tar.xz，排除密码/缓存/旧备份。返回 (bytes, 原始大小, 文件数)。"""
    root = Path(project_root)
    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in PROJECT_EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.name in PROJECT_EXCLUDE_FILES or p.name.endswith(PROJECT_EXCLUDE_SUFFIX):
            continue
        files.append(p)

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for f in files:
            tf.add(f, arcname=str(f.relative_to(root)).replace("\\", "/"))
    plain = raw.getvalue()
    return compress_bytes(plain, level=level, compressor=compressor), len(plain), len(files)
