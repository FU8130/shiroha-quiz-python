"""第 4 批冒烟：答案区、双文件、表格。"""
from quiz_parser.answer_section import parse_answer_section
from quiz_parser.dual_file import DualFileMerger
from quiz_parser.excel import ExcelQuestionTableParser
from quiz_parser.models import Question, QuestionType, ParsedAnswerEntry
from quiz_parser.standard import StandardQuestionParser

def test_answer_section():
    text = "题号: 1 2 3\n答案: A B C"
    entries = parse_answer_section(text)
    assert len(entries) == 3
    assert entries[0].answer == ["A"]
    assert entries[2].answer == ["C"]

def test_dual_file():
    q = Question(number="1", type=QuestionType.SINGLE, question="题目", options=[])
    a = ParsedAnswerEntry(number="1", answer=["B"])
    res = DualFileMerger.merge_auto([q], [a])
    assert res.questions[0].answer == ["B"]
    assert res.name == "按全局题号合并"

def test_excel():
    tsv = "题号\t题型\t题干\tA\tB\tC\tD\t答案\t解析\n1\t单选题\t安全帽的作用\t保护\t装饰\t增重\t无用\tA\t保护头部"
    qs = ExcelQuestionTableParser.parse(tsv)
    assert len(qs) == 1
    assert qs[0].type == QuestionType.SINGLE
    assert qs[0].answer == ["A"]
    assert qs[0].options[0].text == "保护"

def run_all() -> bool:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try: t()
        except AssertionError as e: failed.append((t.__name__, str(e)))
    if failed:
        print(f"FAILED: {len(failed)} / {len(tests)}")
        for n, e in failed: print(f"  - {n}: {e}")
        return False
    print(f"OK: {len(tests)} / {len(tests)} tests passed")
    return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
