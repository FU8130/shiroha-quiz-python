# quiz_parser/compact.py
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .base import QuestionImageMarker
from .code_guard import CodeLikeTextGuard

_INLINE_ANSWER = re.compile(r"\S\s+(?:[【\[]?\s*(?:答案|正确答案|参考答案|标准答案)\s*[:：])")
_INLINE_ANALYSIS = re.compile(r"\S\s+(?:[【\[]?\s*(?:解析|答案解析|说明)\s*[:：])")
# 加入了中文逗号
_PUNCT_MARKER = re.compile(r"([A-Ha-h])\s*[.、．:：)），,]")
_BRACKET_MARKER = re.compile(r"[\(（\[【〔〖《]\s*([A-Ha-h])\s*[\)）\]】〕〗》]")

_ABBR_TAIL_PUNCT = set(",，;；:：)）]】}》/\\")

@dataclass
class _OptionMarker:
    key: str
    marker_start: int
    content_start: int
    joined_inside_ascii_word: bool = False

@dataclass
class _ProtectedText:
    text: str
    replacements: dict[str, str]

class CompactQuestionRepair:
    @classmethod
    def has_compact_pattern(cls, raw: str) -> bool:
        if not raw or not raw.strip(): return False
        for raw_line in raw.split("\n"):
            line = raw_line.strip()
            if len(line) < 4: continue
            if cls._find_best_compact_option_run(cls._protect_image_markers(line).text) is not None or _INLINE_ANSWER.search(line) or _INLINE_ANALYSIS.search(line):
                return True
        return False

    @classmethod
    def has_compact_option_sequence(cls, line: str) -> bool:
        if not line or not line.strip(): return False
        return cls._find_best_compact_option_run(cls._protect_image_markers(line.strip()).text) is not None

    @classmethod
    def is_standard_option_line(cls, line: str) -> bool:
        normalized = line.lstrip() if line else ""
        if not normalized: return False
        marker = cls._find_leading_marker(normalized)
        if marker is None: return False
        return not cls._looks_like_dotted_abbreviation(normalized, marker) and not CodeLikeTextGuard.looks_like_leading_code_option(normalized, marker.marker_start, marker.content_start)

    @classmethod
    def repair(cls, raw: str) -> str:
        if not raw or not raw.strip(): return raw
        if not cls.has_compact_pattern(raw): return raw
        lines_out = []
        for line in raw.split("\n"):
            lines_out.extend(cls._repair_line(line).split("\n"))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines_out)).strip()

    @classmethod
    def _repair_line(cls, raw_line: str) -> str:
        original = raw_line.rstrip()
        if not original: return original
        protected = cls._protect_image_markers(original)
        run = cls._find_best_compact_option_run(protected.text)
        repaired = protected.text if run is None else cls._split_by_option_run(protected.text, run)
        repaired = re.sub(r"[ \t]+([【\[]?\s*(?:答案|正确答案|参考答案|标准答案)\s*[:：])", r"\n\1", repaired)
        repaired = re.sub(r"[ \t]+([【\[]?\s*(?:解析|答案解析|说明)\s*[:：])", r"\n\1", repaired)
        return cls._restore_image_markers(repaired, protected)

    @staticmethod
    def _split_by_option_run(line: str, markers: list[_OptionMarker]) -> str:
        pieces = []
        prefix = line[:markers[0].marker_start].strip()
        if prefix: pieces.append(prefix)
        for idx, marker in enumerate(markers):
            end = markers[idx + 1].marker_start if idx + 1 < len(markers) else len(line)
            chunk = line[marker.marker_start:end].strip()
            if chunk: pieces.append(chunk)
        return "\n".join(pieces)

    @classmethod
    def _find_best_compact_option_run(cls, line: str) -> Optional[list[_OptionMarker]]:
        candidates = cls._find_candidate_markers(line)
        if len(candidates) < 2: return None
        runs = []
        for start_i in range(len(candidates)):
            run = [candidates[start_i]]
            expected = cls._key_index(candidates[start_i].key) + 1
            cursor = start_i + 1
            while cursor < len(candidates) and 1 <= expected <= 7:
                cand = candidates[cursor]
                idx = cls._key_index(cand.key)
                if idx == expected:
                    run.append(cand); expected += 1; cursor += 1
                else: break
            if cls._is_valid_compact_run(line, run): runs.append(run)
        if not runs: return None
        runs.sort(key=lambda r: (-len(r), 0 if r[0].key.upper() != "A" else -1, r[0].marker_start))
        return runs[0]

    @classmethod
    def _is_valid_compact_run(cls, line: str, run: list[_OptionMarker]) -> bool:
        if len(run) < 2: return False
        first = run[0]
        prefix = line[:first.marker_start].strip()
        if prefix and first.key.upper() != "A": return False
        if first.joined_inside_ascii_word: return False
        code_like = 0
        for marker in run:
            end = next((m.marker_start for m in run if m.marker_start > marker.marker_start), len(line))
            if CodeLikeTextGuard.looks_like_code_option_chunk(line, marker.marker_start, marker.content_start, end): code_like += 1
        if code_like >= 2: return False
        for idx, marker in enumerate(run):
            if marker.joined_inside_ascii_word and idx == 0: return False
            end = run[idx + 1].marker_start if idx + 1 < len(run) else len(line)
            content = line[marker.content_start:end].strip().strip(";；").strip()
            if not content: return False
        return True

    @classmethod
    def _find_candidate_markers(cls, line: str) -> list[_OptionMarker]:
        markers = []
        for m in _PUNCT_MARKER.finditer(line):
            key = m.group(1); start = m.start(1)
            marker = _OptionMarker(key=key, marker_start=start, content_start=m.end(), joined_inside_ascii_word=cls._is_joined_inside_ascii_word(line, start))
            if not CodeLikeTextGuard.is_index_in_string_or_comment(line, marker.marker_start) and cls._is_candidate_boundary_allowed(line, marker) and not cls._looks_like_dotted_abbreviation(line, marker) and not CodeLikeTextGuard.looks_like_leading_code_option(line, marker.marker_start, marker.content_start):
                markers.append(marker)
        for m in _BRACKET_MARKER.finditer(line):
            key = m.group(1)
            marker = _OptionMarker(key=key, marker_start=m.start(), content_start=m.end(), joined_inside_ascii_word=False)
            if not CodeLikeTextGuard.is_index_in_string_or_comment(line, marker.marker_start) and cls._is_candidate_boundary_allowed(line, marker) and not CodeLikeTextGuard.looks_like_leading_code_option(line, marker.marker_start, marker.content_start):
                markers.append(marker)
        seen = set(); result = []
        for m in sorted(markers, key=lambda x: x.marker_start):
            if (m.marker_start, m.key.upper()) not in seen:
                seen.add((m.marker_start, m.key.upper()))
                result.append(m)
        return result

    @classmethod
    def _find_leading_marker(cls, line: str) -> Optional[_OptionMarker]:
        for regex in (_PUNCT_MARKER, _BRACKET_MARKER):
            for m in regex.finditer(line):
                if m.start() != 0: continue
                key = m.group(1)
                return _OptionMarker(key=key, marker_start=0, content_start=m.end())
        return None

    @staticmethod
    def _is_candidate_boundary_allowed(line: str, marker: _OptionMarker) -> bool:
        if marker.marker_start == 0: return True
        prev = line[marker.marker_start - 1]
        if prev == "_": return False
        if prev.isdigit(): return marker.key.isupper()
        key_lower = marker.key.islower()
        if key_lower and prev.isascii() and prev.isalpha(): return False
        if prev.isascii() and prev.isalpha() and marker.key.isupper(): return True
        return True

    @staticmethod
    def _is_joined_inside_ascii_word(line: str, marker_start: int) -> bool:
        if marker_start == 0: return False
        prev = line[marker_start - 1]
        return prev.isascii() and prev.isalpha()

    @staticmethod
    def _looks_like_dotted_abbreviation(line: str, marker: _OptionMarker) -> bool:
        marker_text = line[marker.marker_start:marker.content_start]
        if "." not in marker_text and "．" not in marker_text: return False
        if CompactQuestionRepair._looks_like_technical_option_expression(line, marker): return False
        if marker.content_start >= len(line): return False
        nxt = line[marker.content_start]
        if not (nxt.isascii() and nxt.isalpha()): return False
        next_next = line[marker.content_start + 1] if marker.content_start + 1 < len(line) else ""
        if next_next in (".", "．"): return True
        if nxt.isupper() and (not next_next or next_next.isspace() or next_next in _ABBR_TAIL_PUNCT): return True
        return False

    @staticmethod
    def _looks_like_technical_option_expression(line: str, marker: _OptionMarker) -> bool:
        tail = line[marker.content_start:].strip()
        return bool(re.search(r"^[A-Z](?:/|[,，])\s*\S+", tail))

    @staticmethod
    def _protect_image_markers(line: str) -> _ProtectedText:
        ranges = QuestionImageMarker.ranges_in(line)
        if not ranges: return _ProtectedText(line, {})
        replacements = {}; parts = []; cursor = 0
        for idx, (s, e) in enumerate(ranges):
            if s < cursor: continue
            parts.append(line[cursor:s])
            token = f"@@SHIROHA_IMG_MARKER_{idx}@@"
            replacements[token] = line[s:e]
            parts.append(token)
            cursor = e
        if cursor < len(line): parts.append(line[cursor:])
        return _ProtectedText("".join(parts), replacements)

    @staticmethod
    def _restore_image_markers(text: str, protected: _ProtectedText) -> str:
        for token, marker in protected.replacements.items(): text = text.replace(token, marker)
        return text

    @staticmethod
    def _key_index(key: str) -> int:
        return ord(key.upper()) - ord("A")