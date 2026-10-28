"""第 3 批冒烟：StandardQuestionParser + MultiBlankQuestionParser。"""
from quiz_parser.standard import StandardQuestionParser
from quiz_parser.models import QuestionType

def test_single_choice():
    lines = ["以下哪项正确？", "A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4", "答案：A"]
    qs = StandardQuestionParser.parse(lines)
    assert len(qs) == 1
    q = qs[0]
    assert q.type == QuestionType.SINGLE
    assert len(q.options) == 4
    assert q.answer == ["A"]

def test_multiple_choice():
    lines = ["以下哪些正确？", "A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4", "答案：AB"]
    qs = StandardQuestionParser.parse(lines)
    assert qs[0].type == QuestionType.MULTIPLE
    assert qs[0].answer == ["A", "B"]

def test_judge():
    lines = ["安全帽的主要作用是保护头部。", "答案：正确"]
    qs = StandardQuestionParser.parse(lines)
    assert qs[0].type == QuestionType.JUDGE
    assert qs[0].answer == ["正确"]
    assert len(qs[0].options) == 2

def test_blank():
    lines = ["安全帽的主要作用是（ ）。", "答案：保护头部"]
    qs = StandardQuestionParser.parse(lines)
    assert qs[0].type == QuestionType.BLANK
    assert qs[0].answer == ["保护头部"]

def test_multi_blank():
    lines = ["安全第一，（  ），（  ）。", "答案：预防为主；综合治理"]
    qs = StandardQuestionParser.parse(lines)
    assert qs[0].type == QuestionType.BLANK
    assert qs[0].answer == ["预防为主；综合治理"]
    assert len(qs[0].blankAnswers) == 2
    assert qs[0].blankAnswers[0] == ["预防为主"]
    assert qs[0].blankAnswers[1] == ["综合治理"]

def run_all() -> bool:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
    if failed:
        print(f"FAILED: {len(failed)} / {len(tests)}")
        for n, e in failed: print(f"  - {n}: {e}")
        return False
    print(f"OK: {len(tests)} / {len(tests)} tests passed")
    return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
