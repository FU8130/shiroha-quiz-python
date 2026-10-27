"""第 2b-2 批冒烟：QuestionBlockSplitter。"""
from quiz_parser.splitter import QuestionBlockSplitter

def test_split_simple():
    text = "1. 第一题\nA. 选项A\nB. 选项B\n2. 第二题\nA. 选项A\nB. 选项B"
    blocks = QuestionBlockSplitter.split(text)
    assert len(blocks) == 2
    assert blocks[0].number == "1"
    assert blocks[1].number == "2"

def test_split_skip_front_matter():
    text = "绝密\n注意事项：请认真作答\n1. 第一题\nA. 选项A\nB. 选项B"
    blocks = QuestionBlockSplitter.split(text)
    assert len(blocks) == 1
    assert blocks[0].number == "1"

def test_split_answer_section_skip():
    text = "1. 第一题\nA. 选项A\nB. 选项B\n参考答案\n1. A\n2. B"
    blocks = QuestionBlockSplitter.split(text)
    assert len(blocks) == 1

def test_split_glued_number():
    text = "1下列说法正确的是\nA. 选项A\nB. 选项B"
    blocks = QuestionBlockSplitter.split(text)
    assert len(blocks) == 1
    assert blocks[0].number == "1"
    assert blocks[0].lines[0] == "下列说法正确的是"

def test_split_allow_unnumbered():
    text = "下列哪项正确（ ）\nA. 选项A\nB. 选项B"
    blocks = QuestionBlockSplitter.split(text, allow_unnumbered=True)
    assert len(blocks) == 1
    assert blocks[0].number == "1"
    assert blocks[0].number_generated is True

def run_all() -> bool:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, e))
    if failed:
        print(f"FAILED: {len(failed)} / {len(tests)}")
        for n, e in failed: print(f"  - {n}: {e}")
        return False
    print(f"OK: {len(tests)} / {len(tests)} tests passed")
    return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
