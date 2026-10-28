"""基础依赖模块，对齐 Kotlin：
QuestionImageMarker / QuestionTextNormalizer / ParserUtils /
QuestionTypeLabelParser / SectionTitleParser。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import QuestionType


# ─────────────────── 1. QuestionImageMarker（仅文本标记识别） ───────────────────

class QuestionImageMarker:
    _COMPATIBLE = re.compile(
        r"(?:\[\s*){0,2}SHIROHA_IMAGE\s*:\s*(img_\d{4})(?:\s*]){0,2}"
        r"|(?:[【\[]\s*){1,2}SHIROHA_IMAGE\s*:\s*(img_\d{4})(?:\s*[】\]]){1,2}",
        re.IGNORECASE,
    )

    @classmethod
    def canonical(cls, image_id: str) -> str:
        return f"[[SHIROHA_IMAGE:{image_id.strip()}]]"

    @classmethod
    def marker_id(cls, raw: str) -> Optional[str]:
        m = cls._COMPATIBLE.search(raw)
        if not m:
            return None
        return next((g.strip() for g in m.groups() if g and g.strip()), None)

    @classmethod
    def canonicalize(cls, text: str) -> str:
        if not cls.contains(text):
            return text
        return cls._COMPATIBLE.sub(
            lambda m: cls.canonical(cls.marker_id(m.group(0)) or ""), text
        )

    @classmethod
    def contains(cls, text: str) -> bool:
        return bool(cls._COMPATIBLE.search(text or ""))

    @classmethod
    def ranges_in(cls, text: str) -> list[tuple[int, int]]:
        if not text:
            return []
        return [m.span() for m in cls._COMPATIBLE.finditer(text)]

    @classmethod
    def ids_in(cls, text: str) -> list[str]:
        if not text:
            return []
        seen, result = set(), []
        for m in cls._COMPATIBLE.finditer(text):
            mid = cls.marker_id(m.group(0))
            if mid and mid not in seen:
                seen.add(mid)
                result.append(mid)
        return result

    @classmethod
    def remove_all(cls, text: str) -> str:
        if not cls.contains(text):
            return text.strip()
        cleaned = cls._COMPATIBLE.sub("", text)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


# ─────────────────── 2. QuestionTextNormalizer ───────────────────

class QuestionTextNormalizer:
    _NOISE_PAGE = re.compile(r"^第\s*\d+\s*页\s*(?:共\s*\d+\s*页)?$")
    _NOISE_LONGNUM = re.compile(r"^-?\d{8,}$")
    _NOISE_SECRET = re.compile(r"^(?:绝密|请勿外传|忽略此处\.\.)$")
    _PROFILE_HEADER = re.compile(
        r"^.*?(?:姓名|单位|岗位|班级|部门)\s*[:：]\s*"
        r"(?=(?:第\s*)?\d{1,4}\s*(?:题)?\s*[.、．:：)）])"
    )

    @classmethod
    def normalize(cls, raw: str) -> str:
        if not raw or not raw.strip():
            return ""
        text = raw
        text = text.replace("\uFEFF", "").replace("\uFE0F", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\u3000", " ")
        text = cls._normalize_fullwidth(text)
        for src, dst in (
            ("（", "("), ("）", ")"), ("：", ":"), ("．", "."),
            ("，", ","), ("；", ";"), ("【", "["), ("】", "]"),
            ("✔", "√"), ("✅", "√"), ("☑", "√"),
            ("✘", "×"), ("✖", "×"), ("❌", "×"), ("❎", "×"),
        ):
            text = text.replace(src, dst)

        lines = []
        for line in text.split("\n"):
            stripped = line.rstrip()
            stripped = cls._PROFILE_HEADER.sub("", stripped).lstrip()
            if cls._is_noise(stripped.strip()):
                continue
            lines.append(stripped)

        joined = "\n".join(lines)
        joined = re.sub(r" {2,}", " ", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()

    @classmethod
    def _normalize_fullwidth(cls, text: str) -> str:
        out = []
        for ch in text:
            code = ord(ch)
            if code == 0x3000:
                out.append(" ")
            elif 0xFF01 <= code <= 0xFF5E:
                out.append(chr(code - 0xFEE0))
            else:
                out.append(ch)
        return "".join(out)

    @classmethod
    def _is_noise(cls, line: str) -> bool:
        if not line:
            return False
        return bool(
            cls._NOISE_PAGE.match(line)
            or cls._NOISE_LONGNUM.match(line)
            or cls._NOISE_SECRET.match(line)
        )


# ─────────────────── 3. ParserUtils ───────────────────

_DIGIT_MAP = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_BINARY_JUDGE_STRONG = re.compile(
    r"(判断|判定|正误|对错|是非|是否|能否|可否|正确与否|错误与否|对还是错|对不对|错不错|正确吗|错误吗)"
)
_BINARY_OPTION_CHOICE = re.compile(
    r"(下列|以下|哪(?:一)?(?:项|个|些|种|条)|选择|选出|应选|正确的是|错误的是|不正确的是|"
    r"不属于|属于|包括|不包括|符合|不符合|最佳|最合适|最恰当)"
)
_BINARY_JUDGE_LOOSE = re.compile(r"(判断|正确|错误|对错|是非|是否|正误|√|✓|✔|☑|×|✗|✖)")

_JUDGE_OPTION_TEXT = {
    "正确", "错误", "对", "错", "是", "否",
    "√", "✓", "✔", "☑", "×", "✗", "✖", "❌",
    "True", "False", "true", "false",
}


def normalize_question_index(raw: str) -> str:
    clean = raw.strip()
    if clean.isdigit():
        return clean
    n = chinese_number_to_int(clean)
    return str(n) if n is not None else ""


def chinese_number_to_int(raw: str) -> Optional[int]:
    if not raw or not raw.strip():
        return None
    normalized = raw.strip().replace("零", "").replace("〇", "")
    if not normalized:
        return 0
    if "百" in normalized:
        parts = normalized.split("百", 1)
        hundreds = _DIGIT_MAP.get(parts[0][0], 1) if parts[0] else 1
        tail = parts[1] if len(parts) > 1 else ""
        return hundreds * 100 + (chinese_number_to_int(tail) or 0)
    if "十" in normalized:
        parts = normalized.split("十", 1)
        tens = _DIGIT_MAP.get(parts[0][0], 1) if parts[0] else 1
        ones = _DIGIT_MAP.get(parts[1][0], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return _DIGIT_MAP.get(normalized[0])


def is_judge_option_pair(option_keys: list[str], option_texts: list[str]) -> bool:
    return (
        [k.upper() for k in option_keys] == ["A", "B"]
        and all(t.strip() in _JUDGE_OPTION_TEXT for t in option_texts)
    )


def should_infer_judge_from_binary_options(stem: str, answer_text: str = "") -> bool:
    clean = stem.strip()
    if _BINARY_JUDGE_STRONG.search(clean):
        return True
    if _BINARY_OPTION_CHOICE.search(clean):
        return False
    return bool(_BINARY_JUDGE_LOOSE.search(clean + answer_text))


# ─────────────────── 4. QuestionTypeLabelParser ───────────────────

@dataclass
class LeadingTypeLabel:
    type: QuestionType
    label: str
    remainder: str


class QuestionTypeLabelParser:
    _WRAPPERS = [("【", "】"), ("[", "]"), ("（", "）"), ("(", ")"),
                 ("〔", "〕"), ("〖", "〗"), ("《", "》")]

    _TYPE_ALIASES: list[tuple[list[str], QuestionType]] = [
        (["单项选择题", "单选题", "选择题", "单项选择", "单选"], QuestionType.SINGLE),
        (["不定项选择题", "多项选择题", "多选题", "不定项选择", "多项选择", "多选"], QuestionType.MULTIPLE),
        (["判断题", "是非题", "对错题", "判断", "是非", "对错"], QuestionType.JUDGE),
        (["填空题", "补全题", "填空", "补全"], QuestionType.BLANK),
        ([
            "结构化面试题", "公考面试题", "公务员面试题", "材料分析题", "案例分析题",
            "名词解释", "论述题", "简答题", "问答题", "面试题", "综合题",
            "结构化面试", "公考面试", "公务员面试", "材料分析", "案例分析",
            "论述", "简答", "问答", "面试", "综合",
        ], QuestionType.SHORT),
    ]

    _ALIASES_BY_LEN: list[tuple[str, QuestionType]] = sorted(
        [(alias, qt) for aliases, qt in _TYPE_ALIASES for alias in aliases],
        key=lambda x: -len(x[0]),
    )

    _FOLLOW_ALLOWED = set(":：-－—、.．(（[【〔〖《")

    @classmethod
    def parse_label(cls, raw: str) -> Optional[QuestionType]:
        label = cls._unwrap(raw).strip().rstrip(":：")
        for alias, qt in cls._ALIASES_BY_LEN:
            if label == alias:
                return qt
        return None

    @classmethod
    def extract_leading(cls, raw: str) -> Optional[LeadingTypeLabel]:
        text = raw.lstrip()
        if not text:
            return None

        for open_w, close_w in cls._WRAPPERS:
            if text.startswith(open_w):
                end = text.find(close_w, len(open_w))
                if end > len(open_w):
                    label = text[len(open_w):end].strip()
                    qt = cls.parse_label(label)
                    if qt is not None:
                        remainder = cls._clean_leading_remainder(text[end + len(close_w):])
                        return LeadingTypeLabel(type=qt, label=label, remainder=remainder)

        for alias, qt in cls._ALIASES_BY_LEN:
            if text.startswith(alias):
                nxt = text[len(alias)] if len(text) > len(alias) else None
                if nxt is None or nxt.isspace() or nxt in cls._FOLLOW_ALLOWED:
                    remainder = cls._clean_leading_remainder(text[len(alias):])
                    return LeadingTypeLabel(type=qt, label=alias, remainder=remainder)
        return None

    @classmethod
    def has_leading(cls, raw: str) -> bool:
        return cls.extract_leading(raw) is not None

    @classmethod
    def _unwrap(cls, raw: str) -> str:
        text = raw.strip()
        for open_w, close_w in cls._WRAPPERS:
            if text.startswith(open_w) and text.endswith(close_w) and len(text) > len(open_w) + len(close_w):
                return text[len(open_w):-len(close_w)].strip()
        return text

    @classmethod
    def _clean_leading_remainder(cls, raw: str) -> str:
        return raw.lstrip().lstrip(":：-－—").lstrip()


# ─────────────────── 5. SectionTitleParser ───────────────────

@dataclass
class SectionInfo:
    title: str
    forced_type: Optional[QuestionType] = None
    is_answer_section: bool = False


class SectionTitleParser:
    _CHINESE_INDEX = "一二三四五六七八九十百"
    _LEADING_INDEX = re.compile(
        rf"^\s*(?:第?[{_CHINESE_INDEX}][、.．]?|第?\d{{1,3}}[、.．]?|"
        rf"\(\s*[{_CHINESE_INDEX}]\s*\)|（\s*[{_CHINESE_INDEX}]\s*）)?\s*"
    )
    _ARABIC_NUMBERED_REMAINDER = re.compile(r"^\s*\d{1,4}\s*[.、．:：)）]\s*(.+)$")
    _SECTION_LIKE = re.compile(
        rf"^\s*(?:第[一二三四五六七八九十百0-9]+(?:部分|卷|章|节|模块)"
        rf"|[{_CHINESE_INDEX}]+[、.．]\s*(?:常识判断|言语理解|语言理解|数量关系|数学能力|数学运算|"
        rf"判断推理|图形推理|定义判断|类比推理|逻辑判断|资料分析|材料分析|综合知识|公共基础知识|"
        rf"专业知识|基础知识|安全知识|理论知识|综合能力|结构化面试|公考面试|公务员面试|面试真题).*)\s*$"
    )
    _NON_TYPE_SECTION_KEYWORD = re.compile(
        r"(部分|试卷|常识判断|言语理解|语言理解|数量关系|数学能力|数学运算|"
        r"判断推理|图形推理|定义判断|类比推理|逻辑判断|资料分析|材料分析|综合知识|"
        r"公共基础知识|专业知识|基础知识|安全知识|理论知识|综合能力|"
        r"结构化面试|公考面试|公务员面试|面试真题)"
    )
    _GENERIC_SECTION_HEADING = re.compile(
        rf"^\s*(?:[{_CHINESE_INDEX}]+|\d{{1,3}})[、.．]\s*(?:(?:边界|极端)|.*(?:测试区|样本|题库|格式|"
        rf"边界(?:测试|样本|用例|情况|场景)|极端(?:测试|样本|用例|情况|场景)|客观题|主观题|材料题|"
        rf"集中答案|AI\s*解析|AI\s*核对|功能测试).*)\s*$",
        re.IGNORECASE,
    )
    _ANSWER_SECTION = re.compile(
        r"(集中答案|集中解析|参考答案|标准答案|正确答案|答案(?:与|及)?解析|答案解析|"
        r"试题答案|答题要点|参考要点|参考思路|答题思路|作答思路|评分要点|答案区|解析区|答案部分)"
    )
    _EXACT_ANSWER_SECTION_TITLE = re.compile(
        rf"^\s*(?:[{_CHINESE_INDEX}]+|\d{{1,3}})?[、.．]?\s*(?:集中答案|集中解析|参考答案|标准答案|"
        rf"正确答案|答案(?:与|及)?解析|答案解析|试题答案|答题要点|参考要点|参考思路|答题思路|"
        rf"作答思路|评分要点|答案区|解析区|答案部分)\s*[:：]?\s*$"
    )
    _INLINE_ANALYSIS_LINE = re.compile(
        r"^\s*(?:(?:[\[【]\s*(?:答案解析|解题思路|解析思路|解题分析|参考解析|详解|分析|理由|解答|解析|说明)\s*[\]】]\s*)"
        r"|(?:(?:答案解析|解题思路|解析思路|解题分析|参考解析|详解|分析|理由|解答|解析|说明)\s*(?:[:：]|\s+)))\s*\S+"
    )
    _QUESTION_BLANK_MARKER = re.compile(r"[（(]\s*[)）]")
    _QUESTION_PROMPT_KEYWORD = re.compile(
        r"(?:[?？]|(?:下列|以下|哪[一项种个]|哪个|哪种|哪项|不正确|不属于|正确|错误|属于|包括|"
        r"主要|应当|应该|可以|能够|能否|是否|为什么|如何))"
    )

    @classmethod
    def parse(cls, raw_line: str) -> Optional[SectionInfo]:
        title = raw_line.strip()
        if not title or len(title) > 60:
            return None

        if cls._is_exact_answer_section_title(title):
            return SectionInfo(title=title, is_answer_section=True)
        if cls._looks_like_numbered_question_stem(title):
            return None
        if cls._GENERIC_SECTION_HEADING.match(title):
            return SectionInfo(title=title)
        if cls._INLINE_ANALYSIS_LINE.match(title):
            return None
        if cls._ANSWER_SECTION.search(title) and not cls._is_inline_answer_line(title):
            return SectionInfo(title=title, is_answer_section=True)
        if cls._looks_like_arabic_numbered_typed_question(title):
            return None

        simplified = cls._LEADING_INDEX.sub("", title)
        simplified = re.sub(r"[\s:：]+$", "", simplified)

        leading = QuestionTypeLabelParser.extract_leading(simplified)
        if leading is not None:
            if not leading.remainder or cls._looks_like_type_section_remainder(leading.remainder):
                return SectionInfo(title=title, forced_type=leading.type)
            return None

        qt = QuestionTypeLabelParser.parse_label(simplified)
        if qt is not None:
            return SectionInfo(title=title, forced_type=qt)
        if cls._SECTION_LIKE.match(title) and cls._NON_TYPE_SECTION_KEYWORD.search(title):
            return SectionInfo(title=title)
        return None

    @classmethod
    def _looks_like_numbered_question_stem(cls, title: str) -> bool:
        m = cls._ARABIC_NUMBERED_REMAINDER.match(title)
        rest = (m.group(1) or "").strip() if m else ""
        if not rest:
            return False
        if cls._looks_like_arabic_numbered_typed_question(title):
            return True
        if cls._QUESTION_BLANK_MARKER.search(rest):
            return True
        if cls._QUESTION_PROMPT_KEYWORD.search(rest) and not cls._looks_like_short_generic_section_title(rest):
            return True
        return False

    @classmethod
    def _looks_like_short_generic_section_title(cls, rest: str) -> bool:
        text = rest.strip().rstrip(":：")
        if len(text) > 16:
            return False
        return bool(re.match(
            rf"^(?:(?:边界|极端)|.*(?:测试区|样本|题库|格式|边界(?:测试|样本|用例|情况|场景)|"
            rf"极端(?:测试|样本|用例|情况|场景)|客观题|主观题|材料题|集中答案|AI\s*解析|AI\s*核对|功能测试).*)$",
            text, re.IGNORECASE,
        ))

    @classmethod
    def _looks_like_type_section_remainder(cls, remainder: str) -> bool:
        text = remainder.strip()
        if not text:
            return True
        if re.match(r"^[（(].*(?:题|小题|道|分|共|共计|每题|每小题|本题|本大题|本部分|满分).*[）)]$", text):
            return True
        if re.match(r"^(?:共|共计|每题|每小题|本题|本大题|本部分|以下|含|满分)", text):
            return True
        return bool(re.match(r"^(?:[，,、；;]\s*)?(?:共|共计|每题|每小题|本题|本大题|本部分|以下|含|满分)", text))

    @classmethod
    def _is_exact_answer_section_title(cls, title: str) -> bool:
        t = title.strip().strip("[]【】（）()").strip()
        return bool(cls._EXACT_ANSWER_SECTION_TITLE.match(t))

    @classmethod
    def _is_inline_answer_line(cls, title: str) -> bool:
        return bool(re.search(
            r"^\s*(?:[\[【]\s*)?(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|"
            r"答题思路|作答思路|评分要点|参考作答|答)(?:\s*[\]】])?\s*(?:[:：]|为|\s+)\s*\S+",
            title,
        ))

    @classmethod
    def _looks_like_arabic_numbered_typed_question(cls, title: str) -> bool:
        m = cls._ARABIC_NUMBERED_REMAINDER.match(title)
        rest = (m.group(1) or "") if m else ""
        return bool(rest) and QuestionTypeLabelParser.has_leading(rest)

    @classmethod
    def is_section_heading(cls, raw_line: str) -> bool:
        return cls.parse(raw_line) is not None

    @classmethod
    def forced_type_of(cls, raw_line: str) -> Optional[QuestionType]:
        info = cls.parse(raw_line)
        return info.forced_type if info else None

    @classmethod
    def is_answer_section_heading(cls, raw_line: str) -> bool:
        info = cls.parse(raw_line)
        return bool(info and info.is_answer_section)
