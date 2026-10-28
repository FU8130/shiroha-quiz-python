"""Shiroha Quiz Python 解析器包。

公开接口：
    from quiz_parser import (
        Question, Option, QuestionType, ImportResult, ImportWarning,
        WarningLevel, ImportDiagnostics, ParsedAnswerEntry,
        AnswerTokenParser,
        QuestionImageMarker, QuestionTextNormalizer,
        QuestionTypeLabelParser, SectionTitleParser, SectionInfo,
        LeadingTypeLabel,
        normalize_question_index, chinese_number_to_int,
        is_judge_option_pair, should_infer_judge_from_binary_options,
    )
"""

from .models import (
    Question, Option, QuestionType,
    ImportResult, ImportWarning, WarningLevel,
    ImportDiagnostics, ParsedAnswerEntry,
)
from .answer_token import AnswerTokenParser
from .base import (
    QuestionImageMarker, QuestionTextNormalizer,
    QuestionTypeLabelParser, LeadingTypeLabel,
    SectionTitleParser, SectionInfo,
    normalize_question_index, chinese_number_to_int,
    is_judge_option_pair, should_infer_judge_from_binary_options,
)

__version__ = "0.1.0"
__all__ = [
    "Question", "Option", "QuestionType",
    "ImportResult", "ImportWarning", "WarningLevel",
    "ImportDiagnostics", "ParsedAnswerEntry",
    "AnswerTokenParser",
    "QuestionImageMarker", "QuestionTextNormalizer",
    "QuestionTypeLabelParser", "LeadingTypeLabel",
    "SectionTitleParser", "SectionInfo",
    "normalize_question_index", "chinese_number_to_int",
    "is_judge_option_pair", "should_infer_judge_from_binary_options",
]
