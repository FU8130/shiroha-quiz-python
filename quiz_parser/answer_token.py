"""答案 token 解析，对齐 Kotlin AnswerTokenParser。

关键规则：
- 选择题语义下 F 就是选项 F，不是 false。
- 判断题语义下 f/false/False 全部映射到「错误」。
- 支持：单字母、多字母、范围 A-D、全选、紧凑串 FH、
  分隔符 F,H / F H / F、H、全角 Ｈ。
"""

from __future__ import annotations

import re
from typing import Optional

ANSWER_LABEL_PATTERN = (
    r"答案|正确答案|参考答案|标准答案|参考要点|参考思路|"
    r"答题要点|答题思路|作答思路|评分要点|参考作答|答"
)
ANSWER_SEPARATOR_PATTERN = r"(?:\s*(?:[:：,，、.．;；]|为)\s*|\s+|(?=\s*[\(（]))"

_JUDGE_TRUE_RE = re.compile(r"^(正确|对|是|√|✓|✔|☑|true|t)$", re.IGNORECASE)
_JUDGE_FALSE_RE = re.compile(r"^(错误|错|否|×|✗|✖|❌|x|false|f)$", re.IGNORECASE)
_LEADING_CHOICE_RE = re.compile(
    r"^\s*([A-Ha-h]{1,8})(?=\s*(?:[.、．:：)）;；\]\}]|[\u4e00-\u9fa5]|$))"
)
_CHOICE_RANGE_RE = re.compile(
    r"^\s*([A-Ha-h])\s*(?:-|－|-|-|~|～|至|到)\s*([A-Ha-h])\s*$"
)
_ALL_CHOICE_RE = re.compile(r"^(?:全选|全部|全部选|以上全选|所有选项|全都选|都选)$")


class AnswerTokenParser:
    @staticmethod
    def is_objective_answer_text(raw: str) -> bool:
        value = AnswerTokenParser.cleanup(raw)
        if not value:
            return False
        if AnswerTokenParser.is_judge_answer_text(value):
            return True
        if AnswerTokenParser._parse_choice_range(value):
            return True
        if _ALL_CHOICE_RE.fullmatch(value):
            return True
        if AnswerTokenParser._parse_separated_choice_letters(value):
            return True
        if _LEADING_CHOICE_RE.search(value):
            return True
        compact = re.sub(r"[,，、;；/\\\s]+", "", value).upper()
        return bool(re.fullmatch(r"[A-H]{1,8}", compact))

    @staticmethod
    def is_judge_answer_text(raw: str) -> bool:
        value = AnswerTokenParser.cleanup(raw)
        if not value:
            return False
        if _JUDGE_TRUE_RE.fullmatch(value) or _JUDGE_FALSE_RE.fullmatch(value):
            return True
        return bool(re.fullmatch(
            r"[ABab]\s*[.、．:：)）]?\s*"
            r"(?:正确|错误|对|错|是|否|√|✓|✔|☑|×|✗|✖|❌|True|False)",
            value, re.IGNORECASE,
        ))

    @staticmethod
    def parse_judge_answer(raw: str) -> list[str]:
        value = AnswerTokenParser.cleanup(raw)
        if not value:
            return []
        if _JUDGE_TRUE_RE.fullmatch(value):
            return ["正确"]
        if _JUDGE_FALSE_RE.fullmatch(value):
            return ["错误"]
        upper = value.upper()
        if upper == "A":
            return ["正确"]
        if upper == "B":
            return ["错误"]
        m = re.fullmatch(
            r"([ABab])\s*[.、．:：)）]?\s*"
            r"(?:正确|错误|对|错|是|否|√|✓|✔|☑|×|✗|✖|❌|True|False)",
            value, re.IGNORECASE,
        )
        if m:
            key = m.group(1).upper()
            if key == "A":
                return ["正确"]
            if key == "B":
                return ["错误"]
        return []

    @staticmethod
    def parse_objective_answers(raw: str, available_option_keys: Optional[list[str]] = None) -> list[str]:
        value = AnswerTokenParser.cleanup(raw)
        if not value:
            return []
        avail: list[str] = []
        if available_option_keys:
            for k in available_option_keys:
                k_norm = str(k).strip().upper()
                if re.fullmatch(r"[A-H]", k_norm) and k_norm not in avail:
                    avail.append(k_norm)

        if re.fullmatch(r"[A-Ha-h]", value):
            return AnswerTokenParser._filter_by_available([value.upper()], avail)
        if _JUDGE_TRUE_RE.fullmatch(value):
            return ["A"]
        if _JUDGE_FALSE_RE.fullmatch(value):
            return ["B"]
        if _ALL_CHOICE_RE.fullmatch(value):
            return avail if avail else ["全选"]
        range_answers = AnswerTokenParser._parse_choice_range(value)
        if range_answers:
            return AnswerTokenParser._filter_by_available(range_answers, avail)
        separated = AnswerTokenParser._parse_separated_choice_letters(value)
        if separated:
            return AnswerTokenParser._filter_by_available(separated, avail)
        m = _LEADING_CHOICE_RE.search(value)
        if m:
            letters = m.group(1).upper()
            if re.fullmatch(r"[A-H]{1,8}", letters):
                return AnswerTokenParser._filter_by_available(list(dict.fromkeys(letters)), avail)
        compact = re.sub(r"[,，、;；/\\\s]+", "", value).upper()
        if re.fullmatch(r"[A-H]{1,8}", compact):
            return AnswerTokenParser._filter_by_available(list(dict.fromkeys(compact)), avail)
        tokens = [t.strip().upper() for t in re.split(r"[,，、;；/\\]+", value) if t.strip()]
        tokens = [t for t in tokens if re.fullmatch(r"[A-H]", t)]
        return AnswerTokenParser._filter_by_available(list(dict.fromkeys(tokens)), avail)

    @staticmethod
    def is_all_choice_answer_text(raw: str) -> bool:
        return bool(_ALL_CHOICE_RE.fullmatch(AnswerTokenParser.cleanup(raw)))

    @staticmethod
    def parse_text_answer(raw: str) -> list[str]:
        value = AnswerTokenParser.cleanup(raw)
        return [value] if value else []

    @staticmethod
    def cleanup(raw: str) -> str:
        value = raw.strip()
        value = AnswerTokenParser._strip_wrapping(value)
        value = re.sub(
            r"^\s*(?:本题)?(?:" + ANSWER_LABEL_PATTERN + r")(?:" + ANSWER_SEPARATOR_PATTERN + r")?",
            "", value,
        )
        value = re.sub(r"^\s*(?:应选|故选)\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"^\s*选\s*(?=[A-Ha-h](?:\b|[.、．:：)）;；,，]))", "", value)
        value = value.strip()
        value = AnswerTokenParser._strip_wrapping(value)
        return value.strip()

    @staticmethod
    def _strip_wrapping(value: str) -> str:
        pairs = [("[[", "]]"), ("【", "】"), ("[", "]"), ("（", "）"), ("(", ")")]
        changed = True
        while changed:
            changed = False
            for left, right in pairs:
                if value.startswith(left) and value.endswith(right) and len(value) >= len(left) + len(right):
                    value = value[len(left): -len(right)]
                    changed = True
                    break
        return value.strip()

    @staticmethod
    def _parse_choice_range(value: str) -> list[str]:
        m = _CHOICE_RANGE_RE.fullmatch(value)
        if not m:
            return []
        start, end = m.group(1).upper(), m.group(2).upper()
        if end < start:
            return []
        return [chr(c) for c in range(ord(start), ord(end) + 1)]

    @staticmethod
    def _parse_separated_choice_letters(value: str) -> list[str]:
        if not re.fullmatch(
            r"[A-Ha-h](?:\s*[,，、;；/\\]\s*[A-Ha-h]|\s+[A-Ha-h]){1,7}", value
        ):
            return []
        tokens = [t.strip().upper() for t in re.split(r"[,，、;；/\\\s]+", value) if t.strip()]
        tokens = [t for t in tokens if re.fullmatch(r"[A-H]", t)]
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _filter_by_available(answers: list[str], available: list[str]) -> list[str]:
        if not answers:
            return []
        if not available:
            return answers
        result: list[str] = []
        for a in answers:
            if a in available and a not in result:
                result.append(a)
        return result
