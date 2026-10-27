# -*- coding: utf-8 -*-
"""WebDAV 增量同步：只传变化的文件，每个文件单独 xz 压缩，省流量。

远端布局：
    <remote>/manifest.json      文件清单（sha256/大小）
    <remote>/files/<路径>.xz    逐文件压缩内容
"""
import fnmatch
import hashlib
import json
import lzma
from datetime import datetime, timezone

PRESET = 9 | getattr(lzma, "PRESET_EXTREME", 0)
STATE_REL = "quiz_parser.data/state.json"
HISTORY_REL = "quiz_parser.data/history.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compress(data: bytes) -> bytes:
    from core.cloudpack import compress_bytes
    return compress_bytes(data, level="standard")


def decompress(data: bytes) -> bytes:
    from core.cloudpack import decompress_bytes
    return decompress_bytes(data)


def _ignored(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in (patterns or []))


def collect_local(banks_dir, state_file=None, history_file=None, ignore=None):
    """本地待同步文件：相对路径 -> Path（ignore 支持通配符）。"""
    out = {}
    for f in sorted(banks_dir.glob("*")):
        if f.is_file() and not _ignored(f.name, ignore):
            out[f"banks/{f.name}"] = f
    if state_file is not None and state_file.exists():
        out[STATE_REL] = state_file
    if history_file is not None and history_file.exists():
        out[HISTORY_REL] = history_file
    return out


def _dirs_of(remote, rel):
    """返回需要创建的远端目录（从浅到深）。"""
    parts = rel.split("/")[:-1]
    out, acc = [], ""
    for p in parts:
        acc = f"{acc}/{p}" if acc else p
        out.append(f"{remote}/files/{acc}" if remote else f"files/{acc}")
    return out


def log_line(log_path, message):
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except Exception:
        pass


def _load_cache(path):
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path, data):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        from core.safe_io import atomic_write_json
        atomic_write_json(path, data)
    except Exception:
        pass


def push(client, remote, local_map, cache_path=None, force=False, min_interval=0, log_path=None):
    """增量上传。

    - cache_path 存在时，用本地缓存判断差异，完全没变则**不发任何请求**
    - force=True 忽略 min_interval（手动同步用）
    """
    cache = _load_cache(cache_path)
    known = dict(cache.get("files") or {})
    manifest_path = f"{remote}/manifest.json" if remote else "manifest.json"

    if cache_path is not None and not force and min_interval:
        last = cache.get("last_sync", 0)
        if last and (datetime.now().timestamp() - last) < min_interval:
            return {"uploaded": 0, "skipped": len(local_map), "sent": 0,
                    "plain": 0, "files": len(local_map), "cached": True, "throttled": True}

    uploaded, skipped, sent, plain_total = 0, 0, 0, 0
    diffs = []
    for rel, path in local_map.items():
        data = path.read_bytes()
        h = sha256(data)
        if (known.get(rel) or {}).get("sha256") == h:
            skipped += 1
            continue
        diffs.append((rel, path, data, h))

    if cache_path is not None and not diffs:
        cache["last_sync"] = datetime.now().timestamp()
        _save_cache(cache_path, cache)
        return {"uploaded": 0, "skipped": skipped, "sent": 0,
                "plain": 0, "files": len(local_map), "cached": True}

    if not cache_path or not known:
        try:
            remote_manifest = json.loads(client.get(manifest_path).decode("utf-8"))
            known.update(remote_manifest.get("files") or {})
        except Exception:
            pass

    for d in {d for rel in local_map for d in _dirs_of(remote, rel)}:
        client.ensure_dir(d)

    for rel, path, data, h in diffs:
        packed = compress(data)
        from core.cloudpack import suffix_for
        ext = ".7z" if packed[:2] == b"7z" else ".xz"
        target = f"{remote}/files/{rel}{ext}" if remote else f"files/{rel}{ext}"
        client.put(target, packed)
        known[rel] = {"sha256": h, "size": len(data), "packed": len(packed),
                      "mtime": path.stat().st_mtime}
        uploaded += 1
        sent += len(packed)
        plain_total += len(data)

    if uploaded:
        manifest = {"version": 1, "updated": datetime.now().isoformat(timespec="seconds"),
                    "files": known}
        payload = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
        client.put(manifest_path, payload)
        sent += len(payload)

    cache["files"] = known
    cache["last_sync"] = datetime.now().timestamp()
    _save_cache(cache_path, cache)
    log_line(log_path, f"上传：{uploaded} 个文件，跳过 {skipped} 个，"
                       f"发送 {sent/1024:.1f} KB（原始 {plain_total/1024:.1f} KB）")
    return {"uploaded": uploaded, "skipped": skipped, "sent": sent,
            "plain": plain_total, "files": len(local_map), "cached": False}


def pull(client, remote, banks_dir, state_file=None, history_file=None, cache_path=None, log_path=None):
    """把远端变化拉回本地；返回统计。"""
    manifest_path = f"{remote}/manifest.json" if remote else "manifest.json"
    cache = _load_cache(cache_path)
    entries = None
    sig = None
    try:
        st = client.stat(manifest_path)
    except Exception:
        st = None
    if st is not None:
        sig = f"{st[0]}|{st[1]}"
        if cache.get("manifest_sig") == sig and cache.get("files"):
            entries = cache["files"]        # 远端清单没变，直接本地判断
    if entries is None:
        manifest = json.loads(client.get(manifest_path).decode("utf-8"))
        entries = manifest.get("files") or {}
        if sig:
            cache["manifest_sig"] = sig

    downloaded, skipped, got, plain_total = 0, 0, 0, 0
    conflicts = []
    cache_files = dict((_load_cache(cache_path).get("files") or {}))
    for rel, meta in entries.items():
        target = None
        if rel.startswith("banks/"):
            target = banks_dir / rel.split("/", 1)[1]
        elif rel == STATE_REL and state_file is not None:
            target = state_file
        elif rel == HISTORY_REL and history_file is not None:
            target = history_file
        if target is None:
            continue
        local_hash = sha256(target.read_bytes()) if target.exists() else None
        if local_hash == meta.get("sha256"):
            skipped += 1
            continue
        cached_hash = (cache_files.get(rel) or {}).get("sha256")
        if target.exists() and local_hash != cached_hash:
            # 本地也改过 → 冲突，保留本地副本再覆盖
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
            conflict = target.with_name(f"{target.stem}.conflict-{stamp}{target.suffix}")
            target.replace(conflict)
            conflicts.append(conflict.name)
        packed = None
        for ext in (".7z", ".xz"):
            try:
                packed = client.get(f"{remote}/files/{rel}{ext}" if remote else f"files/{rel}{ext}")
                break
            except Exception:
                continue
        if packed is None:
            continue
        data = decompress(packed)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        downloaded += 1
        got += len(packed)
        plain_total += len(data)
    if cache_path is not None:
        cache = _load_cache(cache_path)
        files = dict(cache.get("files") or {})
        files.update({rel: meta for rel, meta in entries.items()})
        cache["files"] = files
        cache["last_sync"] = datetime.now().timestamp()
        if sig:
            cache["manifest_sig"] = sig
        _save_cache(cache_path, cache)
    log_line(log_path, f"拉取：下载 {downloaded} 个，跳过 {skipped} 个，"
                       f"接收 {got/1024:.1f} KB，冲突 {len(conflicts)} 个")
    return {"downloaded": downloaded, "skipped": skipped, "got": got,
            "plain": plain_total, "cached": False, "conflicts": conflicts}
