"""第 5 批冒烟：QuizImportParser 端到端测试。"""
from quiz_parser.quiz_parser import QuizImportParser

def test_full_single():
    text = "一、单选题\n1. 安全帽的作用是？\nA. 保护头部\nB. 装饰\nC. 增重\nD. 无用\n答案：A\n解析：安全帽用于保护头部。"
    res = QuizImportParser.parse_standard_text(text)
    assert len(res.questions) == 1
    q = res.questions[0]
    assert q.number == "1"
    assert q.answer == ["A"]
    assert q.analysis == "安全帽用于保护头部。"

def test_full_dual():
    q_text = "1. 以下哪项正确？\nA. 选项1\nB. 选项2"
    a_text = "1. B"
    res = QuizImportParser.parse_dual_text(q_text, a_text)
    assert len(res.questions) == 1
    assert res.questions[0].answer == ["B"]
    assert "双文件合并" in res.strategyName

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
