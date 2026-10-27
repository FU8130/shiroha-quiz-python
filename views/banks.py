# -*- coding: utf-8 -*-
"""题库管理、导入解析、导出与编辑。"""
import csv
import hashlib
import json
import logging
import os
import pickle
import random
import re
import sys
from datetime import datetime
import time
import traceback
import shutil
from pathlib import Path

from quiz_parser.models import Option, Question, QuestionType
from quiz_parser.quiz_parser import QuizImportParser
from quiz_parser.validator import dedupe_questions, validate

from core.paths import (
    BANK_COUNTS_FILE, BANKS_DIR, BASE_DIR, CACHE_DIR, DATA_DIR,
    STATE_FILE, bank_abs_path, bank_rel_key,
)
from core.ui import ask, clear_screen, cyan, dim, green, red, yellow

logger = logging.getLogger("quiz.banks")


TYPE_ALIASES = {
    "single": QuestionType.SINGLE, "singlechoice": QuestionType.SINGLE, "单选": QuestionType.SINGLE,
    "multiple": QuestionType.MULTIPLE, "multiplechoice": QuestionType.MULTIPLE, "多选": QuestionType.MULTIPLE,
    "judge": QuestionType.JUDGE, "truefalse": QuestionType.JUDGE, "判断": QuestionType.JUDGE,
    "blank": QuestionType.BLANK, "fill": QuestionType.BLANK, "填空": QuestionType.BLANK,
    "short": QuestionType.SHORT, "essay": QuestionType.SHORT, "简答": QuestionType.SHORT,
}

class BanksMixin:

    def _bank_digest(self, path_obj):
        try:
            return hashlib.sha256(Path(path_obj).read_bytes()).hexdigest()
        except Exception:
            return ""

    def _parse_bank(self, path_str, silent=False, mode="auto", strategy="auto"):
        path_obj = Path(path_str).resolve()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            stat = path_obj.stat()
            cache_hash = hashlib.md5(f"{path_obj.name}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()
            cache_file = CACHE_DIR / f"{cache_hash}.pkl"

            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        result = pickle.load(f)
                    self._install_bank(path_obj, result)
                    if not silent:
                        print(f"⚡ 已从缓存秒开题库: {self.bank_name} (共 {len(self.questions)} 题)")
                    self._note_bank_hash(self.bank_key, self._bank_digest(path_obj))
                    self._adopt_bank_state()
                    self._cleanup_records()
                    return True
                except Exception:
                    pass

            if not silent:
                print("⏳ 正在解析题库，请稍候...")
            text = read_text_auto(path_obj)
            if path_obj.suffix.lower() == ".json" or mode == "json":
                result = self._parse_json_bank(text, path_obj)
            else:
                result = QuizImportParser.parse_standard_text(text, mode=mode, strategy=strategy)

            self._install_bank(path_obj, result)
            self._note_bank_hash(self.bank_key, self._bank_digest(path_obj))
            if not self.questions:
                if path_obj.stat().st_size == 0 or not text.strip():
                    if not silent:
                        print("📄 空题库已载入：进入「题库管理 → 编辑题目」，按 a 新增题目")
                    self._adopt_bank_state()
                    self.save_state()
                    return True
                if not silent:
                    print("❌ 解析失败，没有识别到任何题目。")
                return False

            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
            except Exception as e:
                logger.warning(f"缓存保存失败: {e}")

            if not silent:
                if not self._print_import_summary():
                    self.questions = []
                    self.bank_key = ""
                    self.bank_path = ""
                    self.bank_name = ""
                    print("已取消导入。")
                    return False
                if getattr(self, "_import_dirty", False):
                    if self._save_bank_file(bank_abs_path(str(path_obj)), self.questions):
                        print(green("✅ 查找替换已写回题库文件"))
            self._adopt_bank_state()
            self._cleanup_records()
            return True
        except Exception as e:
            logger.error(traceback.format_exc())
            if not silent:
                print(f"❌ 解析出错: {e}")
            return False

    def _install_bank(self, path_obj, result):
        self.questions = result.questions
        self.bank_name = path_obj.name
        self.bank_path = bank_rel_key(path_obj)
        self.bank_key = self.bank_path
        self.current_idx = 0
        self._last_strategy = getattr(result, "strategyName", "")
        try:
            _remember_bank_count(self.bank_key, len(self.questions))
        except Exception:
            pass

    def _print_import_summary(self):
        """导入预览：统计 + 预览 + 工具（筛选 / 查找替换）+ 确认。"""
        self._import_dirty = False
        keyword = ""
        status_filter = "priority"
        while True:
            clear_screen()
            print(f"✅ 解析完成: {self.bank_name}")
            print(f"   解析策略: {getattr(self, '_last_strategy', '') or '普通解析'}")
            singles = sum(1 for q in self.questions if q.type == QuestionType.SINGLE)
            multiples = sum(1 for q in self.questions if q.type == QuestionType.MULTIPLE)
            judges = sum(1 for q in self.questions if q.type == QuestionType.JUDGE)
            others = len(self.questions) - singles - multiples - judges
            print(f"   [题型] 单选:{singles} 多选:{multiples} 判断:{judges} 主观/填空:{others}")
            warnings = validate(self.questions)
            if warnings:
                print(f"   [⚠️] 发现 {len(warnings)} 处异常，前 3 条：")
                for w in warnings[:3]:
                    print(f"      - 第 {w.questionNumber} 题: {w.message}")
            else:
                print("   [✨] 所有题目结构完整")

            items = self.questions
            if status_filter != "all":
                problem_nums = {str(w.questionNumber) for w in warnings if w.questionNumber}
                if status_filter == "priority":
                    items = sorted(items, key=lambda q: 0 if str(q.number) in problem_nums else 1)
                elif status_filter == "problem":
                    items = [q for q in items if str(q.number) in problem_nums]
                else:
                    items = [q for q in items if str(q.number) not in problem_nums]
                print(f"\n状态筛选（{'仅异常' if status_filter == 'problem' else '仅正常'}）命中 {len(items)} 题")
            if keyword:
                items = [q for q in items
                         if keyword in q.question or keyword in (q.analysis or "")
                         or any(keyword in o.text for o in q.options)]
                print(f"\n筛选「{keyword}」命中 {len(items)} 题")
            print("\n预览：")
            for q in items[:5]:
                print(f"  {q.number}. {q.question[:36]}")
                if q.options:
                    print("     " + "  ".join(f"{o.key}.{o.text[:12]}" for o in q.options[:4]))
                print(f"     {dim('答案:')} {''.join(q.answer) or '—'}")
            if len(items) > 5:
                print(f"     …… 共 {len(items)} 题")
            print("\n[f]筛选预览  [s]状态筛选  [v]重新校验  [r]查找替换  [d]批量删除")
            print("[y]确认导入  [n]取消  (默认 y)")
            cmd = ask("> ").strip().lower() or "y"
            if cmd == "f":
                keyword = ask("关键词（回车清除）: ").strip()
                continue
            if cmd == "r":
                self._import_find_replace()
                continue
            if cmd == "d":
                self._import_batch_delete(items)
                continue
            if cmd == "s":
                m = ask("状态 [1]异常优先 [2]仅异常 [3]仅正常 [4]全部 (默认1): ").strip() or "1"
                status_filter = {"1": "priority", "2": "problem", "3": "normal", "4": "all"}.get(m, "priority")
                continue
            if cmd == "v":
                w2 = validate(self.questions)
                print(f"  重新校验：{len(self.questions)} 题，异常 {len(w2)} 处")
                for w in w2[:5]:
                    print(f"    - 第 {w.questionNumber} 题: {w.message}")
                ask("  按回车继续...")
                continue
            return cmd != "n"

    def _import_batch_delete(self, items):
        """按预览里的序号批量删除题目（可写 1,3,5-7）。"""
        raw = ask("  删除哪些题（序号，如 1,3,5-7）: ").strip()
        if not raw:
            return
        picks = self._parse_pick(raw, len(items))
        if not picks:
            print("  序号无效")
            ask("  按回车继续...")
            return
        doomed = {id(items[i - 1]) for i in picks}
        before = len(self.questions)
        self.questions = [q for q in self.questions if id(q) not in doomed]
        self._import_dirty = True
        print(f"  已删除 {before - len(self.questions)} 题，剩余 {len(self.questions)} 题")
        ask("  按回车继续...")

    def _import_find_replace(self):
        old = ask("  查找: ").strip()
        if not old:
            return
        new = ask("  替换为: ").strip()
        count = 0
        for q in self.questions:
            if old in q.question:
                q.question = q.question.replace(old, new)
                count += 1
            if old in (q.analysis or ""):
                q.analysis = q.analysis.replace(old, new)
                count += 1
            for o in q.options:
                if old in o.text:
                    o.text = o.text.replace(old, new)
                    count += 1
        self._import_dirty = count > 0
        print(f"  已替换 {count} 处")
        ask("  按回车继续...")

    def _parse_json_bank(self, text, path_obj):
        """真正的 JSON 题库导入（CLI 之前把 .json 当文本，会解析出垃圾）。"""
        from quiz_parser.models import ImportResult, ImportDiagnostics
        data = json.loads(text)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get("banks"), list):
            # 原仓库「导出选中题库」：{app, exportType, banks:[{name, questions:[...]}]}
            items = []
            for bank in data["banks"]:
                if isinstance(bank, dict):
                    items.extend(bank.get("questions") or [])
        elif isinstance(data, dict):
            items = data.get("questions") or data.get("items") or []
        else:
            items = []
        questions = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            stem = str(item.get("question") or item.get("title") or item.get("stem") or "").strip()
            if not stem:
                continue
            raw_type = str(item.get("type") or "").strip()
            q_type = TYPE_ALIASES.get(raw_type.lower(), TYPE_ALIASES.get(raw_type, QuestionType.SINGLE))

            options = []
            raw_opts = item.get("options") or item.get("choices") or []
            if isinstance(raw_opts, dict):
                raw_opts = [{"key": k, "text": v} for k, v in raw_opts.items()]
            for idx, opt in enumerate(raw_opts):
                if isinstance(opt, dict):
                    key = str(opt.get("key") or chr(ord('A') + idx)).strip().upper()
                    val = str(opt.get("text") or opt.get("value") or "").strip()
                else:
                    val = str(opt).strip()
                    matched = re.match(r"^([A-Ha-h])\s*[.、．:：)）]\s*(.*)$", val)
                    if matched:
                        key, val = matched.group(1).upper(), matched.group(2).strip()
                    else:
                        key = chr(ord('A') + idx)
                if val:
                    options.append(Option(key, val))

            raw_ans = item.get("answer")
            if isinstance(raw_ans, list):
                answer = [str(a).strip() for a in raw_ans if str(a).strip()]
            elif raw_ans is None:
                answer = []
            else:
                answer = [str(raw_ans).strip()]

            questions.append(Question(
                number=str(item.get("number") or i + 1),
                type=q_type,
                question=stem,
                options=options,
                answer=answer,
                analysis=str(item.get("analysis") or item.get("explanation") or ""),
                category=str(item.get("category") or item.get("chapter") or ""),
            ))
        return ImportResult(
            questions=questions,
            strategyName="JSON 题库导入",
            warnings=[],
            diagnostics=ImportDiagnostics(normalizedLength=len(text), blockCount=len(questions),
                                          answeredCount=sum(1 for q in questions if q.answer), candidateCount=1),
        )

    def _ask_import_options(self):
        """导入方式：默认全自动；输入 o 再逐项指定。"""
        self._dual_match = "auto"
        ans = ask("高级选项？(回车=自动，o=手动指定): ").strip().lower()
        if ans != "o":
            return "auto", "auto", "auto"
        mode = {"1": "auto", "2": "wenjuanxing", "3": "normal", "4": "json"}.get(
            ask("导入模式 [1]自动 [2]问卷星/考试星 [3]普通题库 [4]JSON (默认1): ").strip() or "1", "auto")
        strategy = {"1": "auto", "2": "standard", "3": "volume", "4": "compact"}.get(
            ask("解析策略 [1]自动 [2]标准逐行 [3]分卷分区 [4]紧凑格式 (默认1): ").strip() or "1", "auto")
        match = {"1": "auto", "2": "group", "3": "number", "4": "number-strict", "5": "order"}.get(
            ask("双文件匹配 [1]自动 [2]分组+顺序 [3]按题号 [4]严格题号 [5]按顺序 (默认1，仅双文件用): ").strip() or "1", "auto")
        self._dual_match = match
        print(f"已选：模式={mode} 策略={strategy} 匹配={match}")
        return mode, strategy, match

    def _show_import_help(self):
        clear_screen()
        print("=" * 52)
        print("              支持的题库格式")
        print("=" * 52)
        print("【单选】")
        print("1. 下列说法正确的是？")
        print("A. 选项一")
        print("B. 选项二")
        print("答案：A")
        print()
        print("【多选】答案写多个字母，如 答案：ABD")
        print("【判断】答案写 正确/错误 或 A/B")
        print("【填空/简答】")
        print("1. 请填写关键词：____。")
        print("参考答案：题库导入")
        print("-" * 52)
        print("• 也支持 CSV/TSV 表格（表头含 title/optionA-D/answer/analysis/分类）")
        print("• 支持 JSON（本工具导出的纯数组，或原仓库的题库对象）")
        print("• 支持双文件：题目一个文件，答案另一个文件（1.B / 2.C 这种）")
        print("=" * 52)
        ask("按回车返回...")

    def _load_sample(self):
        path = BANKS_DIR / "示例题库.txt"
        if not path.exists():
            path.write_text(self.SAMPLE_TEXT, encoding="utf-8")
        return self._parse_bank(str(path))

    def _load_dual_sample(self):
        qp = BANKS_DIR / "示例题目.txt"
        ap = BANKS_DIR / "示例答案.txt"
        qp.write_text(self.DUAL_QUESTIONS, encoding="utf-8")
        ap.write_text(self.DUAL_ANSWERS, encoding="utf-8")
        result = QuizImportParser.parse_dual_text(
            qp.read_text(encoding="utf-8"), ap.read_text(encoding="utf-8"))
        self._install_bank(qp, result)
        self._last_strategy = result.strategyName
        if not self.questions:
            print("❌ 双文件示例没有解析出题目")
            ask()
            return False
        self._print_import_summary()
        self._adopt_bank_state()
        self.save_state()
        return True

    def load_bank(self):
        supported_exts = {".txt", ".csv", ".tsv", ".json"}
        bank_files = [f for f in sorted(BANKS_DIR.iterdir()) if f.is_file() and f.suffix.lower() in supported_exts]

        clear_screen()
        print("=" * 46)
        print("              📚 导入题库")
        print("=" * 46)
        if bank_files:
            for i, f in enumerate(bank_files, 1):
                print(f"  [{i}] {f.name}")
            print("  [0] 输入其它路径    [s] 内置示例    [?] 格式说明")
            print("-" * 46)
            choice = ask("请选择题库序号（回车返回）: ").strip()
            if not choice:
                return
            if choice == "?":
                self._show_import_help()
                return
            if choice.lower() == "s":
                if self._load_sample():
                    self.current_idx = 0
                    self.save_state()
                else:
                    ask("按回车返回...")
                return
            if choice == "0":
                path_str = ask("请输入题库文件路径:\n> ").strip().strip('"').strip("'")
                if not os.path.exists(path_str):
                    print("❌ 找不到该文件！"); ask(); return
            else:
                try:
                    idx = int(choice) - 1
                    if idx < 0 or idx >= len(bank_files):
                        return
                    path_str = str(bank_files[idx])
                except ValueError:
                    return
        else:
            path_str = ask("📂 banks 目录为空，请拖入文件路径:\n> ").strip().strip('"').strip("'")
            if not os.path.exists(path_str):
                print("❌ 找不到该文件！"); ask(); return

        mode, strategy, self._dual_match = self._ask_import_options()
        if path_str.lower().endswith(".json"):
            if self._parse_bank(path_str, mode=mode, strategy=strategy):
                self.current_idx = 0
                self.save_state()
            else:
                ask("按回车返回...")
            return

        # 双文件：题目 + 独立答案
        ans_path = ask("有独立的答案文件吗？(y/N，s=用内置双文件示例): ").strip().lower()
        if ans_path == "s":
            self._load_dual_sample()
            return
        if ans_path == "y":
            ans_file = ask("请输入答案文件路径:\n> ").strip().strip('"').strip("'")
            if os.path.exists(ans_file):
                q_text = read_text_auto(Path(path_str))
                a_text = read_text_auto(Path(ans_file))
                result = QuizImportParser.parse_dual_text(q_text, a_text, match=self._dual_match)
                self._install_bank(Path(path_str), result)
                self._last_strategy = result.strategyName
                if self.questions:
                    self._print_import_summary()
                    self._adopt_bank_state()
                    self._cleanup_records()
                    self.save_state()
                else:
                    print("❌ 双文件合并后没有题目。"); ask()
                return
            print("❌ 答案文件不存在，改为单文件导入。")

        if self._parse_bank(path_str, mode=mode, strategy=strategy):
            self.current_idx = 0
            self.save_state()
        else:
            ask("按回车返回...")

    def _save_bank_file(self, path, questions):
        path = Path(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                data = [{
                    "number": q.number, "type": q.type.value.lower(), "question": q.question,
                    "options": [{"key": o.key, "text": o.text} for o in q.options],
                    "answer": q.answer, "analysis": q.analysis, "category": q.category,
                    "score": q.score, "blankAnswers": q.blankAnswers,
                } for q in questions]
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            elif suffix in (".csv", ".tsv"):
                delimiter = "\t" if suffix == ".tsv" else ","
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=delimiter)
                    w.writerow(["analysis", "answer", "id", "optionA", "optionB", "optionC", "optionD", "optionE", "optionF", "optionG", "optionH", "title", "序号", "分类", "分值"])
                    for q in questions:
                        opts = {o.key: o.text for o in q.options}
                        w.writerow([q.analysis, "".join(q.answer), q.number,
                                    opts.get("A", ""), opts.get("B", ""), opts.get("C", ""), opts.get("D", ""),
                                    opts.get("E", ""), opts.get("F", ""), opts.get("G", ""), opts.get("H", ""),
                                    q.question, q.number, q.category,
                                    "" if q.score is None else q.score])
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for i, q in enumerate(questions, 1):
                        f.write(f"{i}. {q.question}\n")
                        for o in q.options:
                            f.write(f"{o.key}. {o.text}\n")
                        if q.answer:
                            f.write(f"答案：{''.join(q.answer)}\n")
                        if q.analysis:
                            f.write(f"解析：{q.analysis}\n")
                        if q.score is not None:
                            f.write(f"分值：{q.score}\n")
                        f.write("\n")
            return True
        except Exception as e:
            print(red(f"❌ 保存失败: {e}"))
            return False

    def edit_questions(self):
        if not self.questions and not self.bank_key:
            print("⚠️ 请先导入题库！")
            ask()
            return
        keyword = ""
        page = 0
        size = 12
        while True:
            pool = [q for q in self.questions
                    if not keyword or keyword in q.question or keyword in (q.category or "")]
            pages = max(1, (len(pool) + size - 1) // size)
            page = max(0, min(page, pages - 1))
            chunk = pool[page * size:(page + 1) * size]

            clear_screen()
            print("=" * 60)
            print(f"  ✏️  浏览/编辑题目   共 {len(pool)} 题   第 {page + 1}/{pages} 页")
            print("=" * 60)
            if not chunk:
                print("  （没有匹配的题目）")
            for i, q in enumerate(chunk, 1):
                tag = q.category or "未分类"
                print(f"  [{i:>2}] {str(q.number):>4}. {q.question[:34]}  {dim('[' + tag + ']')}")

            print("\n  [n]下一页 [p]上一页 [f]筛选 [g题号]跳转 [d序号]删除 [a]新增 [序号]编辑 [0]返回")
            cmd = ask("  > ").strip().lower()
            if cmd in ("0", ""):
                return
            if cmd == "n":
                page += 1
                continue
            if cmd == "p":
                page -= 1
                continue
            if cmd == "f":
                keyword = ask("  筛选关键词（题干或分类，回车清除）: ").strip()
                page = 0
                continue
            if cmd.startswith("g") and cmd[1:].isdigit():
                want = cmd[1:]
                target = None
                for i, q in enumerate(pool):
                    if str(q.number) == want:
                        target = i
                        break
                if target is None and 1 <= int(want) <= len(pool):
                    target = int(want) - 1
                if target is not None:
                    page = target // size
                continue
            if cmd == "a":
                nq = self._add_question()
                if nq is not None:
                    self.questions.append(nq)
                    if self._save_bank_file(bank_abs_path(self.bank_path), self.questions):
                        print(green(f"✅ 已新增第 {nq.number} 题并保存"))
                    else:
                        print(red("保存失败"))
                    self.save_state()
                    ask("按回车继续...")
                continue
            if cmd.startswith("d") and cmd[1:].isdigit():
                k = int(cmd[1:])
                if 1 <= k <= len(chunk):
                    q = chunk[k - 1]
                    from core.ui import danger_confirm
                    if danger_confirm(self._confirm, f"删除第 {q.number} 题「{q.question[:18]}」"):
                        self.questions.remove(q)
                        self.wrong_book = [i for i in self.wrong_book if i != q.id]
                        self.favorites = [i for i in self.favorites if i != q.id]
                        self.wrong_counts.pop(q.id, None)
                        if self._save_bank_file(bank_abs_path(self.bank_path), self.questions):
                            print(green("✅ 已删除并保存"))
                        else:
                            print(red("保存失败"))
                        self.save_state()
                        ask("按回车继续...")
                        page = 0
                continue
            if cmd.isdigit() and 1 <= int(cmd) <= len(chunk):
                q = chunk[int(cmd) - 1]
                if self._edit_one(q):
                    if self._save_bank_file(bank_abs_path(self.bank_path), self.questions):
                        print(green("✅ 已保存到题库文件"))
                    else:
                        print(red("保存失败，改动仅在本次会话有效"))
                    ask("按回车继续...")
                    return

    def _add_question(self):
        """手动新增一道题；返回 Question 或 None。"""
        import uuid
        stem = ask("  题干: ").strip()
        if not stem:
            print(dim("已取消"))
            return None
        opts = []
        for key in ("A", "B", "C", "D", "E", "F"):
            text = ask(f"  选项{key}（回车跳过）: ").strip()
            if not text:
                if key == "A":
                    continue
                break
            opts.append(Option(key, text))
        ans = ask("  答案（字母，如 B 或 ABD）: ").strip().upper()
        ana = ask("  解析（回车跳过）: ").strip()
        cat = ask("  分类（回车跳过）: ").strip()
        number = max((q.number for q in self.questions), default=0) + 1
        return Question(
            number=number,
            id=str(uuid.uuid4()),
            question=stem,
            options=opts,
            answer=list(ans) if ans else [],
            analysis=ana,
            category=cat,
        )

    def _edit_one(self, q):
        """编辑单题；返回 True 表示有改动需要保存。"""
        changed = False
        while True:
            clear_screen()
            print("=" * 50)
            print(f"  编辑题目 {q.number}   分类: {q.category or '未分类'}")
            print("=" * 50)
            print(f"  1. 题干: {q.question}")
            for o in q.options:
                print(f"     {o.key.lower()}) 选项{o.key}: {o.text}")
            print(f"  2. 答案: {''.join(q.answer) or '(空)'}")
            print(f"  3. 解析: {(q.analysis or '(空)')[:60]}")
            print(f"  4. 分类: {q.category or '(空)'}")
            print(f"  6. 分值: {q.score if q.score is not None else '(默认)'}")
            blanks = "；".join("/".join(b) for b in (q.blankAnswers or []))
            print(f"  7. 多空答案: {blanks or '(空)'}")
            print("  8. 新增一个题空     9. 题型: %s" % q.type.value)
            print("\n  0 取消   5 保存此题的改动   m 关闭多空")
            choice = ask("  选择要修改的项 > ").strip().lower()

            if choice == "0":
                return False
            if choice == "5":
                return changed
            if choice == "1":
                val = ask("  新题干（回车不变）: ").strip()
                if val and val != q.question:
                    q.question = val
                    changed = True
            elif choice == "2":
                val = ask("  新答案（字母，如 B 或 ABD；回车不变）: ").strip().upper()
                if val:
                    q.answer = list(val) if re.fullmatch(r"[A-H]{1,7}", val) else [val]
                    changed = True
            elif choice == "3":
                val = ask("  新解析（回车不变）: ").strip()
                if val and val != q.analysis:
                    q.analysis = val
                    changed = True
            elif choice == "4":
                val = ask("  新分类/章节（回车不变）: ").strip()
                if val != q.category:
                    q.category = val
                    changed = True
            elif choice == "6":
                val = ask("  分值（数字，输入 -1 清除，回车不变）: ").strip()
                if val:
                    try:
                        num = float(val)
                        q.score = None if num < 0 else num
                        changed = True
                    except ValueError:
                        print("  分值必须是数字")
                        ask("  按回车继续...")
            elif choice == "9":
                print("  1 单选  2 多选  3 判断  4 填空  5 简答")
                m = ask("  新题型 (回车不变): ").strip()
                mapping = {"1": QuestionType.SINGLE, "2": QuestionType.MULTIPLE,
                           "3": QuestionType.JUDGE, "4": QuestionType.BLANK, "5": QuestionType.SHORT}
                if m in mapping:
                    q.type = mapping[m]
                    changed = True
            elif choice == "m":
                if q.blankAnswers:
                    q.blankAnswers = []
                    changed = True
                    print("  已关闭多空模式")
                    ask("  按回车继续...")
            elif choice == "8":
                q.blankAnswers = list(q.blankAnswers or []) + [[]]
                q.type = QuestionType.BLANK
                changed = True
                print(f"  已新增第 {len(q.blankAnswers)} 个空（用 7 填答案）")
                ask("  按回车继续...")
            elif choice == "7":
                tip = "  多空答案，空与空用逗号，同一空的多个答案用 |（如：A|a, B），回车不变: "
                val = ask(tip).strip()
                if val:
                    groups = []
                    for part in val.replace("，", ",").split(","):
                        part = part.strip()
                        if part:
                            groups.append([x.strip() for x in part.split("|") if x.strip()])
                    if groups:
                        q.blankAnswers = groups
                        q.type = QuestionType.BLANK
                        changed = True
            elif choice in tuple("abcdefgh"):
                target = choice.upper()
                opt = next((o for o in q.options if o.key == target), None)
                cur = opt.text if opt else ""
                val = ask(f"  选项 {target} 新内容（回车不变，输入 - 删除该选项）: ").strip()
                if val == "-" and opt:
                    q.options.remove(opt)
                    changed = True
                elif val and val != cur:
                    if opt:
                        opt.text = val
                    else:
                        q.options.append(Option(target, val))
                        q.options.sort(key=lambda o: o.key)
                    changed = True

    @staticmethod
    def _question_to_web(q):
        """转成原前端认的题目结构（type 小写 + options 数组）。"""
        return {
            "id": q.id,
            "number": str(q.number),
            "type": q.type.value.lower(),
            "question": q.question,
            "options": [{"key": o.key, "text": o.text} for o in q.options],
            "answer": list(q.answer),
            "analysis": q.analysis or "",
            "category": q.category or "",
            "score": q.score,
            "blankAnswers": q.blankAnswers or [],
        }

    def _export_one(self, src, fmt, out_dir, stamp, compat=None):
        if compat is None:
            compat = (fmt == "4")
        res = QuizImportParser.parse_standard_text(read_text_auto(src))
        qs = res.questions
        if not qs:
            print(red(f"  {src.name}: 没有解析出题目，跳过"))
            return 0

        if fmt in ("1", "4"):
            path = out_dir / f"{src.stem}_{stamp}.json"
            if compat:
                payload = {
                    "app": "Shiroha Quiz",
                    "exportType": "question_banks",
                    "exportedAt": datetime.now().isoformat(timespec="seconds"),
                    "banks": [{
                        "id": src.stem,
                        "name": src.stem,
                        "questions": [self._question_to_web(q) for q in qs],
                    }],
                    "activeBankId": src.stem,
                }
            else:
                payload = [self._question_to_web(q) for q in qs]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        elif fmt == "2":
            path = out_dir / f"{src.stem}_{stamp}.csv"
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["analysis", "answer", "id", "optionA", "optionB", "optionC", "optionD", "optionE", "optionF", "optionG", "optionH", "title", "序号", "分类"])
                for q in qs:
                    opts = {o.key: o.text for o in q.options}
                    w.writerow([q.analysis, "".join(q.answer), q.number,
                                opts.get("A", ""), opts.get("B", ""), opts.get("C", ""), opts.get("D", ""),
                                opts.get("E", ""), opts.get("F", ""), opts.get("G", ""), opts.get("H", ""),
                                q.question, q.number, q.category])
        elif fmt == "3":
            path = out_dir / f"{src.stem}_{stamp}.txt"
            with open(path, "w", encoding="utf-8") as f:
                for i, q in enumerate(qs, 1):
                    f.write(f"{i}. {q.question}\n")
                    for o in q.options:
                        f.write(f"{o.key}. {o.text}\n")
                    if q.answer:
                        f.write(f"答案：{''.join(q.answer)}\n")
                    if q.analysis:
                        f.write(f"解析：{q.analysis}\n")
                    f.write("\n")

        print(f"  ✅ {src.name}: {len(qs)} 题 → {path.name}")
        return len(qs)

    def export_bank(self, bank_files):
        if not bank_files:
            print("没有可导出的题库")
            ask()
            return
        for i, f in enumerate(bank_files, 1):
            print(f"  [{i}] {f.name}")
        print("  [0] 全部题库")
        idx = ask("导出哪个题库 (0=全部): ").strip()
        if not idx.isdigit():
            return
        if int(idx) == 0:
            targets = list(bank_files)
        elif 1 <= int(idx) <= len(bank_files):
            targets = [bank_files[int(idx) - 1]]
        else:
            return

        fmt = ask("格式: [1]JSON(纯题目数组，快)  [2]CSV  [3]TXT  [4]JSON(兼容原仓库) (默认1): ").strip() or "1"
        compat = (fmt == "4")
        out_dir = BASE_DIR / "exports"
        out_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        done = 0
        for src in targets:
            try:
                if self._export_one(src, fmt, out_dir, stamp, compat=compat):
                    done += 1
            except Exception as e:
                print(red(f"  {src.name} 导出失败: {e}"))
        print(green(f"✅ 完成：{done} 个题库 → {out_dir}"))
        ask()

    def manage_banks(self):
        supported_exts = {".txt", ".csv", ".tsv", ".json"}
        sort_mode = "created"

        while True:
            bank_files = [f for f in BANKS_DIR.iterdir() if f.is_file() and f.suffix.lower() in supported_exts]
            if sort_mode == "size":
                bank_files.sort(key=lambda f: -f.stat().st_size)
            elif sort_mode == "created":
                bank_files.sort(key=lambda f: f.stat().st_ctime)
            elif sort_mode == "count":
                counts = _load_bank_counts()
                bank_files.sort(key=lambda f: -counts.get(bank_rel_key(f), 0))
            elif sort_mode == "time":
                bank_files.sort(key=lambda f: -f.stat().st_mtime)
            else:
                bank_files.sort(key=lambda f: f.name)
            clear_screen()
            print("=" * 46)
            print("              📁 题库管理")
            print("=" * 46)
            if bank_files:
                for i, f in enumerate(bank_files, 1):
                    mark = " (当前)" if self.bank_key and bank_rel_key(f) == self.bank_key else ""
                    print(f"  [{i}] {f.name}{green(mark)}")
            else:
                print("  (banks 目录为空)")
            print("\n[1] 合并去重  [2] 重命名  [3] 删除  [4] 导出题库  [5] 编辑题目")
            print("[6] 复制题库  [7] 新建空库  [s] 排序(当前:%s)  [0] 返回" % {"name": "名称", "size": "大小", "time": "时间", "count": "题量", "created": "创建时间"}[sort_mode])
            choice = ask("请选择: ").strip()

            if choice == "0" or not choice:
                return
            if choice == "4":
                self.export_bank(bank_files)
                continue
            if choice == "5":
                self.edit_questions()
                continue
            if choice == "6":
                if not bank_files:
                    print("⚠️ banks 目录为空")
                    ask()
                    continue
                idx = ask("复制哪个题库（序号）: ").strip()
                if not idx.isdigit() or not (1 <= int(idx) <= len(bank_files)):
                    continue
                src = bank_files[int(idx) - 1]
                name = ask("新题库名（回车=原名_副本）: ").strip() or f"{src.stem}_副本"
                dst = BANKS_DIR / f"{name}{src.suffix}"
                if dst.exists():
                    print("⚠️ 同名题库已存在")
                    ask()
                    continue
                shutil.copyfile(src, dst)
                print(green(f"✅ 已复制为 {dst.name}"))
                ask()
                continue
            if choice == "s":
                m = ask("排序 [1]创建时间 [2]名称 [3]题量 [4]修改时间 [5]文件大小: ").strip()
                sort_mode = {"1": "created", "2": "name", "3": "count", "4": "time", "5": "size"}.get(m, sort_mode)
                continue
            if choice == "7":
                name = ask("新空题库名（回车取消）: ").strip()
                if not name:
                    continue
                dst = BANKS_DIR / f"{name}.txt"
                if dst.exists():
                    print("⚠️ 同名题库已存在")
                    ask()
                    continue
                dst.write_text("", encoding="utf-8")
                print(green(f"✅ 已创建空题库 {dst.name}"))
                print(dim("导入它之后，在「编辑题目」里按 a 新增题目"))
                ask()
                continue
            if choice == "1":
                if len(bank_files) < 2:
                    print("⚠️ 少于两个题库无法合并。"); ask(); continue
                seq = ask("要合并的序号(逗号分隔，如 1,2): ").strip()
                try:
                    indices = [int(x.strip()) - 1 for x in seq.split(",") if x.strip()]
                except ValueError:
                    print("❌ 序号无效"); ask(); continue
                merged = []
                for i in indices:
                    if 0 <= i < len(bank_files):
                        print(f"正在读取 {bank_files[i].name}...")
                        res = QuizImportParser.parse_standard_text(read_text_auto(bank_files[i]))
                        merged.extend(res.questions)
                if not merged:
                    print("❌ 读取失败。"); ask(); continue
                final_qs = dedupe_questions(merged)
                removed = len(merged) - len(final_qs)
                name = ask("新题库文件名(无需后缀，回车=自动): ").strip() or f"合并_{datetime.now().strftime('%m%d_%H%M')}"
                out_path = BANKS_DIR / f"{name}.txt"
                with open(out_path, "w", encoding="utf-8") as f:
                    for q in final_qs:
                        f.write(f"{q.number}. {q.question}\n")
                        for opt in q.options:
                            f.write(f"{opt.key}. {opt.text}\n")
                        f.write(f"答案：{''.join(q.answer)}\n\n")
                print(f"✅ 合并完成：{len(final_qs)} 题，去重 {removed} 题 → {out_path.name}")
                ask(); continue

            if choice == "2":
                idx = ask("要重命名的序号: ").strip()
                if not idx.isdigit():
                    continue
                i = int(idx) - 1
                if 0 <= i < len(bank_files):
                    new_name = ask("新文件名(无需后缀): ").strip()
                    if not new_name:
                        continue
                    target = bank_files[i].parent / f"{new_name}{bank_files[i].suffix}"
                    old_path = bank_rel_key(bank_files[i])
                    bank_files[i].rename(target)
                    if self.bank_key == old_path:
                        self.bank_path = bank_rel_key(target)
                        self.bank_key = self.bank_path
                        self.bank_name = target.name
                        self.banks_state[self.bank_key] = self.banks_state.pop(old_path, {
                            "wrong": self.wrong_book, "favorites": self.favorites, "progress": self.current_idx})
                        self.save_state()
                    print("✅ 重命名成功！")
                    ask()
                continue

            if choice == "3":
                idx = ask("要删除的序号: ").strip()
                if not idx.isdigit():
                    continue
                i = int(idx) - 1
                if 0 <= i < len(bank_files):
                    if ask(f"⚠️ 确定删除 {bank_files[i].name} ？(y/N): ").strip().lower() == "y":
                        victim = bank_rel_key(bank_files[i])
                        bank_files[i].unlink()
                        if self.bank_key == victim:
                            self.questions = []
                            self.bank_key = ""
                            self.bank_path = ""
                            self.bank_name = ""
                            self.wrong_book = []
                            self.favorites = []
                            self.save_state()
                            print("✅ 已删除（这是当前题库，已卸载）")
                        else:
                            self.banks_state.pop(victim, None)
                            self.save_state()
                            print("✅ 已删除！")
                        ask()
                continue

def _load_bank_counts():
    try:
        if BANK_COUNTS_FILE.exists():
            raw = json.loads(BANK_COUNTS_FILE.read_text(encoding="utf-8-sig"))
            # 只保留相对路径 key，丢掉历史遗留的绝对路径
            return {k: v for k, v in raw.items() if ":" not in k and not k.startswith("\\\\")}
    except Exception:
        pass
    return {}

def _remember_bank_count(key, count):
    data = _load_bank_counts()
    if data.get(key) == count:
        return
    from core.paths import bank_rel_key
    try:
        key = bank_rel_key(key)
    except Exception:
        pass
    data[key] = count
    try:
        from core.safe_io import atomic_write_json
        atomic_write_json(BANK_COUNTS_FILE, data)
    except Exception:
        pass

def read_text_auto(path_obj: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb18030"]
    last_err = None
    for enc in encodings:
        try:
            with open(path_obj, "r", encoding=enc) as f:
                text = f.read()
            if enc in ("gbk", "gb18030") and text.count("\uFFFD") > 10:
                last_err = f"{enc} 解码大量乱码"
                continue
            return text
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
            continue
    with open(path_obj, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
