"""策略打分，对齐 Kotlin ImportStrategyScorer。"""
from .models import Question, QuestionType, ImportWarning, WarningLevel

def score(questions: list[Question], warnings: list[ImportWarning]) -> int:
    if not questions: return -1000000
    answered = sum(1 for q in questions if q.answer)
    hard_err = sum(1 for w in warnings if w.level == WarningLevel.ERROR)
    soft_warn = sum(1 for w in warnings if w.level == WarningLevel.WARNING)
    analysis = sum(1 for q in questions if q.analysis)
    
    ans_cov = answered / len(questions)
    obj_count = sum(1 for q in questions if q.type in (QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.JUDGE))
    opt_cov = sum(1 for q in questions if q.type in (QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.JUDGE) and len(q.options) >= 2) / obj_count if obj_count else 0.0
    
    section_bonus = 20 if any(q.category for q in questions) else 0
    return int(len(questions) * 5 + answered * 12 + analysis * 4 + ans_cov * 150 + opt_cov * 80 + section_bonus - hard_err * 35 - soft_warn * 6)
