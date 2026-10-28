"""章节范围解析。"""
import re
from .base import normalize_question_index

def normalize_chapter(raw: str) -> str:
    m = re.search(r"第\s*([一二三四五六七八九十百0-9]+)\s*章", raw)
    if not m: return ""
    token = m.group(1)
    num = normalize_question_index(token)
    return f"第{num}章" if num else f"第{token}章"
