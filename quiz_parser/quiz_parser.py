# quiz_parser/quiz_parser.py
from __future__ import annotations
import re
from .models import ImportResult, ImportDiagnostics
from .base import QuestionTextNormalizer, SectionTitleParser
from .compact import CompactQuestionRepair
from .splitter import QuestionBlockSplitter
from .standard import StandardQuestionParser
from .excel import ExcelQuestionTableParser
from .answer_section import parse_answer_section
from .dual_file import DualFileMerger
from .validator import validate, dedupe_questions
from .scorer import score

class QuizImportParser:
    @classmethod
    def parse_standard_text(cls, text: str, mode: str = "auto", strategy: str = "auto") -> ImportResult:
        if not text or not text.strip():
            return cls._empty_result()

        if mode == "wenjuanxing":
            text = cls._strip_wenjuanxing(text)
        if strategy == "compact":
            text = CompactQuestionRepair.repair(text)

        # 表格路径必须用「原始文本」切列：normalize 会把全角逗号 ， 转成 ,，
        # 未加引号的解析列就会被切散，整行列错位。命中表格时也就没必要再对
        # 全文做一遍标准化（大题库能省掉一半时间）。
        allow_table = mode in ("auto", "json")
        if allow_table and ("," in text or "\t" in text):
            print("  [1/2] 尝试表格解析...")
            excel_questions = ExcelQuestionTableParser.parse(text)

            # 解析出题目但全都没有选项，说明可能是被逗号污染的普通文本，回退
            has_options = any(q.options for q in excel_questions) if excel_questions else False

            if excel_questions and has_options:
                print(f"  [2/2] 表格解析成功，共 {len(excel_questions)} 题。")
                excel_valid = validate(excel_questions)
                return cls._build_result(excel_questions, "Excel/CSV 表格题库解析", excel_valid, len(text), 0, 2)
            elif excel_questions and not has_options:
                print("  [!] 表格解析结果无选项，可能是普通文本误判，回退到文本解析...")

        print("  [1/3] 标准化文本...")
        normalized = QuestionTextNormalizer.normalize(text)
        if not normalized:
            return cls._empty_result()

        print("  [2/3] 普通文本切分与材料题重写...")
        normalized = cls._rewrite_shared_stem(normalized)
        
        blocks, ans_section_text = cls._extract_answer_section(normalized)
        std_questions = []
        for block in blocks:
            parsed_qs = StandardQuestionParser.parse(block.lines, block.forced_type)
            for q in parsed_qs:
                q.number = block.number
                q.category = block.category
                std_questions.append(q)
                
        std_warnings = []
        if ans_section_text:
            entries = parse_answer_section(ans_section_text)
            if entries:
                merge_res = DualFileMerger.merge_auto(std_questions, entries)
                std_questions = merge_res.questions
                std_warnings.extend(merge_res.warnings)

        print("  [3/3] 校验并打分...")
        std_valid = validate(std_questions) + std_warnings
        return cls._build_result(std_questions, "常规文本解析", std_valid, len(normalized), len(blocks), 2)

    @classmethod
    def parse_dual_text(cls, question_text: str, answer_text: str, match: str = "auto") -> ImportResult:
        q_norm = QuestionTextNormalizer.normalize(question_text)
        a_norm = QuestionTextNormalizer.normalize(answer_text)
        
        blocks, _ = cls._extract_answer_section(q_norm)
        qs = []
        for b in blocks:
            for q in StandardQuestionParser.parse(b.lines, b.forced_type):
                q.number = b.number
                q.category = b.category
                qs.append(q)
                
        entries = parse_answer_section(a_norm)
        if match == "number":
            merge_res = DualFileMerger._merge_by_number(qs, entries)
        elif match == "group":
            merge_res = DualFileMerger._merge_by_type_and_number(qs, entries)
        elif match == "order":
            merge_res = DualFileMerger._merge_by_sequence(qs, entries)
        elif match == "number-strict":
            merge_res = DualFileMerger.merge_strict_number(qs, entries)
        else:
            merge_res = DualFileMerger.merge_auto(qs, entries)
        
        final_valid = validate(merge_res.questions) + merge_res.warnings
        return cls._build_result(merge_res.questions, f"双文件合并（{merge_res.name}）", final_valid, len(q_norm) + len(a_norm), len(blocks), 1)

    @classmethod
    def _strip_wenjuanxing(cls, text: str) -> str:
        """去掉问卷星/考试星导出里的页眉页脚噪声行。"""
        noise = re.compile(
            r"^(问卷星|考试星|www\.wjx\.cn|https?://|总题数|共\s*\d+\s*题|满分[:：]|"
            r"考试时间|答题时间|您的姓名|提交时间|用时[:：])"
        )
        lines = [ln for ln in text.splitlines() if not noise.match(ln.strip())]
        return "\n".join(lines)

    @classmethod
    def _rewrite_shared_stem(cls, text: str) -> str:
        lines = text.split("\n")
        output = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r"^(?:根据|阅读)(?:以下|下列)?(?:材料|资料|图表|统计资料).*?(?:回答|完成)\s*(\d+)\s*[-~至到]\s*(\d+)\s*题", line):
                material_lines = [line]
                i += 1
                while i < len(lines) and not re.match(r"^\s*\d+\s*[.、．]", lines[i]):
                    if lines[i].strip(): material_lines.append(lines[i].strip())
                    i += 1
                material_text = " ".join(material_lines)
                
                while i < len(lines) and not lines[i].strip():
                    i += 1
                    
                while i < len(lines) and re.match(r"^\s*\d+\s*[.、．]", lines[i]):
                    m = re.match(r"^(\s*\d+\s*[.、．])\s*(.*)", lines[i])
                    output.append(f"{m.group(1)} {material_text} {m.group(2)}")
                    i += 1
                    while i < len(lines) and not re.match(r"^\s*\d+\s*[.、．]", lines[i]) and not re.match(r"^(?:根据|阅读)", lines[i]):
                        output.append(lines[i])
                        i += 1
            else:
                output.append(lines[i])
                i += 1
        return "\n".join(output)

    @classmethod
    def _extract_answer_section(cls, text: str) -> tuple[list, str]:
        lines = text.split("\n")
        ans_start = -1
        for i, line in enumerate(lines):
            sec = SectionTitleParser.parse(line)
            if sec and sec.is_answer_section:
                ans_start = i
                break
                
        if ans_start >= 0:
            q_text = "\n".join(lines[:ans_start])
            a_text = "\n".join(lines[ans_start+1:])
            return QuestionBlockSplitter.split(q_text), a_text
            
        return QuestionBlockSplitter.split(text), ""

    @classmethod
    def _build_result(cls, questions, strategy, warnings, norm_len, block_count, candidate_count) -> ImportResult:
        # 导入时不做自动去重，完全还原原版行为
        ans_count = sum(1 for q in questions if q.answer)
        return ImportResult(
            questions=questions,
            strategyName=strategy,
            warnings=warnings,
            diagnostics=ImportDiagnostics(
                normalizedLength=norm_len,
                blockCount=block_count,
                answeredCount=ans_count,
                candidateCount=candidate_count,
                notes=[f"题型分布：共{len(questions)}题，有答案{ans_count}题"]
            )
        )

    @classmethod
    def _empty_result(cls) -> ImportResult:
        return ImportResult(questions=[], strategyName="空文本", warnings=[], diagnostics=ImportDiagnostics())
