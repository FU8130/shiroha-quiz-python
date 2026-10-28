# quiz_parser/models.py
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class QuestionType(str, Enum):
    SINGLE = "SINGLE"
    MULTIPLE = "MULTIPLE"
    JUDGE = "JUDGE"
    BLANK = "BLANK"
    SHORT = "SHORT"

class WarningLevel(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    ERROR = "ERROR"

@dataclass
class Option:
    key: str
    text: str

@dataclass
class QuestionImage:
    localPath: str
    sourceName: str = ""
    order: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    sizeBytes: int = 0

@dataclass
class Question:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: str = ""
    type: QuestionType = QuestionType.SHORT
    question: str = ""
    options: list[Option] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    blankAnswers: list[list[str]] = field(default_factory=list)
    analysis: str = ""
    category: str = ""
    images: list[QuestionImage] = field(default_factory=list)
    score: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    def copy(self, **kwargs):
        import dataclasses
        return dataclasses.replace(self, **kwargs)

@dataclass
class ImportWarning:
    level: WarningLevel
    questionNumber: Optional[str] = None
    message: str = ""

@dataclass
class ImportDiagnostics:
    normalizedLength: int = 0
    blockCount: int = 0
    answeredCount: int = 0
    candidateCount: int = 0
    notes: list[str] = field(default_factory=list)

@dataclass
class ImportResult:
    questions: list[Question]
    strategyName: str = ""
    warnings: list[ImportWarning] = field(default_factory=list)
    diagnostics: ImportDiagnostics = field(default_factory=ImportDiagnostics)

@dataclass
class ParsedAnswerEntry:
    number: str
    answer: list[str]
    analysis: str = ""
    type: Optional[QuestionType] = None
    category: str = ""
    sequence: int = 0