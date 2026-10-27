# quiz_parser/excel.py
import csv
import io
import re
from .models import Question, Option, QuestionType
from .answer_token import AnswerTokenParser
from .multiblank import MultiBlankQuestionParser
from .base import QuestionTypeLabelParser, QuestionTextNormalizer

class ExcelQuestionTableParser:
    # 无表头时，只有“列数够整齐”才当成表格；否则交回文本解析器
    _TABULAR_MIN_COLS = 5
    _TABULAR_MIN_RATIO = 0.8

    @classmethod
    def parse(cls, text: str) -> list[Question]:
        rows = cls._read_rows(text)
        if not rows:
            return []

        questions = []
        mapping = cls._find_mapping(rows)

        if mapping and mapping.get("header_idx", -1) >= 0:
            start_idx = mapping["header_idx"] + 1
            for row in rows[start_idx:]:
                if not row or not row[0]: continue
                if row[0].lower() == "title": continue
                q = cls._parse_row(row, mapping, len(questions) + 1)
                if q: questions.append(q)
            return questions

        # 没有表头：必须是像样的表格才继续，否则让位给普通文本解析
        if not cls._looks_tabular(rows):
            return []

        for row in rows:
            if not row or len(row) < 3: continue

            is_tail_number_format = (
                row[-1].isdigit() and
                len(row) >= 5 and
                not (re.fullmatch(r"[A-Ha-h]{1,7}", row[-2]) or row[-2] in ("正确", "错误"))
            )

            if is_tail_number_format:
                q = cls._parse_from_tail(row, len(questions) + 1)
            else:
                q = cls._parse_from_head(row, len(questions) + 1)

            if q: questions.append(q)

        return questions

    # ── 行拆分：对齐 Kotlin 的 parseDelimitedRows ──────────────────────────
    @classmethod
    def _read_rows(cls, text: str) -> list[list[str]]:
        """两种拆法都算，再挑更可信的一份：

        1. 全文件 CSV：能正确支持跨行引号字段（一份题库里常有无引号的解析列混排）
        2. 逐行拆分：对齐 Kotlin 的 parseDelimitedRows，能吃掉坏引号 / TSV / 多空格表

        选择规则：谁找到表头就信谁；都没有表头时，挑列数更整齐的那份。
        注意不能只看 strict 是否通过——只有个别引号不规范时，全局非严格解析
        依然是正确的，退化成逐行反而会把列冲散。
        """
        global_rows = None
        try:
            parsed = csv.reader(io.StringIO(text), delimiter=",")
            global_rows = [
                [cls._cleanup_cell(c) for c in row]
                for row in parsed
                if row and any(c.strip() for c in row)
            ]
        except csv.Error:
            global_rows = None

        lines = [line.rstrip() for line in text.split("\n")]
        lines = [line for line in lines if line.strip()]
        line_rows = cls._parse_line_rows(lines)

        if global_rows:
            mapping = cls._find_mapping(global_rows)
            if mapping and mapping.get("header_idx", -1) >= 0:
                return global_rows
        mapping_line = cls._find_mapping(line_rows)
        if mapping_line and mapping_line.get("header_idx", -1) >= 0:
            return line_rows

        if cls._consistency(global_rows) >= cls._consistency(line_rows):
            return global_rows or []
        return line_rows

    @classmethod
    def _parse_line_rows(cls, lines: list[str]) -> list[list[str]]:
        rows = []
        for line in lines:
            if "\t" in line:
                cells = line.split("\t")
            elif cls._looks_like_csv_line(line):
                # 单行里引号不闭合（脏数据常见）时先把引号去掉再切
                fixed = line.replace('"', "") if line.count('"') % 2 else line
                try:
                    cells = next(csv.reader(io.StringIO(fixed), delimiter=","))
                except (csv.Error, StopIteration):
                    cells = fixed.split(",")
            else:
                cells = re.split(r"\s{2,}", line)
            rows.append([cls._cleanup_cell(c) for c in cells])
        return rows

    @staticmethod
    def _looks_like_csv_line(line: str) -> bool:
        if "," not in line:
            return False
        comma_count = line.count(",")
        chinese_comma_count = line.count("，")
        return comma_count >= chinese_comma_count and comma_count >= 2

    _FULLWIDTH = str.maketrans({chr(0xFF01 + i): chr(0x21 + i) for i in range(94)})
    _EXTRA_PUNCT = str.maketrans({
        "【": "[", "】": "]", "✔": "√", "✅": "√", "☑": "√",
        "✘": "×", "✖": "×", "❌": "×", "❎": "×",
    })

    @classmethod
    def _normalize_cell(cls, text: str) -> str:
        """逐格标准化：字符映射与 QuestionTextNormalizer 一致，但不做整段行扫描。"""
        if not text:
            return ""
        if "\uFEFF" in text or "\uFE0F" in text:
            text = text.replace("\uFEFF", "").replace("\uFE0F", "")
        if "\r" in text:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        if "\u3000" in text:
            text = text.replace("\u3000", " ")
        text = text.translate(cls._FULLWIDTH).translate(cls._EXTRA_PUNCT)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def _cleanup_cell(raw: str) -> str:
        text = raw.strip()
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]
        text = text.replace("\\n", "\n").replace("_x000D_", "\n")
        # 切列后才做逐格标准化（对齐 Web 版），避免全角标点被当成分隔符
        return ExcelQuestionTableParser._normalize_cell(text)

    @classmethod
    def _consistency(cls, rows) -> float:
        """出现最多的列数占比；空表返回 0。"""
        if not rows:
            return 0.0
        counts = [len(r) for r in rows if r]
        if not counts:
            return 0.0
        best = max(set(counts), key=counts.count)
        return counts.count(best) / len(counts)

    @classmethod
    def _looks_tabular(cls, rows) -> bool:
        if not rows:
            return False
        counts = [len(r) for r in rows if r]
        if not counts:
            return False
        best = max(set(counts), key=counts.count)
        return best >= cls._TABULAR_MIN_COLS and (counts.count(best) / len(counts)) >= cls._TABULAR_MIN_RATIO

    @classmethod
    def _find_mapping(cls, rows):
        for i, row in enumerate(rows[:10]):
            mapping = {"header_idx": i, "num": -1, "type": -1, "stem": -1, "opts": {}, "ans": -1, "ana": -1, "cat": -1}
            for j, cell in enumerate(row):
                c = cell.lower().replace(" ", "").replace("\n", "")
                if c in ("题号", "序号", "no", "number", "num", "id"): 
                    if mapping["num"] == -1 or c in ("题号", "序号"):
                        mapping["num"] = j
                elif c in ("题型", "类型", "questiontype", "type", "kind"): mapping["type"] = j
                elif c in ("题干", "题目", "问题", "question", "stem", "title", "题目内容", "内容"): mapping["stem"] = j
                elif c in ("答案", "正确答案", "参考答案", "标准答案", "答", "answer", "correctanswer", "rightanswer", "standardanswer"): mapping["ans"] = j
                elif c in ("解析", "答案解析", "说明", "解题思路", "analysis", "explanation", "explain"): mapping["ana"] = j
                elif c in ("分类", "分组", "章节", "标签", "来源", "category", "group", "topic", "section"): mapping["cat"] = j
                elif re.match(r"^(?:option|choice|选项)?([a-h])(?:选项|项)?$", c): 
                    key = c[-1] if c[-1] in "abcdefgh" else c[1]
                    mapping["opts"][key] = j
            
            if mapping["stem"] >= 0 and (mapping["ans"] >= 0 or mapping["opts"]):
                return mapping
        return None

    @classmethod
    def _parse_from_tail(cls, row: list[str], fallback_num: int) -> Question | None:
        num = row[-1].strip()
        if not num.isdigit(): num = str(fallback_num)
            
        raw_ans = ""
        ans_idx = -1
        for idx in range(1, min(7, len(row) - 1)):
            val = row[idx].strip().upper()
            if re.fullmatch(r"[A-H]{1,7}", val) or val in ("正确", "错误", "对", "错"):
                raw_ans = val
                ans_idx = idx
                break
                
        if ans_idx == -1:
            if len(row) > 1:
                raw_ans = row[1]
                ans_idx = 1
            else:
                return None

        ana = ",".join(row[:ans_idx]).strip()
        remainder_text = ",".join(row[ans_idx+1:-1]).strip()
        
        if re.search(r"(?:^|[\s，,])([A-D])[\.．、]\s*\S", remainder_text):
            opts = []
            opt_matches = list(re.finditer(r"(?:^|[\s，,])([A-H])[\.．、]\s*([^A-H]+?)(?=(?:[\s，,][A-H][\.．、])|$)", remainder_text))
            if opt_matches:
                stem_parts = []
                last_end = 0
                for m in opt_matches:
                    if m.start() > last_end:
                        stem_parts.append(remainder_text[last_end:m.start()].strip(" ,，"))
                    key = m.group(1).upper()
                    val = m.group(2).strip(" ,，")
                    opts.append(Option(key, val))
                    last_end = m.end()
                if last_end < len(remainder_text):
                    stem_parts.append(remainder_text[last_end:].strip(" ,，"))
                
                stem = "".join(stem_parts).strip(" ,，")
                stem = re.sub(r'[,，\s]*\d+$', '', stem).strip()
                
                if stem and len(opts) >= 2:
                    return cls._build_question(row, num, stem, raw_ans, ana, opts)

        stem = row[-2].strip()
        opts = []
        opt_start = ans_idx + 1
        if opt_start < len(row) - 2 and row[opt_start].isdigit():
            opt_start += 1
        for i in range(opt_start, len(row) - 2):
            val = row[i].strip()
            if val:
                val = re.sub(r"^[A-Ha-h]\s*[.、．:：)）]\s*", "", val)
                key = chr(ord('A') + len(opts))
                opts.append(Option(key, val))
                
        if not stem or len(stem) < 2: return None
        return cls._build_question(row, num, stem, raw_ans, ana, opts)

    @classmethod
    def _parse_from_head(cls, row: list[str], fallback_num: int) -> Question | None:
        if row[0].isdigit() and len(row) > 1:
            num = row[0]
            start_col = 1
        else:
            num = str(fallback_num)
            start_col = 0
            
        if len(row) <= start_col + 1: return None
        
        stem = row[start_col].strip()
        if not stem: return None
        
        raw_ans = row[-1].strip()
        if not (re.fullmatch(r"[A-Ha-h]{1,7}", raw_ans) or raw_ans in ("正确", "错误", "对", "错", "√", "×")):
            if len(row) > 2 and (re.fullmatch(r"[A-Ha-h]{1,7}", row[-2].strip()) or row[-2].strip() in ("正确", "错误")):
                raw_ans = row[-2].strip()
                opt_end = -2
            else:
                raw_ans = ""
                opt_end = -1
        else:
            opt_end = -1
            
        opts = []
        for i in range(start_col + 1, len(row) + opt_end):
            val = row[i].strip()
            if val:
                val = re.sub(r"^[A-Ha-h]\s*[.、．:：)）]\s*", "", val)
                key = chr(ord('A') + len(opts))
                opts.append(Option(key, val))
                
        return cls._build_question(row, num, stem, raw_ans, "", opts)

    @classmethod
    def _build_question(cls, row, num, stem, raw_ans, ana, opts) -> Question:
        q_type = QuestionType.SINGLE
        ans = AnswerTokenParser.parse_objective_answers(raw_ans, [o.key for o in opts])
        
        if not opts and AnswerTokenParser.is_judge_answer_text(raw_ans):
            q_type = QuestionType.JUDGE
            ans = AnswerTokenParser.parse_judge_answer(raw_ans)
            opts = [Option("A", "正确"), Option("B", "错误")]
        elif not opts and len(raw_ans) > 2:
            q_type = QuestionType.SHORT
            
        mb = MultiBlankQuestionParser.extract(stem, q_type, opts, raw_ans, ans)
        return Question(
            number=str(num), type=q_type, question=mb.question_text,
            options=opts, answer=mb.answer, blankAnswers=mb.blank_answers,
            analysis=ana
        )

    @classmethod
    def _parse_row(cls, row, mapping, fallback_num):
        def cell(idx): return row[idx] if 0 <= idx < len(row) else ""
        stem = cell(mapping["stem"])
        if not stem: return None
        
        num = cell(mapping["num"]) or str(fallback_num)
        cat = cell(mapping["cat"])
        ana = cell(mapping["ana"])
        raw_ans = cell(mapping["ans"])
        
        # 保险机制：如果按表头提取不到答案，强行在这一行里找合法答案
        if not raw_ans:
            for cell_val in row:
                val = cell_val.strip().upper()
                if re.fullmatch(r"[A-H]{1,7}", val) or val in ("正确", "错误", "对", "错"):
                    raw_ans = val
                    break
        
        opts = []
        for k, idx in mapping["opts"].items():
            val = cell(idx)
            val = re.sub(r"^[A-Ha-h]\s*[.、．:：)）]\s*", "", val)
            if val: opts.append(Option(k.upper(), val))
                
        q_type = QuestionTypeLabelParser.parse_label(cell(mapping["type"])) or QuestionType.SINGLE
        
        ans = AnswerTokenParser.parse_objective_answers(raw_ans, [o.key for o in opts])
        
        if not opts and AnswerTokenParser.is_judge_answer_text(raw_ans):
            q_type = QuestionType.JUDGE
            ans = AnswerTokenParser.parse_judge_answer(raw_ans)
            opts = [Option("A", "正确"), Option("B", "错误")]
        elif not opts and len(raw_ans) > 2:
            q_type = QuestionType.SHORT
            
        mb = MultiBlankQuestionParser.extract(stem, q_type, opts, raw_ans, ans)
        return Question(
            number=str(num), type=q_type, question=mb.question_text,
            options=opts, answer=mb.answer, blankAnswers=mb.blank_answers,
            analysis=ana, category=cat
        )