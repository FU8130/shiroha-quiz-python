"""quiz_parser 冒烟测试（第 1 批 + 第 2a 批）。"""

from quiz_parser import (
    QuestionType, AnswerTokenParser,
    QuestionImageMarker, QuestionTextNormalizer,
    QuestionTypeLabelParser, SectionTitleParser,
    chinese_number_to_int, normalize_question_index,
)


def test_models_enum():
    assert QuestionType.SINGLE.value == "SINGLE"
    assert QuestionType.MULTIPLE.value == "MULTIPLE"
    assert QuestionType.JUDGE.value == "JUDGE"
    assert QuestionType.BLANK.value == "BLANK"
    assert QuestionType.SHORT.value == "SHORT"


def test_answer_token_objective():
    assert AnswerTokenParser.parse_objective_answers("A") == ["A"]
    assert AnswerTokenParser.parse_objective_answers("AB") == ["A", "B"]
    assert AnswerTokenParser.parse_objective_answers("FH") == ["F", "H"]
    assert AnswerTokenParser.parse_objective_answers("F,H") == ["F", "H"]
    assert AnswerTokenParser.parse_objective_answers("F.") == ["F"]
    assert AnswerTokenParser.parse_objective_answers("A-D") == ["A", "B", "C", "D"]
    assert AnswerTokenParser.parse_objective_answers("A至D") == ["A", "B", "C", "D"]
    assert AnswerTokenParser.parse_objective_answers("全选", ["A", "B", "C", "D"]) == ["A", "B", "C", "D"]
    assert AnswerTokenParser.parse_objective_answers("以上全选", ["A", "B", "C", "D", "E"]) == ["A", "B", "C", "D", "E"]


def test_answer_token_judge():
    assert AnswerTokenParser.parse_judge_answer("f") == ["错误"]
    assert AnswerTokenParser.parse_judge_answer("false") == ["错误"]
    assert AnswerTokenParser.parse_judge_answer("False") == ["错误"]
    assert AnswerTokenParser.parse_judge_answer("✓") == ["正确"]
    assert AnswerTokenParser.parse_judge_answer("✗") == ["错误"]
    assert AnswerTokenParser.parse_judge_answer("正确") == ["正确"]
    assert AnswerTokenParser.parse_judge_answer("错误") == ["错误"]


def test_answer_token_text():
    assert AnswerTokenParser.parse_text_answer("检查设备、核对参数、确认安全防护措施") == [
        "检查设备、核对参数、确认安全防护措施"
    ]


def test_image_marker():
    assert QuestionImageMarker.contains("[[SHIROHA_IMAGE:img_0001]]")
    assert QuestionImageMarker.marker_id("[[SHIROHA_IMAGE:img_0001]]") == "img_0001"


def test_normalizer():
    assert QuestionTextNormalizer.normalize("\uFEFF1. 以下（正确）") == "1. 以下(正确)"
    assert QuestionTextNormalizer.normalize("绝密\n1. 题目") == "1. 题目"


def test_chinese_number():
    assert chinese_number_to_int("一") == 1
    assert chinese_number_to_int("十") == 10
    assert chinese_number_to_int("十一") == 11
    assert chinese_number_to_int("二十") == 20
    assert chinese_number_to_int("一百二十三") == 123
    assert normalize_question_index("三") == "3"
    assert normalize_question_index("12") == "12"


def test_type_label():
    assert QuestionTypeLabelParser.parse_label("【单选题】") == QuestionType.SINGLE
    assert QuestionTypeLabelParser.parse_label("多项选择") == QuestionType.MULTIPLE
    leading = QuestionTypeLabelParser.extract_leading("单选题：以下说法正确的是")
    assert leading is not None
    assert leading.type == QuestionType.SINGLE
    assert leading.remainder == "以下说法正确的是"


def test_section_title():
    info = SectionTitleParser.parse("一、单选题（共10题）")
    assert info is not None and info.forced_type == QuestionType.SINGLE
    info = SectionTitleParser.parse("二、多选题")
    assert info is not None and info.forced_type == QuestionType.MULTIPLE
    info = SectionTitleParser.parse("参考答案")
    assert info is not None and info.is_answer_section is True
    info = SectionTitleParser.parse("集中答案解析")
    assert info is not None and info.is_answer_section is True
    assert SectionTitleParser.parse("1.下列哪项是正确的") is None


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            failures.append((test.__name__, e))
    if failures:
        print(f"FAILED: {len(failures)} / {len(tests)}")
        for name, err in failures:
            print(f"  - {name}: {err}")
        return False
    print(f"OK: {len(tests)} / {len(tests)} tests passed")
    return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
