"""代码片段保护，对齐 Kotlin CodeLikeTextGuard。

仅拦截高置信度的代码语法外形，避免函数调用、成员访问、字符串和注释
被题号、选项、括号答案或空括号规则误识别。
"""

from __future__ import annotations
import re


_EMPTY_PARENS = re.compile(r"[\(（]\s*[\)）]")
_DECIMAL = re.compile(r"^\s*\d+\.\d+(?:[fFdDlL])?(?=\s*(?:[+\-*/%<>=]|\.\d|$))")
_DOTTED_NUMERIC = re.compile(r"^\s*(?:\d{1,3}\.){2,}\d{1,4}(?=\s|$|[/:+\-*])")
_DIRECT_CALL = re.compile(
    r"^\s*(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|[A-Za-z_]\w*\s*\[[^\]]+])\s*\([^\r\n]*\)\s*(?:[;{]\s*)?$"
)
_CONTROL_CALL = re.compile(
    r"^\s*(?:if|while|for|switch|catch|assert|when)\s*\([^\r\n]*\)\s*(?:[;{]\s*)?$",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"^\s*(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|[A-Za-z_]\w*\s*\[[^\]]+])\s*"
    r"(?:=|\+=|-=|\*=|/=|%=|:=)\s*.+;?\s*$"
)
_MEMBER_ACCESS = re.compile(
    r"^\s*[A-Ha-h]\.[A-Za-z_]\w*(?:\([^\r\n]*?\))?"
    r"(?:\s*[,;]\s*[A-Ha-h]\.[A-Za-z_]\w*(?:\([^\r\n]*?\))?){1,}\s*$"
)
_TECH_ABBREV = re.compile(r"^[A-Z]{1,5}\s*[:：]\s*[+\-]?(?:\d+(?:\.\d+)?|\.\d+)")

_LEADING_IDENT = re.compile(r"^[A-Za-z_]\w*")


class CodeLikeTextGuard:
    # ── 公开接口 ──

    @classmethod
    def is_protected_parenthesized_token(
        cls, text: str, start: int, end: int, token: str,
    ) -> bool:
        if start >= end:
            return False
        if cls.is_index_in_string_or_comment(text, start):
            return True
        if cls._is_call_like_open_paren(text, start):
            return True
        return cls._is_mixed_case_choice_token(token)

    @classmethod
    def has_unprotected_empty_parentheses(cls, text: str) -> bool:
        for m in _EMPTY_PARENS.finditer(text):
            if not cls.is_protected_parenthesized_token(text, m.start(), m.end(), ""):
                return True
        return False

    @classmethod
    def looks_like_standalone_code_expression(cls, line: str) -> bool:
        t = line.strip()
        if not t:
            return False
        if cls._starts_with_comment(t):
            return True
        if cls.has_unprotected_empty_parentheses(t):
            return False
        if cls._contains_cjk(t):
            return False
        return bool(
            _DIRECT_CALL.match(t)
            or _CONTROL_CALL.match(t)
            or _ASSIGNMENT.match(t)
            or _MEMBER_ACCESS.match(t)
        )

    @classmethod
    def looks_like_numeric_code_or_data_line(cls, line: str) -> bool:
        t = line.strip()
        if cls._contains_cjk(t):
            return False
        return bool(_DECIMAL.search(t) or _DOTTED_NUMERIC.search(t))

    @classmethod
    def is_index_in_string_or_comment(cls, text: str, index: int) -> bool:
        if index < 0 or index >= len(text):
            return False
        for s, e in cls._protected_ranges(text):
            if s <= index < e:
                return True
        return False

    @classmethod
    def looks_like_leading_code_option(
        cls, line: str, marker_start: int, content_start: int,
    ) -> bool:
        if not (0 <= marker_start < len(line)) or not (0 <= content_start <= len(line)):
            return False
        if cls.is_index_in_string_or_comment(line, marker_start):
            return True
        if cls._is_embedded_technical_abbrev_marker(line, marker_start, content_start):
            return True

        marker_text = line[marker_start:content_start]
        marker_lead = marker_text.lstrip()[0:1] if marker_text.lstrip() else ""
        if (
            marker_lead in "([【〔〖《"
            and marker_start > 0
            and (cls._is_ascii_ident_part(line[marker_start - 1]) or line[marker_start - 1] in "])")
        ):
            return True

        tail = line[content_start:]
        trimmed = tail.lstrip()
        if trimmed.startswith(("->", "=>", "::", "=")):
            return True

        uses_dot = "." in marker_text or "．" in marker_text
        if not uses_dot or (tail and tail[0].isspace()):
            return False
        if _TECH_ABBREV.search(trimmed):
            return False

        m = _LEADING_IDENT.match(tail)
        if not m:
            return False
        after_idx = m.end()
        after = tail[after_idx] if after_idx < len(tail) else ""
        if after in ("(", "[", ".", "=", ":"):
            return True
        if "::" in tail or "->" in tail or "=>" in tail:
            return True
        if after in (",", ";"):
            rest = tail[after_idx + 1:]
            if re.search(r"\s*[A-Ha-h]\.[A-Za-z_]\w*", rest):
                return True
        return False

    @classmethod
    def looks_like_code_option_chunk(
        cls, line: str, marker_start: int, content_start: int, end_exclusive: int,
    ) -> bool:
        if not (0 <= marker_start < len(line)) or not (0 <= content_start <= len(line)):
            return False
        safe_end = max(content_start, min(end_exclusive, len(line)))
        marker_text = line[marker_start:content_start]
        raw_chunk = line[content_start:safe_end]
        if raw_chunk and raw_chunk[0].isspace():
            return False
        if "." not in marker_text and "．" not in marker_text:
            return False
        chunk = raw_chunk.strip()
        if _TECH_ABBREV.search(chunk):
            return False
        m = _LEADING_IDENT.match(chunk)
        if not m:
            return False
        after_idx = m.end()
        after = chunk[after_idx] if after_idx < len(chunk) else ""
        if after in ("(", "[", ".", "=", ":"):
            return True
        if "::" in chunk or "->" in chunk or "=>" in chunk:
            return True
        if (chunk.endswith(",") or chunk.endswith(";")) and m.end() + 1 == len(chunk):
            return True
        return False

    # ── 内部工具 ──

    @classmethod
    def _is_embedded_technical_abbrev_marker(
        cls, line: str, marker_start: int, content_start: int,
    ) -> bool:
        marker_text = line[marker_start:content_start]
        if ":" not in marker_text and "：" not in marker_text:
            return False
        if marker_start <= 0 or not ("A" <= line[marker_start - 1] <= "Z"):
            return False
        abbr_start = marker_start - 1
        while abbr_start > 0 and "A" <= line[abbr_start - 1] <= "Z":
            abbr_start -= 1
        abbr = line[abbr_start:marker_start + 1]
        if len(abbr) < 2 or len(abbr) > 5:
            return False
        value_tail = line[content_start:].lstrip()
        return bool(re.match(r"^[+\-]?(?:\d+(?:\.\d+)?|\.\d+)", value_tail))

    @classmethod
    def _is_call_like_open_paren(cls, text: str, open_index: int) -> bool:
        if open_index <= 0:
            return False
        immediate = text[open_index - 1]
        if cls._is_ascii_ident_part(immediate) or immediate in "])":
            return True
        if not immediate.isspace():
            return False
        token_end = open_index - 2
        while token_end >= 0 and text[token_end].isspace():
            token_end -= 1
        if token_end < 0 or not cls._is_ascii_ident_part(text[token_end]):
            return False
        token_start = token_end
        while token_start > 0 and cls._is_ascii_ident_part(text[token_start - 1]):
            token_start -= 1
        token = text[token_start:token_end + 1]
        prefix = text[:token_start].rstrip()
        if token.lower() in {"if", "while", "for", "switch", "catch", "assert", "when"}:
            return True
        if not prefix:
            return True
        return prefix[-1] in "= .([{,;:+-*/%!&|<>&"

    @classmethod
    def _is_mixed_case_choice_token(cls, token: str) -> bool:
        compact = re.sub(r"[\s,，、;；/\\]+", "", token or "")
        if not compact or not re.fullmatch(r"[A-Ha-h]+", compact):
            return False
        return any(c.isupper() for c in compact) and any(c.islower() for c in compact)

    @staticmethod
    def _starts_with_comment(text: str) -> bool:
        return text.startswith(("//", "#", "/*", "*/"))

    @classmethod
    def _protected_ranges(cls, text: str) -> list[tuple[int, int]]:
        """返回 [(start, end_exclusive), ...]，标记字符串/注释范围。"""
        ranges: list[tuple[int, int]] = []
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch == "/" and i + 1 < n and text[i + 1] == "/" and cls._is_comment_boundary(text, i):
                ranges.append((i, n))
                break
            if ch == "#" and cls._is_comment_boundary(text, i):
                ranges.append((i, n))
                break
            if ch == "/" and i + 1 < n and text[i + 1] == "*":
                end = text.find("*/", i + 2)
                close = (end + 2) if end >= 0 else n
                ranges.append((i, close))
                i = close
                continue
            if ch in ('"', "'", "`"):
                if ch == "'" and cls._is_apostrophe_inside_word(text, i):
                    i += 1
                    continue
                start = i
                i += 1
                escaping = False
                closed = False
                while i < n:
                    cur = text[i]
                    if escaping:
                        escaping = False
                    elif cur == "\\":
                        escaping = True
                    elif cur == ch:
                        ranges.append((start, i + 1))
                        i += 1
                        closed = True
                        break
                    i += 1
                if not closed:
                    ranges.append((start, n))
                continue
            i += 1
        return ranges

    @staticmethod
    def _is_comment_boundary(text: str, index: int) -> bool:
        if index == 0:
            return True
        prev = text[index - 1]
        return prev.isspace() or prev in ";{}()[]"

    @staticmethod
    def _is_apostrophe_inside_word(text: str, index: int) -> bool:
        if index <= 0 or index + 1 >= len(text):
            return False
        before, after = text[index - 1], text[index + 1]
        return CodeLikeTextGuard._is_ascii_ident_part(before) and CodeLikeTextGuard._is_ascii_ident_part(after)

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any("\u3400" <= c <= "\u9fff" for c in text)

    @staticmethod
    def _is_ascii_ident_part(c: str) -> bool:
        return c.isascii() and (c.isalnum() or c == "_")
