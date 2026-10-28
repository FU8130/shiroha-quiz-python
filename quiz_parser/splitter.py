"""题块切分，对齐 Kotlin QuestionBlockSplitter。"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .models import QuestionType
from .base import QuestionImageMarker, QuestionTypeLabelParser, SectionTitleParser, normalize_question_index
from .compact import CompactQuestionRepair
from .code_guard import CodeLikeTextGuard

@dataclass
class QuestionBlock:
    number: str
    lines: list[str]
    category: str = ""
    forced_type: Optional[QuestionType] = None
    sequence: int = 0
    number_generated: bool = False

@dataclass
class ParsedQuestionStart:
    number: str
    remainder: str
    forced_type: Optional[QuestionType] = None

class QuestionBlockSplitter:
    _STRICT_QS = re.compile(r"^\s*(?:第\s*)?(\d{1,4})\s*(?:题)?\s*[.、．:：)）]\s*(.*)$")
    _BRACKET_QS = re.compile(r"^\s*[【\[]\s*(\d{1,4})\s*[】\]]\s*(.*)$")
    _INTERVIEW_QS = re.compile(r"^\s*(?:(?:问题|题目)\s*([一二三四五六七八九十百0-9]{1,4})|第\s*([一二三四五六七八九十百0-9]{1,4})\s*(?:题|问|道题|个问题)|([一二三四五六七八九十百]+)\s*(?:、|．|\.))\s*[.、．:：)）]?\s*(.*)$")
    _SPACED_QS = re.compile(r"^\s*(\d{1,3})\s+(.+)$")
    _GLUED_QS = re.compile(r"^\s*(\d{1,2})(?=[\u4e00-\u9fa5A-Za-z])(.*)$")

    _ANSWER_LINE = re.compile(r"^\s*(?:[\[【]\s*)?(?:本题)?(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答|答)(?:\s*[\]】])?\s*(?:[:：]|为)?")
    _SUBJ_MARKER_WITH_TAIL = re.compile(r"^\s*(?:(?:[\[【]\s*(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答|答)\s*[\]】]\s*)|(?:(?:本题)?(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答|答)\s*(?:[:：]|为)\s*))(.*)$")
    _BARE_SUBJ_MARKER = re.compile(r"^\s*(?:本题)?(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答|答)\s*$")
    _ANALYSIS_LINE = re.compile(r"^\s*(?:(?:[\[【]\s*(?:答案解析|解题思路|解析思路|解题分析|参考解析|详解|分析|理由|解答|解析|说明)\s*[\]】]\s*)|(?:(?:答案解析|解题思路|解析思路|解题分析|参考解析|详解|分析|理由|解答|解析|说明)\s*[:：]\s*))")
    _EMBEDDED_ANSWER = re.compile(r"[\[【]\s*(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答)\s*(?:[:：]|[\]】])|(?:本题)?(?:答案|正确答案|参考答案|标准答案)\s*为")
    _SUBJ_QUESTION_TYPE = re.compile(r"(?:[【\[（(〔〖《]\s*)?(?:简答题|问答题|面试题|结构化面试题|公考面试题|公务员面试题|材料分析题|案例分析题|名词解释|论述题|综合题)(?:\s*[】\]）)〕〗》])?")
    _SUBJ_CONT_MARKER = re.compile(r"^\s*(?:参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答)\s*[:：]?\s*$")
    _SUBJ_QUESTION_CUE = re.compile(r"(?:请)?(?:简述|简答|论述|阐述|概括|分析|说明|解释|谈谈|指出|列举|试述|为什么|如何|有何|哪些|什么是|提出.{0,12}(?:措施|建议|对策)|说明.{0,12}(?:原因|意义|作用|原则|内容))")
    _SUBJ_ANSWER_INTRO = re.compile(r"(?:如下|以下|主要包括|包括以下|可概括为|分为以下|有以下|要点|措施|原则|原因|意义|作用)\s*[:：]?$")
    _NUMBERED_SUBJ_ITEM = re.compile(r"^\s*(?:(\d{1,2})\s*[.、．:：)）]|[（(]\s*(\d{1,2})\s*[)）])\s*(.+)$")
    _CHINESE_SUBJ_ITEM = re.compile(r"^\s*(?:[一二三四五六七八九十]+\s*[、.．:：)）]|(?:首先|其次|再次|最后|第一|第二|第三|第四|第五|一是|二是|三是|四是|五是))")
    _MATERIAL_INTRO_LINE = re.compile(r"^\s*(?:[一二三四五六七八九十0-9]+[、.．:：]\s*)?根据(?:以下|下列|上述|给定)?(?:资料|材料|图表|统计资料).*回答\s*\d{1,4}\s*[~～\-—至到]\s*\d{1,4}\s*题\s*[。.:：]?\s*$")
    _STANDALONE_NUMERIC = re.compile(r"^\s*[+-]?\d+(?:\s*[.．]\s*\d+)?(?:[Ee][+-]?\d+)?\s*$", re.IGNORECASE)
    _UNNUMBERED_OBJ_MARKER = re.compile(r"[（(]\s*(?:([A-Ha-h]{1,8})|(对|错|正确|错误|√|✓|✔|☑|×|✗|✖|❌|True|False))\s*[)）]", re.IGNORECASE)
    _SHORT_OBJ_ANS_REM = re.compile(r"^\s*(?:[\[【(（]\s*)?(?:[A-Ha-h]{1,8}|对|错|正确|错误|是|否|√|✓|✔|☑|×|✗|✖|❌|True|False)(?:\s*[\]】)）])?\s*[.。]?\s*$", re.IGNORECASE)
    _INLINE_ANS_MARKER = re.compile(r"(?:本题)?(?:答案|正确答案|参考答案|标准答案)\s*(?:[:：]|为)")
    _FILL_BLANK_CUE = re.compile(r"_{2,}|＿{2,}|[（(]\s*(?:_{1,}|＿+|填空|空白)\s*[)）]")
    _JUDGE_CUE = re.compile(r"[（(]\s*(?:对|错|正确|错误|√|✓|✔|☑|×|✗|✖|❌|True|False)\s*[)）]", re.IGNORECASE)
    _PURE_FRONT_MATTER = re.compile(r"^(?:[【\[]?\s*)?(?:绝密|密卷|注意事项(?:\s*[:：].*)?|说明\s*[:：]\s*(?:请|考试|答题|作答|时间|考生).*|请(?:认真|仔细)作答|请在规定时间内完成(?:答题|作答)|请将答案(?:填写|填涂|写在|写到).*|请用\s*2B.*|请勿.*|答题前.*|答题卡.*|考试时间\s*[:：].*|时间\s*[:：].*|在考试结束.*|考试结束.*|全部测验到此结束.*|祝各位考生.*|监考老师.*)(?:\s*[】\]])?\s*[。.!！]?$", re.IGNORECASE)

    @classmethod
    def split(cls, text: str, forced_type: Optional[QuestionType] = None, category: str = "", allow_unnumbered: bool = True) -> list[QuestionBlock]:
        blocks = []
        current_number = None
        current_lines = []
        current_category = category
        current_section_forced_type = forced_type
        current_forced_type = forced_type
        current_number_generated = False
        synthetic_number = 0
        sequence = 0
        skipping_global_answer_section = False
        skipping_material_intro = False
        last_completed_explicit_number = None

        def flush():
            nonlocal current_number, current_lines, current_forced_type, current_number_generated, sequence, last_completed_explicit_number
            if current_number is None: return
            clean_lines = [l.strip() for l in current_lines if l.strip()]
            if clean_lines:
                blocks.append(QuestionBlock(
                    number=current_number, lines=clean_lines, category=current_category,
                    forced_type=current_forced_type, sequence=sequence, number_generated=current_number_generated
                ))
                sequence += 1
                if not current_number_generated:
                    base_num = current_number.split("-")[0]
                    if base_num.isdigit():
                        last_completed_explicit_number = int(base_num)
            current_number = None
            current_lines = []
            current_forced_type = current_section_forced_type
            current_number_generated = False

        source_lines = text.split("\n")
        for line_idx, raw_line in enumerate(source_lines):
            line = raw_line.strip()
            if not line: continue
            if current_number is None and cls._is_pure_front_matter(line): continue

            if cls._is_material_intro(line):
                flush()
                skipping_material_intro = True
                continue

            if current_number is not None and cls._should_attach_subj_ans_marker(current_lines, line, current_forced_type):
                current_lines.append(line)
                skipping_material_intro = False
                continue

            if skipping_global_answer_section:
                section = SectionTitleParser.parse(line)
                if section:
                    if section.is_answer_section:
                        skipping_material_intro = False
                        continue
                    flush()
                    current_category = section.title or category
                    current_section_forced_type = section.forced_type or forced_type
                    current_forced_type = current_section_forced_type
                    skipping_global_answer_section = False
                    skipping_material_intro = False
                    continue
                restart = cls._parse_question_start(line)
                if restart is None or not cls._should_resume_after_global_ans(source_lines, line_idx, restart, last_completed_explicit_number):
                    continue
                skipping_global_answer_section = False
                skipping_material_intro = False

            section = SectionTitleParser.parse(line)
            if section:
                if section.is_answer_section:
                    flush()
                    skipping_global_answer_section = True
                    skipping_material_intro = False
                    continue
                flush()
                current_category = section.title or category
                current_section_forced_type = section.forced_type or forced_type
                current_forced_type = current_section_forced_type
                skipping_global_answer_section = False
                skipping_material_intro = False
                continue

            if current_number is not None and cls._should_keep_as_subj_ans_cont(current_lines, line, current_number, current_forced_type, source_lines, line_idx):
                current_lines.append(line)
                continue
            if current_number is not None and cls._should_keep_as_analysis_cont(current_lines, line, source_lines, line_idx):
                current_lines.append(line)
                continue

            explicit_start = cls._parse_question_start(line)
            if explicit_start:
                flush()
                skipping_material_intro = False
                current_number = explicit_start.number
                current_number_generated = False
                current_forced_type = explicit_start.forced_type or current_section_forced_type
                if explicit_start.remainder.strip(): current_lines = [explicit_start.remainder.strip()]
                else: current_lines = []
                continue

            if current_number is None:
                if skipping_material_intro: continue
                if allow_unnumbered and (cls._is_likely_unnumbered_q(line) or cls._is_likely_typed_q(line, forced_type)):
                    synthetic_number += 1
                    current_number = str(synthetic_number)
                    current_number_generated = True
                    typed = QuestionTypeLabelParser.extract_leading(line)
                    current_forced_type = typed.type if typed else current_section_forced_type
                    current_lines.append(typed.remainder if typed and typed.remainder else line)
                continue

            if allow_unnumbered and cls._should_start_next_synthetic(current_lines, line):
                parent_num = current_number
                flush()
                synthetic_number += 1
                current_number = cls._synthetic_q_number(parent_num, synthetic_number)
                current_number_generated = True
                typed = QuestionTypeLabelParser.extract_leading(line)
                current_forced_type = typed.type if typed else current_section_forced_type
                current_lines.append(typed.remainder if typed and typed.remainder else line)
            else:
                current_lines.append(line)

        flush()
        return cls._normalize_generated_q_numbers(blocks)

    @classmethod
    def _parse_question_start(cls, line: str) -> Optional[ParsedQuestionStart]:
        if cls._is_standalone_numeric_table_value(line): return None
        if CodeLikeTextGuard.looks_like_numeric_code_or_data_line(line): return None

        m = cls._BRACKET_QS.search(line)
        if m:
            typed = QuestionTypeLabelParser.extract_leading(m.group(2))
            return ParsedQuestionStart(m.group(1), typed.remainder if typed else m.group(2), typed.type if typed else None)

        m = cls._INTERVIEW_QS.search(line)
        if m:
            raw_num = next((g for g in [m.group(1), m.group(2), m.group(3)] if g), "")
            num = normalize_question_index(raw_num)
            rest = m.group(4).strip()
            is_chinese_ordinal = bool(m.group(3))
            if num and (not is_chinese_ordinal or cls._looks_like_interview_rem(rest)):
                typed = QuestionTypeLabelParser.extract_leading(rest)
                return ParsedQuestionStart(num, typed.remainder if typed else rest, typed.type if typed else None)

        m = cls._STRICT_QS.search(line)
        if m:
            if cls._is_invalid_number(m.group(1)): return None
            typed = QuestionTypeLabelParser.extract_leading(m.group(2))
            return ParsedQuestionStart(m.group(1), typed.remainder if typed else m.group(2), typed.type if typed else None)

        m = cls._SPACED_QS.search(line)
        if m:
            num, rest = m.group(1), m.group(2)
            if len(num) <= 3 and not cls._is_invalid_number(num) and not cls._looks_like_year_prefix(num, rest):
                typed = QuestionTypeLabelParser.extract_leading(rest)
                return ParsedQuestionStart(num, typed.remainder if typed else rest, typed.type if typed else None)

        m = cls._GLUED_QS.search(line)
        if m:
            num, rest = m.group(1), m.group(2)
            if len(num) <= 2 and not cls._is_invalid_number(num) and rest.strip():
                typed = QuestionTypeLabelParser.extract_leading(rest)
                return ParsedQuestionStart(num, typed.remainder if typed else rest, typed.type if typed else None)
        return None

    @classmethod
    def _should_resume_after_global_ans(cls, source_lines, line_idx, start, last_num):
        curr = int(start.number) if start.number.isdigit() else None
        if curr is None or last_num is None: return False
        if curr <= last_num or curr - last_num > 5: return False
        return cls._looks_like_likely_q_structure(source_lines, line_idx, start, True)

    @classmethod
    def _looks_like_likely_q_structure(cls, source_lines, line_idx, start, require_subj_ans):
        rem = start.remainder.strip()
        if not rem or cls._SHORT_OBJ_ANS_REM.match(rem): return cls._looks_like_img_only_obj_q(source_lines, line_idx, start)
        if CompactQuestionRepair.has_compact_option_sequence(rem): return True
        if cls._count_standard_options_ahead(source_lines, line_idx) >= 2: return True
        if cls._looks_like_img_only_obj_q(source_lines, line_idx, start): return True
        if cls._looks_like_blank_or_judge(source_lines, line_idx, start): return True
        subj_like = start.forced_type in (QuestionType.SHORT, QuestionType.BLANK) or cls._looks_like_subj_rem(rem)
        if not subj_like: return False
        return not require_subj_ans or cls._has_answer_marker_ahead(source_lines, line_idx)

    @classmethod
    def _normalize_generated_q_numbers(cls, blocks):
        if not any(b.number_generated for b in blocks): return blocks
        explicit_nums = {int(b.number.strip()) for b in blocks if not b.number_generated and b.number.strip().isdigit() and int(b.number.strip()) > 0}
        gen_nums = set()
        res = []
        for idx, b in enumerate(blocks):
            if not b.number_generated:
                res.append(b)
                continue
            cand = idx + 1
            while cand in explicit_nums or cand in gen_nums:
                cand += 1
            gen_nums.add(cand)
            res.append(QuestionBlock(str(cand), b.lines, b.category, b.forced_type, b.sequence, b.number_generated))
        return res

    @classmethod
    def _synthetic_q_number(cls, parent, idx):
        base = parent.split("-")[0].strip() if parent else ""
        return f"{base}-{idx}" if base else str(idx)

    @staticmethod
    def _is_invalid_number(n): return n.strip().isdigit() and int(n.strip()) == 0

    @classmethod
    def _is_standalone_numeric_table_value(cls, line):
        norm = line.strip()
        if not cls._STANDALONE_NUMERIC.match(norm): return False
        digits = sum(c.isdigit() for c in norm)
        if digits >= 4 or re.search(r"[.．Ee]", norm, re.IGNORECASE) or norm == "0": return True
        return False

    @staticmethod
    def _looks_like_year_prefix(n, r): return len(n) == 4 and r.startswith("年")

    @classmethod
    def _is_material_intro(cls, line):
        return bool(re.search(r"^\s*材料[一二三四五六七八九十0-9]+\s*[:：]", line) or cls._MATERIAL_INTRO_LINE.search(line))

    @classmethod
    def _is_pure_front_matter(cls, line): return bool(cls._PURE_FRONT_MATTER.match(line.strip()))

    @classmethod
    def _count_standard_options_ahead(cls, source_lines, q_idx):
        opt_count = 0; non_blank = 0
        for i in range(q_idx + 1, len(source_lines)):
            l = source_lines[i].strip()
            if not l: continue
            non_blank += 1
            if cls._parse_question_start(l) or SectionTitleParser.is_section_heading(l): break
            if CompactQuestionRepair.is_standard_option_line(l):
                opt_count += 1
                if opt_count >= 2: return opt_count
            if non_blank >= 12: break
        return opt_count

    @classmethod
    def _looks_like_img_only_obj_q(cls, source_lines, line_idx, start):
        forced_obj = start.forced_type in (QuestionType.SINGLE, QuestionType.MULTIPLE)
        rem = start.remainder.strip()
        rem_obj = bool(rem) and (CompactQuestionRepair.has_compact_option_sequence(rem) or bool(re.search(r"(?:下列|以下|哪个|哪项|哪一项|选择|选出|正确|错误|不正确|符合|不符合|最(?:合适|符合|恰当))", rem)))
        ev = cls._scan_q_structure_ahead(source_lines, line_idx)
        if forced_obj and (ev["obj"] or ev["img_choice"] or ev["img_ans"]): return True
        if rem_obj and (ev["obj"] or ev["img_choice"]): return True
        if not rem and ev["img_choice"] and ev["ans"]: return True
        return False

    @classmethod
    def _scan_q_structure_ahead(cls, source_lines, q_idx):
        ev = {"img": False, "obj": False, "img_choice": False, "ans": False, "img_ans": False}
        non_blank = 0; std_opts = 0; has_compact = False; has_img_lbls = False
        for i in range(q_idx + 1, len(source_lines)):
            l = source_lines[i].strip()
            if not l: continue
            non_blank += 1
            if cls._parse_question_start(l) or SectionTitleParser.is_section_heading(l): break
            if QuestionImageMarker.contains(l): ev["img"] = True
            if CompactQuestionRepair.is_standard_option_line(l): std_opts += 1
            if CompactQuestionRepair.has_compact_option_sequence(l): has_compact = True
            if cls._is_seq_img_option_label_line(l): has_img_lbls = True
            if cls._ANSWER_LINE.search(l) or cls._INLINE_ANS_MARKER.search(l): ev["ans"] = True
            if non_blank >= 14: break
        ev["obj"] = std_opts >= 2 or has_compact
        ev["img_choice"] = ev["img"] and (has_img_lbls or ev["obj"])
        ev["img_ans"] = ev["img"] and ev["ans"]
        return ev

    @staticmethod
    def _is_seq_img_option_label_line(line):
        toks = [t.strip().upper() for t in line.split() if t.strip()]
        if len(toks) < 2 or len(toks) > 8: return False
        if any(not re.match(r"^[A-H]$", t) for t in toks): return False
        return toks == [chr(65 + i) for i in range(len(toks))]

    @classmethod
    def _looks_like_blank_or_judge(cls, source_lines, line_idx, start):
        rem = start.remainder.strip()
        if not rem or cls._SHORT_OBJ_ANS_REM.match(rem): return False
        if not cls._has_inline_or_ahead_ans(source_lines, line_idx, rem): return False
        return bool(cls._FILL_BLANK_CUE.search(rem) or cls._JUDGE_CUE.search(rem) or cls._has_judge_ans_ahead(source_lines, line_idx) or CodeLikeTextGuard.has_unprotected_empty_parentheses(rem))

    @classmethod
    def _has_inline_or_ahead_ans(cls, source_lines, line_idx, rem):
        return bool(cls._INLINE_ANS_MARKER.search(rem) or cls._has_answer_marker_ahead(source_lines, line_idx))

    @classmethod
    def _has_answer_marker_ahead(cls, source_lines, line_idx):
        non_blank = 0
        for i in range(line_idx + 1, len(source_lines)):
            l = source_lines[i].strip()
            if not l: continue
            non_blank += 1
            if cls._extract_subj_ans_tail(l) is not None: return True
            if cls._parse_question_start(l) or SectionTitleParser.is_section_heading(l) or non_blank >= 12: break
        return False

    @classmethod
    def _has_judge_ans_ahead(cls, source_lines, line_idx):
        from .answer_token import AnswerTokenParser
        non_blank = 0
        for i in range(line_idx + 1, len(source_lines)):
            l = source_lines[i].strip()
            if not l: continue
            non_blank += 1
            tail = cls._extract_subj_ans_tail(l)
            if tail is not None and AnswerTokenParser.parse_judge_answer(tail): return True
            if cls._parse_question_start(l) or SectionTitleParser.is_section_heading(l) or non_blank >= 12: break
        return False

    @classmethod
    def _should_attach_subj_ans_marker(cls, current_lines, line, forced_type):
        if not current_lines or cls._extract_subj_ans_tail(line) is None: return False
        if any(CompactQuestionRepair.is_standard_option_line(l) for l in current_lines): return False
        if forced_type == QuestionType.SHORT: return True
        q_part = "\n".join(current_lines)
        return bool(cls._SUBJ_QUESTION_TYPE.search(q_part) or cls._SUBJ_QUESTION_CUE.search(q_part))

    @classmethod
    def _should_keep_as_subj_ans_cont(cls, current_lines, line, curr_num, forced_type, source_lines, line_idx):
        ans_idx = cls._find_subj_ans_marker_idx(current_lines, forced_type)
        if ans_idx < 0: return False
        if cls._looks_like_typed_q_start(line): return False
        if re.search(r"^\s*(?:问题|题目|第\s*[一二三四五六七八九十百0-9]+\s*(?:题|问|道题|个问题))", line): return False
        start = cls._parse_question_start(line)
        if start:
            if cls._looks_like_likely_q_structure(source_lines, line_idx, start, True): return False
            if cls._starts_later_q_within_window(curr_num, start) and cls._looks_like_blank_or_judge(source_lines, line_idx, start): return False
        item = cls._parse_numbered_subj_item(line)
        if item is None: return bool(cls._CHINESE_SUBJ_ITEM.search(line))
        prev_nums = [it[0] for it in (cls._parse_numbered_subj_item(l) for l in current_lines[ans_idx+1:]) if it]
        last_num = prev_nums[-1] if prev_nums else None
        curr_q_idx = int(curr_num.split("-")[0]) if curr_num.split("-")[0].isdigit() else None
        expected_next = curr_q_idx is not None and item[0] == curr_q_idx + 1
        rolls_back = last_num is not None and item[0] <= last_num
        breaks_seq = last_num is not None and item[0] != last_num + 1
        has_blank_sep = any(not source_lines[i].strip() for i in range(max(0, line_idx - 2), line_idx))
        looks_like_q = cls._looks_like_subj_rem(item[1])
        has_own_ans = cls._has_answer_marker_ahead(source_lines, line_idx)
        clearly_later = curr_q_idx is not None and item[0] > curr_q_idx and item[0] - curr_q_idx <= 5 and has_own_ans and looks_like_q
        is_high_conf = clearly_later or (expected_next and (has_own_ans or (rolls_back and looks_like_q) or (breaks_seq and looks_like_q) or (last_num is None and has_blank_sep and looks_like_q)))
        if is_high_conf: return False
        if last_num is None: return item[0] == 1 or not expected_next
        return item[0] >= last_num or not expected_next

    @classmethod
    def _should_keep_as_analysis_cont(cls, current_lines, line, source_lines, line_idx):
        if not any(cls._ANALYSIS_LINE.search(l) for l in current_lines): return False
        start = cls._parse_question_start(line)
        if not start: return False
        return not cls._looks_like_likely_q_structure(source_lines, line_idx, start, False)

    @classmethod
    def _find_subj_ans_marker_idx(cls, current_lines, forced_type):
        idx = next((i for i in range(len(current_lines)-1, -1, -1) if cls._extract_subj_ans_tail(current_lines[i]) is not None), -1)
        if idx < 0: return -1
        if forced_type == QuestionType.SHORT: return idx
        q_part = "\n".join(current_lines[:idx])
        if cls._SUBJ_QUESTION_TYPE.search(q_part) or cls._SUBJ_QUESTION_CUE.search(q_part): return idx
        marker = current_lines[idx]
        if cls._SUBJ_CONT_MARKER.search(marker): return idx
        tail = cls._extract_subj_ans_tail(marker) or ""
        if not tail or cls._SUBJ_ANSWER_INTRO.search(tail): return idx
        return -1

    @classmethod
    def _extract_subj_ans_tail(cls, line):
        m = cls._SUBJ_MARKER_WITH_TAIL.search(line)
        if m: return m.group(1).strip()
        return "" if cls._BARE_SUBJ_MARKER.match(line) else None

    @classmethod
    def _parse_numbered_subj_item(cls, line):
        m = cls._NUMBERED_SUBJ_ITEM.search(line)
        if not m: return None
        num = int(m.group(1) or m.group(2))
        content = m.group(3).strip()
        return (num, content) if content else None

    @staticmethod
    def _looks_like_subj_rem(content):
        n = content.strip()
        if not n: return False
        return n.endswith(("？", "?")) or bool(re.search(r"^(?:请|简述|简答|论述|阐述|概括|分析|说明|解释|谈谈|指出|列举|试述|为什么|如何|结合|根据|什么是|有哪些|有何|提出)", n))

    @classmethod
    def _starts_later_q_within_window(cls, curr_num, start):
        c = int(curr_num.split("-")[0]) if curr_num.split("-")[0].isdigit() else None
        n = int(start.number) if start.number.isdigit() else None
        return c is not None and n is not None and c < n <= c + 5

    @classmethod
    def _looks_like_typed_q_start(cls, line):
        return (cls._parse_question_start(line) or ParsedQuestionStart("", "", None)).forced_type is not None

    @staticmethod
    def _looks_like_interview_rem(rest):
        if not rest or SectionTitleParser.is_section_heading(rest): return False
        if re.search(r"(?:测试区|样本|题库|格式|边界|极端|客观题|主观题|材料题|集中答案|功能测试)", rest, re.IGNORECASE): return False
        return bool(re.search(r"[?？]", rest) or re.search(r"^(?:请|谈谈|你|如何|为什么|是否|如果|根据|结合|概括|指出|分析|提出|围绕|下列|单位|群众|有人认为|某)", rest))

    @classmethod
    def _should_start_next_synthetic(cls, current_lines, next_line):
        if any(cls._SUBJ_CONT_MARKER.search(l) for l in current_lines): return False
        if not cls._is_likely_unnumbered_q(next_line): return False
        if CompactQuestionRepair.is_standard_option_line(next_line): return False
        has_opt = any(CompactQuestionRepair.is_standard_option_line(l) or CompactQuestionRepair.has_compact_option_sequence(l) for l in current_lines)
        has_ans = any(cls._EMBEDDED_ANSWER.search(l) or cls._ANSWER_LINE.search(l) for l in current_lines)
        return has_ans or has_opt

    @classmethod
    def _is_likely_typed_q(cls, line, forced_type):
        if forced_type is None: return False
        if len(line) < 2 or CompactQuestionRepair.is_standard_option_line(line): return False
        if cls._ANSWER_LINE.search(line) or cls._ANALYSIS_LINE.search(line) or SectionTitleParser.is_section_heading(line): return False
        return True

    @classmethod
    def _is_likely_unnumbered_q(cls, line):
        if len(line) < 4 or cls._is_pure_front_matter(line): return False
        if re.search(r"^(?:用途|说明|备注|注意|提示)\s*[:：]", line): return False
        if re.search(r"^\s*[\[【]\s*(?:待确认|备注|提示|说明|注|注意)", line): return False
        if CompactQuestionRepair.is_standard_option_line(line) or cls._ANSWER_LINE.search(line) or cls._ANALYSIS_LINE.search(line) or SectionTitleParser.is_section_heading(line): return False
        typed = QuestionTypeLabelParser.extract_leading(line)
        if typed and typed.remainder: return True
        if cls._EMBEDDED_ANSWER.search(line): return True
        if CodeLikeTextGuard.looks_like_standalone_code_expression(line): return False
        if cls._has_unprotected_obj_marker(line) or CodeLikeTextGuard.has_unprotected_empty_parentheses(line): return True
        if re.search(r"^(?:问题|题目|请回答|请谈谈|谈谈|你怎么看|你怎么处理)", line): return True
        if re.search(r"[?？。]$", line): return True
        return False

    @classmethod
    def _has_unprotected_obj_marker(cls, line):
        for m in cls._UNNUMBERED_OBJ_MARKER.finditer(line):
            tok = m.group(1) or m.group(2)
            if not CodeLikeTextGuard.is_protected_parenthesized_token(line, m.start(), m.end(), tok): return True
        return False
