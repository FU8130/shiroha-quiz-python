# -*- coding: utf-8 -*-
"""GUI 套壳：本地 HTTP 服务，前端在 gui/static/，只替换存储层。"""
import base64
import hmac
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.paths import (BANKS_DIR, BASE_DIR, CONFIG_DIR, DATA_DIR, GUI_KV_FILE,
                        HISTORY_FILE, SECRET_FILE, STATE_FILE, SYNC_CACHE_FILE)
from core.safe_io import atomic_write_json
from services.banks import list_banks, read_state
from gui.questions import load_questions

WEB_DIR = Path(__file__).resolve().parent / "static"
KV_FILE = GUI_KV_FILE  # config/gui_kv.json
WEBDAV_SECRET = SECRET_FILE  # 与 TUI 共用同一份云密码（config/cloud.secret）

def _migrate_webdav_secret():
    """早期 GUI 用独立 webdav.secret；统一到 cloud.secret，旧文件改名备份。"""
    legacy = DATA_DIR / "webdav.secret"
    try:
        if not legacy.exists():
            return
        if not WEBDAV_SECRET.exists():
            legacy.replace(WEBDAV_SECRET)
        else:
            legacy.replace(DATA_DIR / "webdav.secret.bak")
    except OSError:
        pass


_migrate_webdav_secret()
_SECRET_KV = re.compile(r"(pass|secret|token|api[_-]?key|ai_key)", re.I)

# 前端诊断日志：放系统目录（%LOCALAPPDATA%\ShirohaQuiz\logs），不污染便携数据
LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ShirohaQuiz" / "logs"
LOG_FILE = LOG_DIR / "gui.log"
LOG_MAX_BYTES = 512 * 1024
_LOG_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()


def _log_write(level: str, msg: str, extra=None) -> None:
    try:
        with _LOG_LOCK:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
                for i in (2, 1):
                    src = LOG_FILE.with_name(f"gui.{i}.log")
                    if src.exists():
                        src.replace(LOG_FILE.with_name(f"gui.{i + 1}.log"))
                LOG_FILE.replace(LOG_FILE.with_name("gui.1.log"))
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            tail = (" " + json.dumps(extra, ensure_ascii=False)) if extra else ""
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(f"{ts} [{level}] {msg}{tail}\n")
    except Exception:
        pass

_MIME_OVERRIDE = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _gui_section(st: dict) -> dict:
    gui = st.get("gui")
    return gui if isinstance(gui, dict) else {}


def _read_kv() -> dict:
    """UI 偏好与 TUI 数据同放 state.json 的 gui 段（便携、单一数据源）。"""
    st = read_state()
    out = {k: v for k, v in _gui_section(st).items() if isinstance(v, str)}
    if not out and KV_FILE.exists():
        # 兼容旧版独立文件：一次性并回 state.json
        legacy = _read_json(KV_FILE, {})
        if isinstance(legacy, dict) and legacy:
            st["gui"] = dict(_gui_section(st), **{str(k): str(v) for k, v in legacy.items()})
            atomic_write_json(STATE_FILE, st)
            KV_FILE.replace(KV_FILE.with_name(KV_FILE.name + ".bak"))
            return {str(k): str(v) for k, v in legacy.items()}
    return out


def _write_kv(kv: dict) -> None:
    """只落盘 UI 偏好（主题/侧栏等）；密钥与超大缓存不写。"""
    clean = {}
    for k, v in kv.items():
        if _SECRET_KV.search(k) or len(v) > 256_000:
            continue
        clean[k] = v
    st = read_state()
    st["gui"] = dict(_gui_section(st), **clean)
    atomic_write_json(STATE_FILE, st)


def _iso(ts):
    """epoch 秒 → 本地 ISO 时间；失败返回空串。"""
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(timespec="seconds")
    except Exception:
        return ""


def _epoch(iso):
    """ISO 时间 → epoch 秒；失败返回 0。"""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _wrong_entries(slot: dict) -> list:
    status = slot.get("wrong_status") or {}
    counts = slot.get("wrong_counts") or {}
    rights = slot.get("right_counts") or {}
    lasts = slot.get("wrong_last") or {}
    out = []
    for qid in slot.get("wrong") or []:
        out.append({
            "id": qid,
            "wrongCount": int(counts.get(qid, 1) or 1),
            "rightCount": int(rights.get(qid, 0) or 0),
            "reviewRightCount": int(rights.get(qid, 0) or 0),
            "streakCorrectCount": 0,
            "lastWrongAt": _iso(lasts.get(qid)),
            "lastCorrectAt": "",
            "lastReviewedAt": _iso(lasts.get(qid)),
            "nextReviewAt": "",
            "reviewLevel": 0,
            "lastAnswer": [],
            "source": "tui",
            "timestamp": int(float(lasts.get(qid) or 0) * 1000),
            "status": str(status.get(qid) or "未掌握"),
        })
    return out


def _merge_records(gui_records, tui_records) -> list:
    """GUI 记录 + TUI history 合并去重（TUI 后补的记录也要出现在 GUI 里）。"""
    merged, seen = [], set()

    def sig(rec):
        keys = ("mode", "bankName", "date", "total", "correct")
        return "|".join(str(rec.get(k) or "") for k in keys)

    def add(rec):
        if not isinstance(rec, dict):
            return
        key = sig(rec)
        if key in seen:
            return
        seen.add(key)
        merged.append(rec)

    for rec in (gui_records if isinstance(gui_records, list) else []):
        add(rec)
    for rec in (tui_records if isinstance(tui_records, list) else []):
        add(rec)
    merged.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    return merged


def _history_records() -> list:
    """TUI 的 history.json → 前端 records 形状（新的在前）。"""
    from core.paths import HISTORY_FILE

    hist = _read_json(HISTORY_FILE, [])
    out = []
    if not isinstance(hist, list):
        return out
    for i, rec in enumerate(reversed(hist)):
        if not isinstance(rec, dict):
            continue
        total = int(rec.get("total") or 0)
        correct = int(rec.get("correct") or 0)
        mode = "考试" if "考试" in str(rec.get("mode", "")) else "练习"
        out.append({
            "id": f"tui-{i}",
            "mode": mode,
            "bankId": rec.get("bank_key") or "",
            "bankName": rec.get("bank_name") or rec.get("bank") or "TUI",
            "scopeType": "BANK",
            "scopeName": rec.get("bank_name") or "",
            "total": total,
            "answered": total,
            "correct": correct,
            "wrong": max(0, total - correct),
            "accuracy": int(rec.get("accuracy") or 0),
            "score": rec.get("score"),
            "date": rec.get("date") or "",
            "duration": int(rec.get("duration") or 0),
            "details": [],
        })
    return out


def _safe_bank_path(name: str) -> Path:
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "")).strip(" .") or "导入题库"
    base = base[:60]
    path = BASE_DIR / "banks" / f"{base}.json"
    i = 2
    while path.exists():
        path = BASE_DIR / "banks" / f"{base}_{i}.json"
        i += 1
    return path


def _web_questions_to_tui(questions) -> list:
    out = []
    for i, q in enumerate(questions or [], 1):
        if not isinstance(q, dict):
            continue
        raw_opts = q.get("options")
        options = []
        if isinstance(raw_opts, dict):
            for k, v in raw_opts.items():
                options.append({"key": str(k), "text": str(v)})
        elif isinstance(raw_opts, list):
            for o in raw_opts:
                if isinstance(o, dict):
                    options.append({"key": str(o.get("key") or chr(65 + len(options))),
                                    "text": str(o.get("text") or o.get("value") or "")})
                elif isinstance(o, str):
                    options.append({"key": chr(65 + len(options)), "text": o})
        answer = q.get("answer") or []
        if isinstance(answer, str):
            answer = [answer]
        out.append({
            "number": q.get("number") or i,
            "type": str(q.get("type") or "single").lower(),
            "question": str(q.get("question") or ""),
            "options": options,
            "answer": [str(a) for a in answer],
            "analysis": q.get("analysis") or "",
            "category": q.get("category") or "",
            "score": q.get("score"),
            "blankAnswers": q.get("blankAnswers") or [],
        })
    return out


def build_web_state() -> dict:
    """把 TUI 的 state.json / history.json 翻译成原前端认识的形状。"""
    st = read_state()
    slots = st.get("banks") or {}
    gui = st.get("gui") if isinstance(st.get("gui"), dict) else {}
    aliases = gui.get("bank_alias") if isinstance(gui.get("bank_alias"), dict) else {}
    alias_targets = set(aliases.values())
    meta = list_banks()
    banks, wrong_book, favorites = [], {}, {}
    for item in meta:
        key = item["key"]
        if key in alias_targets:
            continue  # 这个文件是 GUI 导入题库的落盘副本，由下面的别名条目统一展示
        slot = slots.get(key) or {}
        banks.append({
            "id": key,
            "name": item.get("name") or Path(key).stem,
            "groupName": "",
            "createdAt": "",
            "updatedAt": "",
            "questions": load_questions(key),
        })
        wrong_book[key] = _wrong_entries(slot)
        favorites[key] = list(slot.get("favorites") or [])
    for bid, rel in aliases.items():
        if not (BASE_DIR / rel).exists():
            continue
        slot = slots.get(rel) or {}
        banks.append({
            "id": bid,
            "name": Path(rel).stem,
            "groupName": "",
            "createdAt": "",
            "updatedAt": "",
            "questions": load_questions(rel),
        })
        wrong_book[bid] = _wrong_entries(slot)
        favorites[bid] = list(slot.get("favorites") or [])
    active = st.get("bank_path") or (banks[0]["id"] if banks else "")
    return {
        "schemaVersion": 1,
        "banks": banks,
        "activeBankId": active,
        "wrongBook": wrong_book,
        "favorites": favorites,
        "records": _merge_records(gui.get("records"), _history_records()),
        "settings": gui.get("settings") if isinstance(gui.get("settings"), dict) else {},
        "crossPlatformMeta": {"favoriteQuestions": {}},
    }


def apply_web_state(payload: dict) -> dict:
    """只回写 TUI 认识的字段：activeBankId / 错题 / 收藏；GUI 自己的设置与记录单独存。"""
    st = read_state()
    slots = st.setdefault("banks", {})
    changed = []
    raw_banks = payload.get("banks") or {}
    items = raw_banks.items() if isinstance(raw_banks, dict) else ((b.get("id"), b) for b in raw_banks)
    for key0, bank in items:
        key = bank.get("id") or key0
        if not key or key not in slots:
            continue
        slot = slots.setdefault(key, {})
        entries = (payload.get("wrongBook") or {}).get(key)
        if isinstance(entries, list):
            clean = [e for e in entries if isinstance(e, dict) and e.get("id")]
            slot["wrong"] = [str(e["id"]) for e in clean]
            slot["wrong_counts"] = {str(e["id"]): int(e.get("wrongCount") or 0) for e in clean}
            slot["right_counts"] = {str(e["id"]): int(e.get("rightCount") or 0) for e in clean}
            slot["wrong_status"] = {str(e["id"]): (e.get("status") or "未掌握") for e in clean}
            slot["wrong_last"] = {str(e["id"]): _epoch(e.get("lastWrongAt")) for e in clean}
            changed.append(key)
        fav = (payload.get("favorites") or {}).get(key)
        if isinstance(fav, list):
            slot["favorites"] = [str(x) for x in fav if x]
            changed.append(key)
    active = payload.get("activeBankId")
    if active in slots:
        st["bank_path"] = active
    gui = st.get("gui") if isinstance(st.get("gui"), dict) else {}
    aliases = gui.get("bank_alias") if isinstance(gui.get("bank_alias"), dict) else {}
    # GUI 里新导入的题库（带题目）落成 banks/*.json，并记下 GUI id 到文件名的别名
    for bank in payload.get("banks") or []:
        bid = bank.get("id")
        questions = bank.get("questions")
        if not bid or bid in slots or not isinstance(questions, list) or not questions:
            continue
        rel = aliases.get(bid)
        path = (BASE_DIR / rel) if rel else _safe_bank_path(bank.get("name"))
        data = _web_questions_to_tui(questions)
        if not data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        rel = path.relative_to(BASE_DIR).as_posix()
        aliases[bid] = rel
        slots.setdefault(rel, {})
        if not st.get("bank_path"):
            st["bank_path"] = bid
    gui = dict(_gui_section(st))
    gui["settings"] = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    gui["records"] = payload.get("records") if isinstance(payload.get("records"), list) else []
    gui["bank_alias"] = aliases
    st["gui"] = gui
    st.setdefault("version", 2)
    atomic_write_json(STATE_FILE, st)
    return {"ok": True, "changed": sorted(set(changed))}



# ---------- 间隔复习（FSRS-6）：与 TUI 共用 state.banks[*].srs / srs_day / srs_log ----------

def _srs_settings() -> dict:
    from core import config as appcfg
    from core import srs

    try:
        cfg = dict(appcfg.load().get("srs") or {})
    except Exception:
        cfg = {}
    raw_steps = cfg.get("steps") or [1, 10]
    steps = tuple(float(m) * 60.0 for m in raw_steps if float(m) > 0) or srs.STEPS_DEFAULT
    return {
        "new_per_day": max(0, int(cfg.get("new_per_day", 20) or 0)),
        "review_per_day": max(0, int(cfg.get("review_per_day", 200) or 0)),
        "steps": steps,
        "relearn": steps[-1],
        "leech": max(1, int(cfg.get("leech", 8) or 8)),
        "day_start": max(0, min(23, int(cfg.get("day_start", 4) or 0))),
        "fuzz": max(0.0, min(0.5, float(cfg.get("fuzz", 0.05) or 0.0))),
        "learn_ahead": max(0.0, float(cfg.get("learn_ahead", 20) or 0.0)) * 60.0,
    }


def _srs_bank():
    st = read_state()
    key = st.get("bank_path") or ""
    slot = (st.get("banks") or {}).get(key) or {}
    if not isinstance(slot, dict):
        slot = {}
    return st, key, slot


def _srs_today(slot: dict, cfg: dict, now=None) -> dict:
    from core import srs

    now = time.time() if now is None else now
    today = srs.day_key(now, cfg["day_start"])
    day = slot.get("srs_day") if isinstance(slot.get("srs_day"), dict) else {}
    if str(day.get("date") or "") != today:
        day = {"date": today, "new": 0, "review": 0}
    return day


def _srs_counters(questions, cards, now) -> dict:
    from core import srs

    new = due = learning = review = paused = 0
    next_due = 0.0
    for q in questions:
        card = cards.get(q.id)
        if not isinstance(card, dict) or str(card.get("state") or "new") == "new":
            new += 1
            continue
        if card.get("leech"):
            paused += 1
            continue
        stt = str(card.get("state") or "")
        if stt in ("learning", "relearning"):
            learning += 1
        elif stt == "review":
            review += 1
        if srs.due_now(card, now):
            due += 1
        else:
            d = float(card.get("due", 0) or 0)
            if d and (not next_due or d < next_due):
                next_due = d
    return {"new": new, "due": due, "learning": learning, "review": review,
            "paused": paused, "nextDue": next_due}


def srs_summary() -> dict:
    from core import srs

    cfg = _srs_settings()
    st, key, slot = _srs_bank()
    questions = load_questions(key) if key else []
    cards = slot.get("srs") if isinstance(slot.get("srs"), dict) else {}
    now = time.time()
    day = _srs_today(slot, cfg, now)
    c = _srs_counters(questions, cards, now)
    return {
        "ok": True,
        "bankId": key,
        "total": len(questions),
        "cards": len(cards),
        "new": c["new"],
        "due": c["due"],
        "learning": c["learning"],
        "review": c["review"],
        "paused": c["paused"],
        "todayNew": int(day.get("new", 0) or 0),
        "todayReview": int(day.get("review", 0) or 0),
        "limits": {"newPerDay": cfg["new_per_day"], "reviewPerDay": cfg["review_per_day"],
                   "leech": cfg["leech"]},
        "nextDue": _iso(c["nextDue"]) if c["nextDue"] else "",
        "dayStart": day.get("date"),
    }


def _q_item(q, is_new, card) -> dict:
    from core import srs

    now = time.time()
    options = []
    for o in (getattr(q, "options", None) or []):
        if isinstance(o, dict):
            options.append({"key": str(o.get("key") or ""), "text": str(o.get("text") or "")})
        else:
            options.append({"key": str(getattr(o, "key", "") or ""), "text": str(getattr(o, "text", "") or "")})
    return {
        "id": q.id,
        "number": getattr(q, "number", ""),
        "type": getattr(q, "type", "") or "",
        "question": getattr(q, "question", ""),
        "options": options,
        "answer": [str(x) for x in (getattr(q, "answer", None) or [])],
        "analysis": getattr(q, "analysis", "") or "",
        "category": getattr(q, "category", "") or "",
        "isNew": bool(is_new),
        "card": {
            "state": srs.human_state(card) if card else "新卡",
            "interval": srs.human_interval(card, now) if card else "现在",
            "reps": int(card.get("reps", 0) or 0) if card else 0,
        },
    }


def srs_queue(limit: int = 20) -> dict:
    from core import srs

    cfg = _srs_settings()
    st, key, slot = _srs_bank()
    if not key:
        return {"ok": False, "error": "还没有选择题库"}
    questions = load_questions(key)
    if not questions:
        return {"ok": False, "error": "当前题库没有题目"}
    cards = slot.get("srs") if isinstance(slot.get("srs"), dict) else {}
    now = time.time()
    day = _srs_today(slot, cfg, now)
    rem_new = max(0, cfg["new_per_day"] - int(day.get("new", 0) or 0))
    rem_rev = max(0, cfg["review_per_day"] - int(day.get("review", 0) or 0))
    raw = srs.build_queue(cards, questions, now, new_limit=rem_new,
                          review_limit=rem_rev, learn_ahead=cfg["learn_ahead"])
    by_id = {q.id: q for q in questions}
    items = []
    for qid, is_new in raw[: max(1, int(limit))]:
        q = by_id.get(qid)
        if q is None:
            continue
        items.append(_q_item(q, is_new, cards.get(qid)))
    return {"ok": True, "bankId": key, "items": items, "summary": srs_summary(),
            "remaining": len(raw)}


def srs_preview(qid: str) -> dict:
    from core import srs

    cfg = _srs_settings()
    st, key, slot = _srs_bank()
    questions = load_questions(key) if key else []
    q = next((x for x in questions if x.id == qid), None)
    if q is None:
        return {"ok": False, "error": "题目不在当前题库"}
    cards = slot.get("srs") if isinstance(slot.get("srs"), dict) else {}
    now = time.time()
    base = cards.get(qid) or srs.new_card(now)
    ratings = {}
    for r in (1, 2, 3, 4):
        c = srs.review(base, r, now=now, steps=cfg["steps"], relearn=cfg["relearn"],
                       leech=cfg["leech"], fuzz=cfg["fuzz"])
        ratings[str(r)] = {"interval": srs.human_interval(c, now),
                           "state": srs.human_state(c)}
    return {"ok": True, "ratings": ratings}


def srs_apply_review(qid: str, rating: int) -> dict:
    from core import srs

    rating = int(rating)
    if rating not in (1, 2, 3, 4):
        return {"ok": False, "error": "rating 必须是 1..4"}
    cfg = _srs_settings()
    with _STATE_LOCK:
        st, key, slot = _srs_bank()
        if not key:
            return {"ok": False, "error": "还没有选择题库"}
        questions = load_questions(key)
        q = next((x for x in questions if x.id == qid), None)
        if q is None:
            return {"ok": False, "error": "题目不在当前题库"}
        slots = st.setdefault("banks", {})
        slot = slots.get(key)
        if not isinstance(slot, dict):
            slot = slots[key] = {}
        cards = slot.get("srs")
        if not isinstance(cards, dict):
            cards = slot["srs"] = {}
        now = time.time()
        day = _srs_today(slot, cfg, now)
        old = cards.get(qid)
        is_new = str((old or {}).get("state") or "new") == "new"
        card = srs.review(old or srs.new_card(now), rating, now=now, steps=cfg["steps"],
                          relearn=cfg["relearn"], leech=cfg["leech"], fuzz=cfg["fuzz"])
        cards[qid] = card
        bucket = "new" if is_new else "review"
        day[bucket] = int(day.get(bucket, 0) or 0) + 1
        slot["srs_day"] = day
        log = slot.get("srs_log")
        if not isinstance(log, list):
            log = slot["srs_log"] = []
        log.append([int(now), qid, rating])
        if len(log) > 5000:
            del log[:-5000]
        atomic_write_json(STATE_FILE, st)
    return {
        "ok": True,
        "card": {
            "state": srs.human_state(card),
            "interval": srs.human_interval(card, now),
            "leech": bool(card.get("leech")),
            "stability": round(float(card.get("s") or 0), 2),
            "difficulty": round(float(card.get("d") or 0), 2),
            "reps": int(card.get("reps", 0) or 0),
            "lapses": int(card.get("lapses", 0) or 0),
        },
        "day": day,
        "summary": srs_summary(),
    }


def _dav_url(endpoint: str, rel: str, trailing: bool = False) -> str:
    base = str(endpoint or "").strip()
    if not base:
        raise ValueError("empty endpoint")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https"):
        raise ValueError("endpoint must be http(s)")
    segments = [urllib.parse.quote(s, safe="") for s in str(rel or "").replace("\\", "/").split("/") if s]
    path = parts.path.rstrip("/") + "/" + "/".join(segments)
    if trailing and segments:
        path += "/"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


_SYNC_LOCK = threading.Lock()


def _sync_settings():
    """增量同步沿用终端版的云配置，保证网页版和终端版记同一份同步状态。"""
    try:
        from core import config as app_config
        cloud = dict((app_config.load() or {}).get("cloud") or {})
    except Exception:
        cloud = {}
    return {
        "url": str(cloud.get("url") or "").strip(),
        "user": str(cloud.get("user") or "").strip(),
        "remote": str(cloud.get("remote_dir") or "quiz_py").strip("/"),
        "ignore": list(cloud.get("ignore") or []),
    }


def _sync_password():
    try:
        from core import secret as _secret
        return _secret.load_password(WEBDAV_SECRET) or ""
    except Exception:
        return ""


def _sync_ready(settings, password):
    if not settings["url"]:
        return "还没有云地址：请先在「云设置」里填写 WebDAV 地址。"
    if not password:
        return "没有可用的云密码：请先在「云设置」里保存密码。"
    return ""


def _sync_client(settings, password):
    from core.webdav import WebDAVClient
    return WebDAVClient(settings["url"], settings["user"], password)


def _sync_local_map(settings):
    from core import cloudsync
    return cloudsync.collect_local(BANKS_DIR, STATE_FILE, HISTORY_FILE,
                                   ignore=settings.get("ignore"))


def _sync_cache_path():
    return SYNC_CACHE_FILE


def _sync_info():
    settings = _sync_settings()
    password = _sync_password()
    cache = {}
    try:
        cache = json.loads(_sync_cache_path().read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    files = dict(cache.get("files") or {})
    device = ""
    try:
        from core import cloudsync
        device = cloudsync.device_id()
    except Exception:
        device = ""
    last_sync = 0
    try:
        last_sync = int(cache.get("last_sync") or 0)
    except Exception:
        last_sync = 0
    last_text = ""
    if last_sync:
        try:
            last_text = datetime.fromtimestamp(last_sync).isoformat(timespec="seconds")
        except Exception:
            last_text = ""
    return {
        "ok": True,
        "configured": not bool(_sync_ready(settings, password)),
        "problem": _sync_ready(settings, password),
        "url": settings["url"],
        "user": settings["user"],
        "remote": settings["remote"],
        "hasPassword": bool(password),
        "device": device,
        "knownFiles": len(files),
        "knownDeleted": len(dict(cache.get("deleted") or {})),
        "lastSync": last_text,
        "manifestUpdated": cache.get("manifest_updated") or "",
    }


def _sync_run(action, payload):
    if action not in ("plan", "push", "pull"):
        return {"ok": False, "error": "未知操作：%s" % action}
    settings = _sync_settings()
    password = _sync_password()
    problem = _sync_ready(settings, password)
    if problem:
        return {"ok": False, "error": problem, "configured": False}
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "同步已经在进行中，请稍候再试。"}
    try:
        from core import cloudsync
        policy = "skip" if str(payload.get("policy") or "").strip().lower() == "skip" else "overwrite"
        client = _sync_client(settings, password)
        if action == "plan":
            local = _sync_local_map(settings)
            result = cloudsync.plan(client, settings["remote"], local, cache_path=_sync_cache_path())
            return {"ok": True, "action": "plan", "plan": result, "policy": policy}
        if action == "pull":
            stats = cloudsync.pull(
                client, settings["remote"], BANKS_DIR, STATE_FILE, HISTORY_FILE,
                cache_path=_sync_cache_path(),
                log_path=DATA_DIR / "cloud_sync.log",
                policy=policy,
                trash_dir=BANKS_DIR.parent / "backups" / "cloud-deleted")
            return {"ok": True, "action": "pull", "stats": stats, "policy": policy}
        local = _sync_local_map(settings)
        stats = cloudsync.push(
            client, settings["remote"], local,
            cache_path=_sync_cache_path(),
            log_path=DATA_DIR / "cloud_sync.log",
            force=True, policy=policy, data_dir=DATA_DIR)
        return {"ok": True, "action": "push", "stats": stats, "policy": policy}
    except Exception as exc:
        _log_write("error", "sync %s failed" % action, {"error": str(exc)})
        return {"ok": False, "error": str(exc)}
    finally:
        _SYNC_LOCK.release()


def _dav_proxy(payload: dict) -> dict:
    endpoint = str(payload.get("endpoint") or "")
    method = str(payload.get("method") or "GET").upper()
    url = _dav_url(endpoint, str(payload.get("path") or ""), bool(payload.get("trailingSlash")))
    headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
    clean = {str(k): str(v) for k, v in headers.items() if len(str(k)) < 100 and len(str(v)) < 8192}
    raw = None
    if payload.get("bodyBase64"):
        raw = base64.b64decode(str(payload["bodyBase64"]))
    elif payload.get("bodyText") is not None:
        raw = str(payload["bodyText"]).encode("utf-8")
    try:
        timeout = float(payload.get("timeoutMs") or 30000) / 1000.0
    except (TypeError, ValueError):
        timeout = 30.0
    timeout = max(1.0, min(timeout, 180.0))
    req = urllib.request.Request(url, data=raw, method=method, headers=clean)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            resp_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read() or b""
        status = exc.code
        resp_headers = dict(exc.headers.items()) if exc.headers else {}
    return {
        "status": status,
        "headers": resp_headers,
        "bodyBase64": base64.b64encode(body).decode("ascii"),
    }


# ================= 局域网访问 / 可选访问口令 =================
# 默认仍然只听 127.0.0.1；只有显式 --lan / --host <非回环地址> 才暴露到局域网。
_LOOPBACK_HOSTS = {"", "127.0.0.1", "localhost", "::1"}
AUTH_COOKIE = "quiz_gui_key"          # 口令通过后种的 Cookie 名
AUTH_MAX_AGE = 30 * 24 * 60 * 60      # Cookie 有效期 30 天
TOKEN_PARAM = "k"                     # 首次访问用 ?k=<口令> 换 Cookie

# 401 页面：中文说明 + 怎么拿到口令（不泄露口令本身）
_AUTH_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>需要访问口令</title>
<style>
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
      font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#222}
 .card{max-width:30rem;padding:1.6rem 1.8rem;background:#fff;border-radius:12px;
       box-shadow:0 6px 24px rgba(0,0,0,.08)}
 h1{margin:0 0 .8rem;font-size:1.25rem}
 p{margin:.55rem 0;line-height:1.65;font-size:.95rem;color:#444}
 code{padding:.1rem .35rem;background:#eef1f5;border-radius:4px;font-size:.9em;word-break:break-all}
</style></head>
<body><div class="card">
<h1>🔒 需要访问口令</h1>
<p>这个题库页面启用了访问口令（启动参数 <code>--token</code>），当前请求没有通过校验。</p>
<p>正确链接形如：<code>http://&lt;本机IP&gt;:&lt;端口&gt;/?k=&lt;口令&gt;</code></p>
<p>打开一次后浏览器会记住口令（约 30 天），也可以直接问开启服务的人要口令。</p>
</div></body></html>
"""


def _is_loopback_host(host: str) -> bool:
    """判断监听地址是否只对本机可见（决定要不要打印局域网提示）。"""
    h = (host or "").strip().lower()
    if h in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _lan_ipv4_addresses() -> list:
    """枚举本机可能的局域网 IPv4 地址（纯标准库，不引第三方依赖）。

    两个来源取并集去重：
      1) UDP「连一下」默认路由地址：不会真的发包，只让内核选出出口网卡的地址；
      2) gethostbyname_ex(hostname)：补上多网卡机器上其余地址。
    过滤回环 / 0.0.0.0 / 169.254.x 这类不可达地址，私有网段排前面，
    默认路由那张网卡排最前（打印时会标记，一般选它）。
    注意：纯标准库拿不到网卡名字，VMware / VirtualBox 的虚拟网卡可能一并列出，
    所以只做排序和标记，不猜名字瞎过滤，避免误删真正的无线网卡。
    """
    found = []

    def _add(ip):
        ip = (ip or "").strip()
        if ip and ip not in found:
            found.append(ip)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.2)
            # 挑一个通常不在本网段的地址做路由选择；UDP connect 不产生流量
            for probe in ("8.8.8.8", "192.168.255.255"):
                try:
                    sock.connect((probe, 80))
                    _add(sock.getsockname()[0])
                    break
                except OSError:
                    continue
        finally:
            sock.close()
    except OSError:
        pass

    try:
        _name, _aliases, addrs = socket.gethostbyname_ex(socket.gethostname())
        for ip in addrs:
            _add(ip)
    except OSError:
        pass

    def _usable(ip):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return not (addr.is_loopback or addr.is_unspecified or addr.is_link_local)

    def _rank(ip):
        if found and ip == found[0]:
            return 0                      # 默认出口网卡
        try:
            if ipaddress.ip_address(ip).is_private:
                return 1                  # 10./172.16-31./192.168.
        except ValueError:
            pass
        return 2

    return sorted((ip for ip in found if _usable(ip)), key=_rank)


def _firewall_hint(port: int) -> str:
    """生成可复制的 Windows 防火墙放行命令（只打印，绝不自动执行）。"""
    return (
        "netsh advfirewall firewall add rule "
        f'name="Shiroha Quiz GUI {port}" dir=in action=allow protocol=TCP localport={port}'
    )


class _Handler(SimpleHTTPRequestHandler):
    server_version = "QuizGUI/1.0"
    auth_token = ""  # 空串 = 不校验；由 _make_handler() 注入，类属性避免改父类构造签名

    def guess_type(self, path):
        suffix = Path(path).suffix.lower()
        return _MIME_OVERRIDE.get(suffix) or super().guess_type(path)

    def end_headers(self):
        # 统一禁止浏览器猜测 MIME（不影响下面已有的 Content-Type / 缓存逻辑）
        self.send_header("X-Content-Type-Options", "nosniff")
        # 静态资源同样禁止浏览器缓存：便携盘符变化或前端更新后，
        # 不会再出现“服务端已更新、浏览器仍拿旧副本”的情况。
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    # ---------------- 访问口令 ----------------

    def _cookie_token(self) -> str:
        """从 Cookie 里取口令（取不到返回空串）。"""
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == AUTH_COOKIE:
                return urllib.parse.unquote(value)
        return ""

    def _discard_body(self, limit: int = 256 * 1024):
        """401 之前把请求体读掉一部分：否则客户端还在写 body 就可能收到连接重置，
        浏览器/XHR 看到的是“网络错误”而不是 401。只读有限字节，不陪着超大 body 耗流量。"""
        try:
            remaining = min(int(self.headers.get("Content-Length") or 0), limit)
        except (TypeError, ValueError):
            return
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 16 * 1024))
            if not chunk:
                return
            remaining -= len(chunk)

    def _send_auth_page(self, status: int = 401):
        """返回 401 中文提示页（未带口令 / 口令不正确都走这里）。"""
        self._discard_body()
        body = _AUTH_PAGE.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _gate(self) -> bool:
        """口令闸门。True=放行；False=已经写回 302/401，调用方直接 return 即可。

        - 没设口令（auth_token 为空）：全部放行，行为与旧版一致；
        - ?k=<正确口令>：种 HttpOnly Cookie 并 302 去掉 k 参数
          （不让口令留在地址栏 / 浏览器历史 / 被人转发的链接里）；
        - Cookie 里口令正确：放行；
        - 其余情况（含 k 写错）：401，不再继续处理。
        """
        token = self.auth_token
        if not token:
            return True
        parsed = urllib.parse.urlparse(self.path)
        supplied = (urllib.parse.parse_qs(parsed.query).get(TOKEN_PARAM) or [""])[0]
        want = token.encode("utf-8")
        if supplied:
            if hmac.compare_digest(supplied.encode("utf-8"), want):
                rest = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                        if k != TOKEN_PARAM]
                location = parsed.path or "/"
                if rest:
                    location += "?" + urllib.parse.urlencode(rest, doseq=True)
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header(
                    "Set-Cookie",
                    f"{AUTH_COOKIE}={urllib.parse.quote(token, safe='')}; Path=/; "
                    f"HttpOnly; SameSite=Lax; Max-Age={AUTH_MAX_AGE}",
                )
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return False
            # 明确带了 k 但不对：按需求直接 401，不提示具体错在哪
            self._send_auth_page(401)
            return False
        if hmac.compare_digest(self._cookie_token().encode("utf-8"), want):
            return True
        self._send_auth_page(401)
        return False

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json({"ok": True, "version": "gui-1"})
            return True
        if path == "/api/banks" and method == "GET":
            self._json({"banks": list_banks()})
            return True
        if path == "/api/state" and method == "GET":
            self._json(build_web_state())
            return True
        if path == "/api/state" and method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 64 * 1024 * 1024))
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception as exc:
                self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
                return True
            try:
                self._json(apply_web_state(payload))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return True
        if path == "/api/log" and method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 256 * 1024))
                payload = json.loads(raw.decode("utf-8") or "{}")
                lvl = str(payload.get("level") or "info")[:10]
                msg = str(payload.get("msg") or "")[:2000]
                ctx = payload.get("ctx")
                if not isinstance(ctx, dict):
                    ctx = {"raw": str(ctx)[:500]} if ctx else None
                _log_write(lvl, msg, ctx)
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return True
        if path == "/api/log" and method == "GET":
            tail = []
            try:
                if LOG_FILE.exists():
                    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
                    tail = lines[-80:]
            except Exception:
                pass
            self._json({"ok": True, "path": str(LOG_FILE), "lines": tail})
            return True
        if path == "/api/kv" and method == "GET":
            self._json(_read_kv())
            return True
        if path == "/api/kv" and method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 8 * 1024 * 1024))
                kv = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(kv, dict):
                    raise ValueError("kv must be an object")
                _write_kv({str(k): str(v) for k, v in kv.items()})
                self._json({"ok": True, "keys": len(kv)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return True
        if path == "/api/srs/summary" and method == "GET":
            self._json(srs_summary())
            return True
        if path == "/api/srs/queue" and method == "GET":
            qs = urllib.parse.parse_qs(parsed.query or "")
            try:
                limit = int((qs.get("limit") or ["20"])[0] or 20)
            except ValueError:
                limit = 20
            try:
                self._json(srs_queue(limit))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return True
        if path == "/api/srs/preview" and method == "GET":
            qs = urllib.parse.parse_qs(parsed.query or "")
            qid = str((qs.get("id") or [""])[0] or "")
            if not qid:
                self._json({"ok": False, "error": "missing id"}, 400)
            else:
                self._json(srs_preview(qid))
            return True
        if path == "/api/srs/review" and method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 64 * 1024))
                payload = json.loads(raw.decode("utf-8") or "{}")
                qid = str(payload.get("id") or "")
                rating = int(payload.get("rating") or 0)
            except Exception as exc:
                self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
                return True
            try:
                self._json(srs_apply_review(qid, rating))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return True
        if path == "/api/builtin":
            meta = list_banks()
            if method == "POST":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    payload = json.loads(self.rfile.read(min(length, 64 * 1024)).decode("utf-8") or "{}")
                    key = str(payload.get("key") or "")
                    keys = {item["key"] for item in meta}
                    if key not in keys:
                        raise ValueError("unknown bank key")
                    from core import config as app_config
                    cfg = app_config.load()
                    cfg.setdefault("gui", {})["builtin_bank"] = key
                    app_config.save(cfg)
                    self._json({"ok": True, "builtin": key})
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                return True
            if not meta:
                self._json({"ok": False, "error": "banks/ 目录为空"}, 404)
                return True
            keys = {item["key"] for item in meta}
            try:
                from core import config as app_config
                configured = str((app_config.load().get("gui") or {}).get("builtin_bank") or "")
            except Exception:
                configured = ""
            active = str(read_state().get("bank_path") or "")
            pick = None
            for candidate in (configured, active):
                if candidate and candidate in keys:
                    pick = next(i for i in meta if i["key"] == candidate)
                    break
            if pick is None:
                pick = next((i for i in meta if "01_" in Path(i["key"]).name), None)
            if pick is None:
                pick = meta[0]
            self._json({"ok": True, "id": pick["key"],
                        "name": pick.get("name") or Path(pick["key"]).stem,
                        "questions": load_questions(pick["key"]),
                        "banks": [{"key": i["key"], "name": i.get("name") or Path(i["key"]).stem} for i in meta]})
            return True
        if path == "/api/webdav/password":
            try:
                from core import secret as _secret
                if method == "GET":
                    mode = _secret.secret_status(WEBDAV_SECRET) or ""
                    if mode == "missing":
                        mode = ""
                    value = _secret.load_password(WEBDAV_SECRET) if mode else ""
                    self._json({"ok": True, "has": bool(mode), "mode": mode,
                                "password": value or ""})
                    return True
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 64 * 1024))
                payload = json.loads(raw.decode("utf-8") or "{}")
                if payload.get("clear"):
                    _secret.clear_password(WEBDAV_SECRET)
                    self._json({"ok": True, "cleared": True})
                else:
                    pwd = str(payload.get("password") or "")
                    if not pwd:
                        raise ValueError("empty password")
                    # 沿用 TUI 已选的保存方式（dpapi / plain），避免把便携的明文改成机器绑定
                    _mode = _secret.secret_status(WEBDAV_SECRET) or ""
                    _secret.save_password(WEBDAV_SECRET, pwd, mode=("plain" if _mode == "plain" else "dpapi"))
                    self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return True
        if path == "/api/webdav/proxy" and method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 96 * 1024 * 1024))
                payload = json.loads(raw.decode("utf-8") or "{}")
                result = _dav_proxy(payload)
                _log_write("info", "webdav proxy", {"method": payload.get("method"),
                                                    "status": result.get("status")})
                self._json(result)
            except Exception as exc:
                _log_write("error", "webdav proxy failed", {"error": str(exc)})
                self._json({"ok": False, "error": str(exc)}, 502)
            return True
        if path == "/api/sync/info" and method == "GET":
            try:
                self._json(_sync_info())
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return True
        if path.startswith("/api/sync/") and method == "POST":
            action = path[len("/api/sync/"):].strip("/")
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(length, 256 * 1024)) if length else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                payload = {}
            result = _sync_run(action, payload)
            code = 200 if result.get("ok") else (409 if result.get("error", "").startswith("同步已经在") else 400)
            self._json(result, code)
            return True
        if path.startswith("/api/bank/") and method == "GET":
            key = urllib.parse.unquote(path[len("/api/bank/"):])
            questions = load_questions(key)
            if not questions:
                self._json({"ok": False, "error": "bank not found or empty"}, 404)
            else:
                self._json({"ok": True, "key": key, "questions": questions})
            return True
        return False

    def do_GET(self):
        if not self._gate():
            return
        if self.path.split("?")[0] in ("/review", "/review/"):
            self.path = "/review.html"
        if self.path.startswith("/api/") and self._api("GET"):
            return
        super().do_GET()

    def do_HEAD(self):
        # 静态资源也支持 HEAD，口令同样要过；未放行时 _gate() 已写好响应头
        if not self._gate():
            return
        super().do_HEAD()

    def do_POST(self):
        if not self._gate():
            return
        if self.path.startswith("/api/") and self._api("POST"):
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


def _make_handler(token: str):
    """按口令生成 handler 类。用类属性注入，避免改 SimpleHTTPRequestHandler 的构造签名。"""
    class _TokenHandler(_Handler):
        auth_token = token

    return _TokenHandler


def _build_server(port: int = 0, host: str = "127.0.0.1", token: str = ""):
    """创建（但不启动）HTTP 服务；单独抽出来方便自测拿到真实端口。"""
    handler = partial(_make_handler((token or "").strip()), directory=str(WEB_DIR))
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd


def serve(port: int = 0, host: str = "127.0.0.1", open_browser: bool = True, token: str = ""):
    token = (token or "").strip()
    httpd = _build_server(port, host, token)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"🌐 GUI 已启动：{url}")
    print("   数据目录：", BASE_DIR)
    print("   关闭窗口或按 Ctrl+C 结束。")

    # 只有真的暴露到局域网时才多打提示；只听 127.0.0.1 时输出与旧版完全一致
    if not _is_loopback_host(host):
        key_suffix = f"?{TOKEN_PARAM}={urllib.parse.quote(token, safe='')}" if token else ""
        try:
            bound = str(ipaddress.ip_address(host)) if host.strip() != "0.0.0.0" else ""
        except ValueError:
            bound = ""
        ips = _lan_ipv4_addresses()
        if bound:
            ips = [bound] + [ip for ip in ips if ip != bound]
        print("📡 局域网地址（手机需与本机连同一 WiFi）：")
        if not ips:
            print("   （没找到可用的局域网 IPv4，确认已连 WiFi 或网线）")
        for idx, ip in enumerate(ips):
            if bound:
                mark = "  ← --host 指定的地址" if ip == bound else ""
            else:
                mark = "  ← 默认网卡，一般选这个" if idx == 0 else ""
            print(f"   http://{ip}:{actual_port}/{key_suffix}{mark}")
        if token:
            print("🔒 已启用访问口令：带 ?k=… 的链接打开一次即可，之后靠 Cookie（约 30 天）放行。")
        else:
            print("⚠️  未设口令：同一网络内任何人都能打开本页。要限制请加 --token <字符串>。")
        # 只打印、绝不自动执行：改防火墙是用户的决定
        print("🧱 若手机打不开，多半是被防火墙拦了。管理员 PowerShell 里跑一次这条（仅提示）：")
        print(f"   {_firewall_hint(actual_port)}")
    elif token:
        print("🔒 已启用访问口令（仅本机监听，口令意义不大，但行为保持一致）。")

    if open_browser:
        # 监听 0.0.0.0 / 指定网卡时，浏览器打不开这个地址，本机改用 127.0.0.1
        browse = url if _is_loopback_host(host) else f"http://127.0.0.1:{actual_port}/"
        if token:
            browse += f"?{TOKEN_PARAM}={urllib.parse.quote(token, safe='')}"
        threading.Timer(0.6, lambda: webbrowser.open(browse)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出 GUI。")
    finally:
        httpd.server_close()
