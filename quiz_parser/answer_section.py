# quiz_parser/answer_section.py
import re
from typing import Optional
from .models import ParsedAnswerEntry, QuestionType
from .answer_token import AnswerTokenParser

def parse_answer_section(text: str, default_type: Optional[QuestionType] = None) -> list[ParsedAnswerEntry]:
    if not text: return []
    entries = []
    
    # 按行严格匹配，不使用复杂正则以免卡死
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # 1. 表格格式：题号: 1 2 3 / 答案: A B C
    for i, line in enumerate(lines):
        if line.startswith("题号") and i + 1 < len(lines) and lines[i+1].startswith("答案"):
            nums = re.findall(r"\d+", line)
            ans_tokens = re.findall(r"[A-Ha-h]+", lines[i+1])
            for n, a in zip(nums, ans_tokens):
                entries.append(ParsedAnswerEntry(number=n, answer=AnswerTokenParser.parse_objective_answers(a), type=default_type))
            return entries

    # 2. 范围格式：1-5: A B A C D
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*[:：]\s*(.+)", text)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        tokens = re.findall(r"[A-Ha-h]+", m.group(3))
        for i, n in enumerate(range(start, end + 1)):
            if i < len(tokens):
                entries.append(ParsedAnswerEntry(number=str(n), answer=AnswerTokenParser.parse_objective_answers(tokens[i]), type=default_type))
        return entries

    # 3. 紧凑格式：1A2B3C4D
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"(?:\d{1,3}[A-Ha-h]+)+", compact):
        for m in re.finditer(r"(\d{1,3})([A-Ha-h]+)", compact):
            entries.append(ParsedAnswerEntry(number=m.group(1), answer=AnswerTokenParser.parse_objective_answers(m.group(2)), type=default_type))
        return entries

    # 4. 逐行：1.A / 1、A / 1 A
    for line in lines:
        m = re.match(r"^\s*(\d{1,3})\s*[.、．:：]?\s*([A-Ha-h]+)\s*$", line)
        if m:
            entries.append(ParsedAnswerEntry(number=m.group(1), answer=AnswerTokenParser.parse_objective_answers(m.group(2)), type=default_type))
            continue
        # 同行多个：1.A 2.B 3.C
        m_multi = re.finditer(r"(\d{1,3})\s*[.、．:：]?\s*([A-Ha-h]+)", line)
        if m_multi:
            for m in m_multi:
                entries.append(ParsedAnswerEntry(number=m.group(1), answer=AnswerTokenParser.parse_objective_answers(m.group(2)), type=default_type))
    
    return entries