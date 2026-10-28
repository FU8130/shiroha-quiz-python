"""第 2b-1 批冒烟：CodeLikeTextGuard + CompactQuestionRepair。"""

from quiz_parser.code_guard import CodeLikeTextGuard
from quiz_parser.compact import CompactQuestionRepair
from quiz_parser.base import QuestionImageMarker


def test_guard_string_protection():
    # 字符串里的括号受保护
    assert CodeLikeTextGuard.is_index_in_string_or_comment('x = "(A)"', 5)
    # 注释里的括号受保护
    assert CodeLikeTextGuard.is_index_in_string_or_comment("// (B)\n", 4)
    # 普通括号不受保护
    assert not CodeLikeTextGuard.is_index_in_string_or_comment("（AD）", 1)


def test_guard_empty_parens():
    assert CodeLikeTextGuard.has_unprotected_empty_parentheses("以下（）说法")
    assert not CodeLikeTextGuard.has_unprotected_empty_parentheses('x = "()"')


def test_guard_code_expression():
    assert CodeLikeTextGuard.looks_like_standalone_code_expression("ls.append(Da)")
    assert CodeLikeTextGuard.looks_like_standalone_code_expression("if (x > 0)")
    assert not CodeLikeTextGuard.looks_like_standalone_code_expression("以下哪项正确（A）")


def test_guard_numeric_code():
    assert CodeLikeTextGuard.looks_like_numeric_code_or_data_line("3.14159")
    assert CodeLikeTextGuard.looks_like_numeric_code_or_data_line("192.168.1.1")


def test_compact_basic_sequence():
    assert CompactQuestionRepair.has_compact_option_sequence("A.xx B.xx C.xx D.xx")


def test_compact_no_false_positive():
    assert not CompactQuestionRepair.has_compact_option_sequence("以下哪项正确（A）")


def test_compact_standard_option_line():
    assert CompactQuestionRepair.is_standard_option_line("A. 选项文字")
    assert CompactQuestionRepair.is_standard_option_line("A、选项文字")
    assert not CompactQuestionRepair.is_standard_option_line("A型血")


def test_compact_repair_split():
    out = CompactQuestionRepair.repair("题干 A.aa B.bb C.cc D.dd")
    lines = out.split("\n")
    assert "A.aa" in lines or "A. aa" in lines
    assert any("B.bb" in l or "B. bb" in l for l in lines)


def test_compact_technical_expr():
    assert not CompactQuestionRepair.has_compact_option_sequence("E.U. 温度")


def test_compact_image_marker():
    # 图片标记内的字母不能触发紧凑拆分
    assert not CompactQuestionRepair.has_compact_option_sequence(
        "[[SHIROHA_IMAGE:img_0001]] A.xx"
    )


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
        for n, e in failed:
            print(f"  - {n}: {e}")
        return False
    print(f"OK: {len(tests)} / {len(tests)} tests passed")
    return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
