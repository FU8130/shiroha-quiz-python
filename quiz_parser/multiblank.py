"""多空填空支持，对齐 Kotlin MultiBlankQuestionParser / MultiBlankSupport。"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .models import Question, QuestionType
from .code_guard import CodeLikeTextGuard

@dataclass
class MultiBlankResult:
    question_text: str
    answer: list[str]
    blank_answers: list[list[str]]
    warnings: list[str]

class MultiBlankSupport:
    _ROUND_BLANK = re.compile(r"(?<![A-Za-z0-9_])(?:\(\s*\)|（\s*）)")
    _UNDERLINE_BLANK = re.compile(r"_{3,}")

    @classmethod
    def count_explicit_blanks(cls, text: str) -> int:
        if not text: return 0
        return len(cls._ROUND_BLANK.findall(text)) + len(cls._UNDERLINE_BLANK.findall(text))

    @classmethod
    def compatibility_answer(cls, groups: list[list[str]]) -> list[str]:
        if not groups: return []
        primary = [g[0].strip() if g else "" for g in groups]
        if all(not p for p in primary): return []
        return ["；".join(primary)]

    @classmethod
    def split_reliable_parts(cls, raw: str, expected_count: int) -> Optional[list[str]]:
        if expected_count <= 1 or not raw.strip(): return None
        trimmed = raw.strip()
        lines = [l.strip() for l in trimmed.split("\n") if l.strip()]
        if len(lines) == expected_count: return lines

        for sep in [r"[；;]", r"[|｜]"]:
            parts = [p.strip() for p in re.split(sep, trimmed) if p.strip()]
            if len(parts) == expected_count: return parts

        if "/" in trimmed or "／" in trimmed:
            if not re.search(r"https?://|www\.", trimmed, re.IGNORECASE) and not re.search(r"\b\d{1,4}/\d{1,2}(?:/\d{1,4})?\b", trimmed) and not re.search(r"\b[A-Za-z]{1,8}\s*/\s*[A-Za-z]{1,8}\b", trimmed):
                parts = [p.strip() for p in re.split(r"[/／]", trimmed) if p.strip()]
                if len(parts) == expected_count: return parts
        return None

class MultiBlankQuestionParser:
    _INLINE_META = re.compile(r"(?:以下简称|主席令|年修订|第\d+号|批复|发文|文件|国发|国办发)")
    _INLINE_ANS_LIKE = re.compile(r"^(?:[A-Ha-h]{1,8}|对|错|正确|错误|是|否|√|✓|✔|☑|×|✗|✖|❌|True|False)$", re.IGNORECASE)

    @classmethod
    def extract(cls, stem: str, type: QuestionType, options: list, answer_text: str, normalized_answer: list[str]) -> MultiBlankResult:
        if type != QuestionType.BLANK:
            return MultiBlankResult(stem, normalized_answer, [], [])

        # 1. 提取内嵌括号和已填空
        parts = []
        groups = []
        warnings = []
        
        # 先匹配显式空括号
        round_matches = list(re.finditer(r"(?<![A-Za-z0-9_])(?:\(\s*\)|（\s*）)", stem))
        underline_matches = list(re.finditer(r"_{3,}", stem))
        
        all_matches = sorted(round_matches + underline_matches, key=lambda m: m.start())
        
        if len(all_matches) > 1:
            # 多空
            last_end = 0
            for m in all_matches:
                parts.append(stem[last_end:m.start()])
                parts.append("（  ）") # 统一替换为空括号
                groups.append([])
                last_end = m.end()
            parts.append(stem[last_end:])
            new_stem = "".join(parts)

            # 尝试用 legacy answer 填充分组
            raw_ans = normalized_answer[0] if normalized_answer else ""
            split_parts = MultiBlankSupport.split_reliable_parts(raw_ans, len(groups))
            if split_parts:
                groups = [[p] for p in split_parts]
                return MultiBlankResult(new_stem, MultiBlankSupport.compatibility_answer(groups), groups, warnings)
            else:
                warnings.append(f"检测到{len(groups)}个题空，答案数量无法对应，请人工核对")
                return MultiBlankResult(new_stem, normalized_answer, groups, warnings)
        return MultiBlankResult(stem, normalized_answer, [], [])
