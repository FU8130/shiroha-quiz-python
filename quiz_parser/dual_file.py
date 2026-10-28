"""双文件合并，对齐 Kotlin DualFileMerger。"""
from dataclasses import dataclass
from .models import Question, ParsedAnswerEntry, QuestionType, ImportWarning, WarningLevel
from .validator import validate
from .scorer import score
from .answer_token import AnswerTokenParser
from .multiblank import MultiBlankSupport
from .chapter import normalize_chapter

@dataclass
class MergeResult:
    questions: list[Question]
    warnings: list[ImportWarning]
    name: str = "按题号合并"

class DualFileMerger:
    @classmethod
    def merge_strict_number(cls, questions: list[Question], answers: list[ParsedAnswerEntry]) -> MergeResult:
        """严格按题号匹配：题号字符串必须完全一致，不做模糊/顺序兜底。"""
        by_number = {str(a.number).strip(): a for a in answers}
        warns = []
        for q in questions:
            key = str(q.number).strip()
            entry = by_number.get(key)
            if entry is None:
                warns.append(ImportWarning(WarningLevel.WARNING, q.number, "未匹配到对应答案"))
                continue
            if not q.answer:
                q.answer = list(entry.answer)
        return MergeResult(questions, warns)

    @classmethod
    def merge_auto(cls, questions: list[Question], answers: list[ParsedAnswerEntry]) -> MergeResult:
        c1 = cls._merge_by_number(questions, answers)
        c2 = cls._merge_by_type_and_number(questions, answers)
        c3 = cls._merge_by_sequence(questions, answers)
        
        candidates = [c1, c2]
        if not any(a.number in {q.number for q in questions} for a in answers):
            candidates.append(c3)
            
        best = c1
        best_score = -999999
        for c in candidates:
            v = validate(c.questions)
            s = score(c.questions, v + c.warnings)
            if s > best_score:
                best_score = s
                best = c
        return best

    @classmethod
    def _apply_answer(cls, q: Question, entry: ParsedAnswerEntry) -> Question:
        if q.type == QuestionType.BLANK:
            blank_count = len(q.blankAnswers) if len(q.blankAnswers) > 1 else MultiBlankSupport.count_explicit_blanks(q.question)
            if blank_count and blank_count > 1 and not q.answer:
                raw = "；".join(entry.answer)
                parts = MultiBlankSupport.split_reliable_parts(raw, blank_count)
                if parts:
                    groups = [[p] for p in parts]
                    return q.copy(blankAnswers=groups, answer=MultiBlankSupport.compatibility_answer(groups), analysis=q.analysis or entry.analysis)

        merged_ans = q.answer if q.answer else entry.answer
        merged_type = QuestionType.MULTIPLE if q.type == QuestionType.SINGLE and len(merged_ans) > 1 else q.type
        return q.copy(type=merged_type, answer=merged_ans, analysis=q.analysis or entry.analysis)

    @classmethod
    def _merge_by_number(cls, questions: list[Question], answers: list[ParsedAnswerEntry]) -> MergeResult:
        amap = {a.number: a for a in answers}
        used = set()
        warns = []
        res = []
        for q in questions:
            if q.number in amap:
                used.add(q.number)
                res.append(cls._apply_answer(q, amap[q.number]))
            else:
                warns.append(ImportWarning(WarningLevel.WARNING, q.number, "未匹配到对应答案"))
                res.append(q)
        return MergeResult(res, warns, "按全局题号合并")

    @classmethod
    def _merge_by_type_and_number(cls, questions: list[Question], answers: list[ParsedAnswerEntry]) -> MergeResult:
        typed_answers = [a for a in answers if a.type is not None]
        if not typed_answers: return cls._merge_by_number(questions, answers)
        amap = {(a.type or QuestionType.SINGLE, a.number): a for a in typed_answers}
        warns = []
        res = []
        for q in questions:
            match = amap.get((q.type, q.number))
            if match:
                res.append(cls._apply_answer(q, match))
            else:
                warns.append(ImportWarning(WarningLevel.WARNING, q.number, "未在对应题型分组中匹配到答案"))
                res.append(q)
        return MergeResult(res, warns, "按题型分组题号合并")

    @classmethod
    def _merge_by_sequence(cls, questions: list[Question], answers: list[ParsedAnswerEntry]) -> MergeResult:
        warns = []
        res = []
        for i, q in enumerate(questions):
            if i < len(answers):
                res.append(cls._apply_answer(q, answers[i]))
            else:
                warns.append(ImportWarning(WarningLevel.WARNING, q.number, "按顺序未匹配到答案"))
                res.append(q)
        return MergeResult(res, warns, "按顺序合并")
