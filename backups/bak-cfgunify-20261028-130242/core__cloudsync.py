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
from pathlib import Path

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


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


DELETED_TTL_DAYS = 180
DEVICE_FILE = "sync_device.json"


def _prune_deleted(deleted):
    cutoff = datetime.now().timestamp() - DELETED_TTL_DAYS * 86400
    return {rel: ts for rel, ts in (deleted or {}).items() if _parse_iso(ts) >= cutoff}


def device_id(data_dir=None):
    """本设备标识。落在 quiz_parser.data/sync_device.json，跟着项目迁移。"""
    if data_dir is None:
        return "local"
    path = Path(data_dir) / DEVICE_FILE
    try:
        if path.exists():
            info = json.loads(path.read_text(encoding="utf-8"))
            if info.get("id"):
                return str(info["id"])
    except Exception:
        pass
    import uuid
    info = {"id": uuid.uuid4().hex[:12], "created": _now_iso()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        from core.safe_io import atomic_write_json
        atomic_write_json(path, info)
    except Exception:
        pass
    return info["id"]


def _remote_manifest(client, remote):
    path = f"{remote}/manifest.json" if remote else "manifest.json"
    try:
        return json.loads(client.get(path).decode("utf-8")), path
    except Exception:
        return None, path


def _target_for(rel, banks_dir, state_file, history_file):
    if rel.startswith("banks/"):
        return banks_dir / rel.split("/", 1)[1]
    if rel == STATE_REL and state_file is not None:
        return Path(state_file)
    if rel == HISTORY_REL and history_file is not None:
        return Path(history_file)
    return None


def _write_manifest(client, path, files, deleted, cache=None, device=None):
    manifest = {"version": 2, "updated": _now_iso(),
                "files": files, "deleted": _prune_deleted(deleted)}
    if device:
        manifest["devices"] = {device: manifest["updated"]}
    payload = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    client.put(path, payload)
    if cache is not None:
        cache["manifest_updated"] = manifest["updated"]
        cache["deleted"] = manifest["deleted"]
    return payload


def plan(client, remote, local_map, cache_path=None):
    """同步预检：不发写请求，只读远端清单，报告会动哪些文件。"""
    cache = _load_cache(cache_path)
    known = dict(cache.get("files") or {})
    remote_manifest, _ = _remote_manifest(client, remote)
    remote_files = dict((remote_manifest or {}).get("files") or {})
    remote_deleted = dict((remote_manifest or {}).get("deleted") or {})

    local_sha = {}
    for rel, path in local_map.items():
        try:
            local_sha[rel] = sha256(Path(path).read_bytes())
        except OSError:
            continue

    to_upload = [rel for rel, h in local_sha.items() if (known.get(rel) or {}).get("sha256") != h]
    to_download = [rel for rel, meta in remote_files.items()
                   if (known.get(rel) or {}).get("sha256") != meta.get("sha256")]
    conflicts = [rel for rel in to_upload
                 if rel in remote_files
                 and known.get(rel, {}).get("sha256") not in (None, remote_files[rel].get("sha256"))]
    local_deleted = [rel for rel in known if rel not in local_sha]
    remote_deleted_local = [rel for rel in remote_deleted if rel in local_sha]
    resurrect = [rel for rel in remote_deleted_local
                 if rel in known and local_sha.get(rel) == (known.get(rel) or {}).get("sha256")]
    return {"to_upload": to_upload, "to_download": to_download, "conflicts": conflicts,
            "local_deleted": local_deleted, "remote_deleted": remote_deleted_local,
            "resurrect_blocked": resurrect,
            "unchanged": len(local_sha) - len(to_upload),
            "remote_files": len(remote_files)}


def push(client, remote, local_map, cache_path=None, force=False, min_interval=0,
         log_path=None, policy="overwrite", prune=True, data_dir=None):
    """增量上传。

    - cache_path 存在时，用本地缓存判断差异，完全没变则**不发任何请求**
    - force=True 忽略 min_interval（手动同步用）
    - policy: overwrite（默认，冲突时以本地为准）/ skip（发现远端已变则整体跳过）
    - prune=True 时，本地删掉的文件会在远端一并删除并写墓碑（deleted）
    """
    cache = _load_cache(cache_path)
    known = dict(cache.get("files") or {})
    deleted = dict(cache.get("deleted") or {})
    manifest_path = f"{remote}/manifest.json" if remote else "manifest.json"
    device = device_id(data_dir)

    if cache_path is not None and not force and min_interval:
        last = cache.get("last_sync", 0)
        if last and (datetime.now().timestamp() - last) < min_interval:
            return {"uploaded": 0, "skipped": len(local_map), "sent": 0,
                    "plain": 0, "files": len(local_map), "cached": True,
                    "throttled": True, "deleted": 0, "conflicts": [], "policy": policy}

    hashes = {}
    for rel, path in local_map.items():
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        hashes[rel] = (Path(path), data, sha256(data))

    diffs = [(rel,) + hashes[rel] for rel in hashes
             if (known.get(rel) or {}).get("sha256") != hashes[rel][2]]
    removed = [rel for rel in known if rel not in hashes]

    if diffs or removed:
        remote_manifest, _ = _remote_manifest(client, remote)
    else:
        remote_manifest = None
    remote_files = dict((remote_manifest or {}).get("files") or {})
    remote_deleted = dict((remote_manifest or {}).get("deleted") or {})

    # 远端墓碑：本机还留着旧文件时不重新上传（防止离线设备把已删文件“复活”）
    resurrect_blocked = []
    if remote_deleted:
        keep = []
        for item in diffs:
            rel, path, data, h = item
            known_sha = (known.get(rel) or {}).get("sha256")
            if rel in remote_deleted and rel not in remote_files and known_sha and known_sha == h:
                resurrect_blocked.append(rel)
                continue
            keep.append(item)
        diffs = keep

    # 冲突：远端这份文件跟我们上次同步时不一样，且与本地也不同 → 两台设备都改过
    conflicts = []
    survivors = []
    for rel, path, data, h in diffs:
        remote_sha = (remote_files.get(rel) or {}).get("sha256")
        known_sha = (known.get(rel) or {}).get("sha256")
        if remote_sha and remote_sha == h:
            known[rel] = remote_files[rel]
            continue
        if remote_sha and known_sha and remote_sha != known_sha:
            conflicts.append(rel)
        survivors.append((rel, path, data, h))
    diffs = survivors

    if policy == "skip" and conflicts:
        log_line(log_path, f"跳过上传：远端已变化 {len(conflicts)} 个文件（policy=skip）")
        return {"uploaded": 0, "skipped": len(hashes), "sent": 0, "plain": 0,
                "files": len(hashes), "cached": False, "deleted": 0,
                "conflicts": conflicts, "policy": policy, "skipped_conflict": True,
                "resurrect_blocked": resurrect_blocked}

    if not diffs and not removed:
        cache["last_sync"] = datetime.now().timestamp()
        _save_cache(cache_path, cache)
        return {"uploaded": 0, "skipped": len(hashes), "sent": 0, "plain": 0,
                "files": len(hashes), "cached": True, "deleted": 0,
                "conflicts": conflicts, "policy": policy,
                "resurrect_blocked": resurrect_blocked}

    for d in {d for rel in local_map for d in _dirs_of(remote, rel)}:
        client.ensure_dir(d)

    uploaded, sent, plain_total = 0, 0, 0
    for rel, path, data, h in diffs:
        packed = compress(data)
        ext = ".7z" if packed[:2] == b"7z" else ".xz"
        target = f"{remote}/files/{rel}{ext}" if remote else f"files/{rel}{ext}"
        client.put(target, packed)
        # 同一文件只保留一种压缩后缀：历史上 .xz/.7z 交替时远端会留两份，内容容易打架
        alt_ext = ".xz" if ext == ".7z" else ".7z"
        alt = (remote + "/files/" + rel + alt_ext) if remote else ("files/" + rel + alt_ext)
        try:
            client.delete(alt)
        except Exception:
            pass
        known[rel] = {"sha256": h, "size": len(data), "packed": len(packed),
                      "mtime": path.stat().st_mtime}
        uploaded += 1
        sent += len(packed)
        plain_total += len(data)

    pruned = 0
    if prune and removed:
        for rel in removed:
            for ext in (".xz", ".7z"):
                target = f"{remote}/files/{rel}{ext}" if remote else f"files/{rel}{ext}"
                try:
                    client.delete(target)
                except Exception:
                    pass
            known.pop(rel, None)
            deleted[rel] = _now_iso()
            pruned += 1

    if uploaded or pruned:
        merged_deleted = dict(deleted)
        for rel, ts in remote_deleted.items():
            if rel not in merged_deleted:
                merged_deleted[rel] = ts
        payload = _write_manifest(client, manifest_path, known, merged_deleted, cache, device)
        sent += len(payload)
        deleted = merged_deleted

    cache["files"] = known
    cache["deleted"] = deleted
    cache["last_sync"] = datetime.now().timestamp()
    _save_cache(cache_path, cache)
    log_line(log_path, f"上传：{uploaded} 个文件，跳过 {max(0, len(hashes) - uploaded)} 个，"
                       f"删除同步 {pruned} 个，冲突 {len(conflicts)} 个，"
                       f"发送 {sent/1024:.1f} KB（原始 {plain_total/1024:.1f} KB）")
    return {"uploaded": uploaded, "skipped": max(0, len(hashes) - uploaded), "sent": sent,
            "plain": plain_total, "files": len(hashes), "cached": False,
            "deleted": pruned, "conflicts": conflicts, "policy": policy,
            "resurrect_blocked": resurrect_blocked}


def pull(client, remote, banks_dir, state_file=None, history_file=None, cache_path=None,
         log_path=None, policy="overwrite", trash_dir=None, tombstone_delete=True):
    """把远端变化拉回本地；返回统计。

    - 远端墓碑（deleted）里、本地又没改过的文件 → 移入 backups/cloud-deleted（不复活、不硬删）
    - policy=skip 时，本地改过的文件一律保留，不下载远端版本
    """
    manifest_path = f"{remote}/manifest.json" if remote else "manifest.json"
    if trash_dir is None:
        trash_dir = Path(banks_dir).parent / "backups" / "cloud-deleted"
    cache = _load_cache(cache_path)
    entries = None
    sig = None
    deleted = {}
    try:
        st = client.stat(manifest_path)
    except Exception:
        st = None
    if st is not None:
        sig = f"{st[0]}|{st[1]}"
        if cache.get("manifest_sig") == sig and cache.get("files"):
            entries = cache["files"]          # 远端清单没变，直接本地判断
            deleted = dict(cache.get("deleted") or {})
    if entries is None:
        manifest = json.loads(client.get(manifest_path).decode("utf-8"))
        entries = manifest.get("files") or {}
        deleted = dict(manifest.get("deleted") or {})
        if sig:
            cache["manifest_sig"] = sig

    downloaded, skipped, got, plain_total = 0, 0, 0, 0
    conflicts, removed_local = [], []
    cache_files = dict((cache.get("files") or {}))

    # ① 先处理远端墓碑：本地没改过的旧文件移入回收目录
    if tombstone_delete:
        for rel, ts in deleted.items():
            if rel in entries:
                continue                      # 后来又被重新上传了，以文件为准
            target = _target_for(rel, banks_dir, state_file, history_file)
            if target is None or not target.exists():
                continue
            local_hash = sha256(target.read_bytes())
            cached_hash = (cache_files.get(rel) or {}).get("sha256")
            if local_hash != cached_hash:
                conflicts.append(target.name + "（本地也改过，保留）")
                continue
            try:
                trash_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
                trash = Path(trash_dir) / f"{target.stem}.{stamp}{target.suffix}"
                target.replace(trash)
                removed_local.append(target.name)
                cache_files.pop(rel, None)
            except Exception:
                pass

    # ② 再按清单拉取
    for rel, meta in entries.items():
        target = _target_for(rel, banks_dir, state_file, history_file)
        if target is None:
            continue
        local_hash = sha256(target.read_bytes()) if target.exists() else None
        if local_hash == meta.get("sha256"):
            skipped += 1
            continue
        cached_hash = (cache_files.get(rel) or {}).get("sha256")
        if target.exists() and local_hash != cached_hash:
            if policy == "skip":
                conflicts.append(target.name + "（本地也改过，保留）")
                skipped += 1
                continue
            # 本地也改过 → 冲突，保留本地副本再覆盖
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
            conflict = target.with_name(f"{target.stem}.conflict-{stamp}{target.suffix}")
            target.replace(conflict)
            conflicts.append(conflict.name)
        # 远端同一文件可能同时留着 .7z 和 .xz（历史遗留），按清单 sha256 挑对的那份
        data = None
        fallback = None
        got_bytes = 0
        for ext in (".7z", ".xz"):
            try:
                cand = client.get(f"{remote}/files/{rel}{ext}" if remote else f"files/{rel}{ext}")
            except Exception:
                continue
            try:
                plain = decompress(cand)
            except Exception:
                continue
            if fallback is None:
                fallback = plain
                got_bytes = len(cand)
            if sha256(plain) == meta.get("sha256"):
                data = plain
                got_bytes = len(cand)
                break
        if data is None:
            data = fallback
        if data is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        downloaded += 1
        got += got_bytes
        plain_total += len(data)

    if cache_path is not None:
        cache = _load_cache(cache_path)
        files = dict(cache.get("files") or {})
        files.update({rel: meta for rel, meta in entries.items()})
        for rel in removed_local:
            files.pop(_key_of(rel, entries), None)
        cache["files"] = files
        cache["deleted"] = deleted
        cache["last_sync"] = datetime.now().timestamp()
        if sig:
            cache["manifest_sig"] = sig
        _save_cache(cache_path, cache)
    log_line(log_path, f"拉取：下载 {downloaded} 个，跳过 {skipped} 个，"
                       f"墓碑删除 {len(removed_local)} 个，冲突 {len(conflicts)} 个，"
                       f"接收 {got/1024:.1f} KB")
    return {"downloaded": downloaded, "skipped": skipped, "got": got,
            "plain": plain_total, "cached": False, "conflicts": conflicts,
            "removed": removed_local}


def _key_of(name, entries):
    """按文件名反查清单里的相对路径。"""
    for rel in entries:
        if rel.split("/")[-1] == name:
            return rel
    return name
