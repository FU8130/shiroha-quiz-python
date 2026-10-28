# quiz_parser/standard.py
from __future__ import annotations
import re
from typing import Optional

from .models import Question, Option, QuestionType
from .base import QuestionTypeLabelParser, should_infer_judge_from_binary_options, is_judge_option_pair
from .answer_token import AnswerTokenParser
from .compact import CompactQuestionRepair
from .code_guard import CodeLikeTextGuard
from .multiblank import MultiBlankQuestionParser

class StandardQuestionParser:
    # 加入了中文逗号，兼容 A，选项1
    _OPTION_LINE = re.compile(r"^([A-Ha-h])\s*[.、．:：)），,]\s*(.*)$")
    _ANS_LINE = re.compile(r"^\s*(?:[\[【]\s*)?(?:本题)?(?:答案|正确答案|参考答案|标准答案|参考要点|参考思路|答题要点|答题思路|作答思路|评分要点|参考作答|答)(?:\s*[\]】])?\s*(?:[:：]|为)\s*(.*)$")
    _ANALYSIS_LINE = re.compile(r"^\s*(?:[\[【]\s*)?(?:答案解析|解题思路|解析思路|解题分析|参考解析|详解|分析|理由|解答|解析|说明)(?:\s*[\]】])?\s*(?:[:：]|\s+)\s*(.*)$")
    _PAREN_ANS = re.compile(r"[（(]\s*([A-Ha-h](?:\s*[,，、\s]\s*[A-Ha-h]){0,7})\s*[）)]")
    # 新增：行内答案提取
    _INLINE_ANS = re.compile(r"(?:答案|正确答案|参考答案)\s*[:：]\s*([A-Ha-h]+|对|错|正确|错误|√|×|F|T|True|False|是|否)\s*$", re.IGNORECASE)

    @classmethod
    def parse(cls, lines: list[str], forced_type: Optional[QuestionType] = None) -> list[Question]:
        if not lines: return []
        
        raw_text = "\n".join(lines)
        repaired_text = CompactQuestionRepair.repair(raw_text)
        repaired_lines = [l.strip() for l in repaired_text.split("\n") if l.strip()]

        stem_lines = []
        options = []
        answer_raw = ""
        analysis_lines = []
        
        state = "stem"
        for line in repaired_lines:
            if state == "stem":
                m_ans = cls._ANS_LINE.match(line)
                if m_ans:
                    answer_raw = m_ans.group(1).strip()
                    state = "analysis"
                    continue
                m_ana = cls._ANALYSIS_LINE.match(line)
                if m_ana:
                    analysis_lines.append(m_ana.group(1).strip())
                    state = "analysis"
                    continue
                
                m_opt = cls._OPTION_LINE.match(line)
                if m_opt:
                    key = m_opt.group(1).upper()
                    text = m_opt.group(2).strip()
                    if not CodeLikeTextGuard.looks_like_leading_code_option(line, 0, len(line) - len(m_opt.group(2))):
                        options.append(Option(key, text))
                        state = "options"
                        continue
                stem_lines.append(line)
            elif state == "options":
                m_ans = cls._ANS_LINE.match(line)
                if m_ans:
                    answer_raw = m_ans.group(1).strip()
                    state = "analysis"
                    continue
                m_ana = cls._ANALYSIS_LINE.match(line)
                if m_ana:
                    analysis_lines.append(m_ana.group(1).strip())
                    state = "analysis"
                    continue
                
                m_opt = cls._OPTION_LINE.match(line)
                if m_opt:
                    key = m_opt.group(1).upper()
                    text = m_opt.group(2).strip()
                    if not CodeLikeTextGuard.looks_like_leading_code_option(line, 0, len(line) - len(m_opt.group(2))):
                        options.append(Option(key, text))
                        continue
                if options:
                    options[-1].text += "\n" + line
                else:
                    stem_lines.append(line)
            elif state == "analysis":
                m_ana = cls._ANALYSIS_LINE.match(line)
                if m_ana:
                    analysis_lines.append(m_ana.group(1).strip())
                else:
                    analysis_lines.append(line)

        stem = "\n".join(stem_lines).strip()
        analysis = "\n".join(analysis_lines).strip()
        
        # 提取题干末尾的答案
        if not answer_raw:
            m_inline = cls._INLINE_ANS.search(stem)
            if m_inline:
                answer_raw = m_inline.group(1)
                stem = stem[:m_inline.start()].strip()
                
        # 提取题干括号答案
        if not answer_raw:
            m = cls._PAREN_ANS.search(stem)
            if m:
                start, end = m.span()
                if (start == 0 or not stem[start-1].isalnum()) and (end == len(stem) or not stem[end].isalnum()):
                    answer_raw = m.group(1)
                    stem = stem[:start] + stem[end:]
                    stem = stem.strip()

        if forced_type:
            q_type = forced_type
        else:
            q_type = cls._infer_type(stem, options, answer_raw)

        if q_type in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            ans = AnswerTokenParser.parse_objective_answers(answer_raw, [o.key for o in options])
        elif q_type == QuestionType.JUDGE:
            ans = AnswerTokenParser.parse_judge_answer(answer_raw)
            if not options:
                options = [Option("A", "正确"), Option("B", "错误")]
        else:
            ans = AnswerTokenParser.parse_text_answer(answer_raw)

        mb_result = MultiBlankQuestionParser.extract(stem, q_type, options, answer_raw, ans)
        
        q = Question(
            number="", type=q_type, question=mb_result.question_text,
            options=options, answer=mb_result.answer, blankAnswers=mb_result.blank_answers,
            analysis=analysis, warnings=mb_result.warnings
        )
        return [q]

    @classmethod
    def _infer_type(cls, stem: str, options: list[Option], answer_raw: str) -> QuestionType:
        if options:
            if is_judge_option_pair([o.key for o in options], [o.text for o in options]) and should_infer_judge_from_binary_options(stem, answer_raw):
                return QuestionType.JUDGE
            if len(options) == 2 and all(o.text in ["正确", "错误", "对", "错", "是", "否", "√", "×", "True", "False"] for o in options):
                return QuestionType.JUDGE
            ans = AnswerTokenParser.parse_objective_answers(answer_raw)
            if len(ans) > 1:
                return QuestionType.MULTIPLE
            return QuestionType.SINGLE
        
        if AnswerTokenParser.is_judge_answer_text(answer_raw):
            return QuestionType.JUDGE
        if CodeLikeTextGuard.has_unprotected_empty_parentheses(stem) or re.search(r"_{2,}|＿{2,}", stem):
            return QuestionType.BLANK
        if re.search(r"(填空|补全|填入|空白处)", stem):
            return QuestionType.BLANK
        return QuestionType.SHORT