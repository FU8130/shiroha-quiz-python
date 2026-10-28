# -*- coding: utf-8 -*-
"""给 GUI 用的题库读取：复用 TUI 的 pickle 缓存，保证题目 id 与状态一致。"""
import hashlib
import json
import pickle
from pathlib import Path

from core.paths import CACHE_DIR, bank_abs_path
from quiz_parser.models import Option, Question, QuestionType
from quiz_parser.quiz_parser import QuizImportParser

_TYPE_TO_WEB = {
    QuestionType.SINGLE: "single",
    QuestionType.MULTIPLE: "multiple",
    QuestionType.JUDGE: "judge",
    QuestionType.BLANK: "blank",
    QuestionType.SHORT: "short",
}

_mem = {}


def read_text_auto(path_obj: Path) -> str:
    """与 TUI 相同的编码回退顺序。"""
    last = None
    data = Path(path_obj).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError as exc:
            last = exc
    raise last


def _cache_file(path_obj: Path) -> Path:
    stat = path_obj.stat()
    raw = f"{path_obj.name}_{stat.st_size}_{stat.st_mtime}".encode()
    return CACHE_DIR / f"{hashlib.md5(raw).hexdigest()}.pkl"


def _result_for(path_obj: Path):
    """优先读缓存；没有缓存就解析一次并写入同一缓存（与 TUI 共用）。"""
    cache_file = _cache_file(path_obj)
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass

    text = read_text_auto(path_obj)
    if path_obj.suffix.lower() == ".json":
        questions = _json_questions(text)
        result = type("R", (), {"questions": questions})()
    else:
        result = QuizImportParser.parse_standard_text(text)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "wb") as fh:
            pickle.dump(result, fh)
    except Exception:
        pass
    return result


def _json_questions(text: str):
    data = json.loads(text)
    items = data.get("questions") if isinstance(data, dict) else data
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        qtype = str(item.get("type") or "").lower()
        kind = {
            "single": QuestionType.SINGLE, "multiple": QuestionType.MULTIPLE,
            "judge": QuestionType.JUDGE, "blank": QuestionType.BLANK,
            "short": QuestionType.SHORT, "short_answer": QuestionType.SHORT,
        }.get(qtype, QuestionType.SHORT)
        options = []
        for i, opt in enumerate(item.get("options") or []):
            if isinstance(opt, str):
                options.append(Option(key=chr(65 + i), text=opt))
            elif isinstance(opt, dict):
                options.append(Option(key=str(opt.get("key") or chr(65 + i)),
                                      text=str(opt.get("text") or "")))
        answer = item.get("answer") or []
        if isinstance(answer, str):
            answer = [answer]
        out.append(Question(
            id=str(item.get("id") or __import__("uuid").uuid4()),
            number=str(item.get("number") or ""),
            type=kind,
            question=str(item.get("question") or item.get("title") or ""),
            options=options,
            answer=[str(a) for a in answer],
            blankAnswers=[list(map(str, g)) for g in (item.get("blankAnswers") or [])],
            analysis=str(item.get("analysis") or ""),
            category=str(item.get("category") or ""),
        ))
    return out


def _serialize(q) -> dict:
    return {
        "id": q.id,
        "number": q.number,
        "type": _TYPE_TO_WEB.get(q.type, "short"),
        "question": q.question,
        "options": [{"key": o.key, "text": o.text} for o in q.options],
        "answer": list(q.answer),
        "blankAnswers": [list(g) for g in q.blankAnswers],
        "analysis": q.analysis,
        "category": q.category,
    }


def load_questions(key: str):
    """按状态里的相对 key 取题目；文件不存在时返回空列表。"""
    path_obj = Path(bank_abs_path(key))
    if not path_obj.exists():
        return []
    stat = path_obj.stat()
    sig = (str(stat.st_mtime_ns), stat.st_size)
    hit = _mem.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        result = _result_for(path_obj)
    except Exception:
        return []
    out = [_serialize(q) for q in (result.questions or [])]
    _mem[key] = (sig, out)
    return out
