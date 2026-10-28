# -*- coding: utf-8 -*-
"""练习：设置、答题循环、判分反馈、答题卡、错题/收藏、搜索。"""
import random
import re
import sys
import textwrap
import time

from quiz_parser.models import QuestionType

from core.paths import bank_abs_path
from core.ui import (status_bar, 
    KeyReader, ask, bold, clear_screen, cyan, dim, green, progress_bar, red, yellow,
)


class PracticeMixin:
    def _render_question(self, q, idx, total, status, marked):
        clear_screen()
        answered = sum(1 for s in status if s in ("ok", "bad"))
        correct = sum(1 for s in status if s == "ok")
        bar = status_bar(status, idx) if status else progress_bar(idx, total)
        head = f"{bar} {idx + 1}/{total}"
        answered_now = sum(1 for s in status if s in ("ok", "bad"))
        stats = f"✅{correct}  ❌{answered - correct}  ⭐{len(self.favorites)}  已答{answered_now}"
        print(f"{cyan(head)}   {dim(stats)}   {dim(self.bank_name)}")
        if total > 60:
            per = (total + 59) // 60
            print(dim(f"   进度条：共 {total} 题，每格约 {per} 题；格内有错标红，无错有对标绿"))
        if marked and idx in marked:
            print(yellow("★ 已标记"))
        print("-" * 46)
        missed = self.wrong_counts.get(q.id, 0)
        mark = f"   {red('错过 ' + str(missed) + ' 次')}" if missed else ""
        print(dim(f"第 {q.number} 题 · {q.type.value}") + mark)

        for line in textwrap.wrap(q.question, width=44) or [""]:
            print(line)
        print()
        previous = (getattr(self, "_session_answers", {}) or {}).get(q.id)
        if q.options:
            for opt in q.options:
                chosen = previous and opt.key in previous
                arrow = green("▸ ") if chosen else "  "
                print(f" {arrow}{bold(opt.key)}. {opt.text}")
            print()
        if previous:
            tag = green("你的答案：") if status[idx] == "ok" else red("你的答案：")
            print(tag + bold(previous))
            print()

    @staticmethod
    def _render_card(status, marked, idx):
        line = []
        for i, s in enumerate(status):
            n = f"{i + 1:>2}"
            if i == idx:
                n = cyan(n)
            elif s == "ok":
                n = green(n)
            elif s == "bad":
                n = red(n)
            else:
                n = dim(n)
            if (i + 1) in marked:
                n = yellow("★" + n)
            line.append(n)
        rows = [" ".join(line[i:i + 15]) for i in range(0, len(line), 15)]
        return "\n".join(rows)

    def _toggle_favorite(self, q, quiet=False):
        if q.id in self.favorites:
            self.favorites.remove(q.id)
            if not quiet:
                print(yellow("☆ 已取消收藏"))
        else:
            self.favorites.append(q.id)
            if not quiet:
                print(yellow("★ 已收藏"))
        self.save_state()

    def _read_number_line(self, hint_text=""):
        """读一行数字（用于 /J 跳题），Esc 取消。"""
        sys.stdout.write(hint_text)
        sys.stdout.flush()
        buf = ""
        while True:
            try:
                ch = KeyReader.getch()
            except (KeyboardInterrupt, EOFError):
                print()
                return ""
            if ch in ("\r", "\n"):
                print()
                return buf.strip()
            if ch == "\x1b":
                print()
                return ""
            if ch in ("\x08", "\x7f"):
                if buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch.isdigit():
                buf += ch
                sys.stdout.write(ch)
                sys.stdout.flush()

    def _read_action(self, q, current, status, marked, total=None, is_exam=False, deadline=None):
        """读一次操作。终端下单键即时生效；重定向时退化为整行输入。

        返回 (kind, text)：
          ("answer", "ABD") / ("skip", "") / ("quit", "") / ("back", "") / ("jump", "12")
        """
        prompt = cyan("👉 答案 ") + dim(
            "(A-H / 1-8 作答 · Enter 提交 · / 前缀命令 · #12 跳题 · [ ] 上下题)")
        hint = "> "
        print(dim("   命令：/F 收藏 /M 标记 /B 答题卡 /A 答案 /E 编辑 /S 跳过 /Q 退出 · F2 收藏 F4 标记 ; 看答案"))

        def prompt_text():
            star = "★" if q.id in self.favorites else "☆"
            mark = "✎" if (marked is not None and current in marked) else " "
            return dim(f"[{star}{mark}] ") + "> "

        def redraw(buf=""):
            # 单行锁定：先擦本行再重画；有 deadline 时右侧带秒级倒计时
            extra = ""
            if deadline:
                rem = max(0, int(deadline - time.time()))
                extra = "  " + dim(f"⏱ {rem // 60:02d}:{rem % 60:02d}")
            sys.stdout.write("\r" + " " * 72 + "\r" + prompt_text() + buf + extra)
            sys.stdout.flush()

        valid_keys = {o.key.upper() for o in q.options} or set("ABCD")
        single_only = q.type in (QuestionType.SINGLE, QuestionType.JUDGE)

        def key_for_digit(d):
            """1-8 -> 对应的选项字母（超出选项数返回 None）。"""
            if not d.isdigit():
                return None
            idx = int(d) - 1
            if 0 <= idx < len(q.options):
                return q.options[idx].key.upper()
            return None

        def reveal():
            if is_exam:
                print(dim("考试中不能看答案"))
                return
            print(yellow(f"\n正确答案：{''.join(q.answer) or '(无)'}"))
            if q.analysis:
                for line in textwrap.wrap(q.analysis, width=44):
                    print(dim("📝 " + line))

        def collect(text):
            text = (text or "").strip()
            if not text.isdigit() or not total:
                return None
            n = int(text)
            return n if 1 <= n <= total else None

        def step(delta):
            n = current + delta
            if total:
                n = max(1, min(total, n))
            return max(1, n)

        # 只给“需要反复按的开关”配功能键；其余保持 / 命令或已有单键
        FUNC_MAP = {
            "F2": "f",   # 收藏 / 取消（可反复按）
            "F4": "m",   # 标记 / 取消（F3 在 VSCode 被占用）
        }

        def exec_cmd(letter):
            """执行一个命令字母；返回 (kind, text) 或 ("repeat", key)。"""
            low = (letter or "").lower()
            if low == "q":
                if self._confirm("退出本次练习？"):
                    return ("quit", "")
                return None
            if low == "s":
                return ("skip", "")
            if low == "f":
                self._toggle_favorite(q, quiet=True)
                return None
            if low == "m":
                self._toggle_mark(current, marked, quiet=True)
                return None
            if low == "b":
                self._show_card(status, marked, current - 1)
                return None
            if low == "a":
                reveal()
                return None
            if low == "e":
                self._edit_one(q)
                if self._save_bank_file(bank_abs_path(self.bank_path), self.questions):
                    print(green("✅ 改动已写回题库"))
                return None
            print(dim("未知命令：/F /M /B /A /E /S /Q（F2 收藏 / F4 标记 / ; 看答案）"))
            return None

        if not KeyReader.available():
            while True:
                try:
                    line = ask(prompt + " " + hint).strip()
                except (EOFError, KeyboardInterrupt):
                    return "back", ""
                if not line:
                    continue
                low = line.lower()
                explicit = low.startswith("/")
                key = low.lstrip("/").strip()
                if explicit:
                    if key in ("q", "quit", "exit"):
                        return "quit", ""
                    if key in ("s", "skip"):
                        return "skip", ""
                    if key in ("f", "fav"):
                        self._toggle_favorite(q)
                        continue
                    if key in ("m", "mark"):
                        self._toggle_mark(current, marked)
                        continue
                    if key in ("b", "?", "/?"):
                        self._show_card(status, marked, current - 1)
                        continue
                    if key in ("a", "ans"):
                        reveal()
                        continue
                    if key in ("j", "jump"):
                        n = collect(ask("跳到第几题: "))
                        if n is None:
                            print(dim("题号无效"))
                            continue
                        return "jump", str(n)
                    if key in ("p", "prev"):
                        return "jump", str(step(-1))
                    if key in ("n", "next"):
                        return "jump", str(step(1))
                    if key.isdigit() and collect(key):
                        return "jump", key
                    print(dim("未知命令，可用 /F /M /B /J /P /N /A /S /Q"))
                    continue
                if line.strip() == ";":
                    reveal()
                    continue
                if low.startswith("#"):
                    n = collect(low[1:])
                    if n is None:
                        print(dim("题号无效"))
                        continue
                    return "jump", str(n)
                if low.isdigit():
                    mapped = "".join(k for k in (key_for_digit(c) for c in low) if k)
                    if mapped:
                        return "answer", mapped
                cand = line.strip().upper().replace(" ", "").replace(",", "").replace("，", "")
                if not cand:
                    continue
                bad = [c for c in cand if c not in valid_keys]
                if bad:
                    print(dim(f"只能输入选项里的字母：{'/'.join(sorted(valid_keys))}（{'、'.join(bad)} 无效）"))
                    continue
                cand = "".join(dict.fromkeys(cand))
                if single_only and len(cand) > 1:
                    print(dim("单选题只能选一个选项"))
                    continue
                return "answer", cand

        print(prompt)
        sys.stdout.write(hint)
        sys.stdout.flush()
        prev = (getattr(self, "_session_answers", {}) or {}).get(q.id, "") or ""
        buf = "".join(ch for ch in prev.upper() if ch in valid_keys)
        if single_only:
            buf = buf[:1]
        if buf:
            redraw(buf)
        slash = False
        empty_enters = 0
        while True:
            try:
                if deadline:
                    if time.time() >= deadline:
                        return "timeout", ""
                    ch = KeyReader.getch_timeout(0.2)
                    if ch is None:
                        redraw(buf)
                        continue
                else:
                    ch = KeyReader.getch()
            except (KeyboardInterrupt, EOFError):
                print()
                return "back", ""

            if not ch:
                continue

            # Ctrl 快捷键：单键、可反复按
            if ch in FUNC_MAP:
                res = exec_cmd(FUNC_MAP[ch])
                if res:
                    return res
                redraw(buf)
                sys.stdout.flush()
                continue

            if ch == "/":
                slash = True
                continue

            # 「/」两键命令；执行 f/m 后可连按该键继续切换
            if slash:
                slash = False
                if ch in ("\r", "\n", "\x1b", "\x08", "\x7f"):
                    continue
                res = exec_cmd(ch)
                if res:
                    return res
                redraw(buf)
                sys.stdout.flush()
                continue

            if ch in ("\r", "\n"):
                if not buf:
                    empty_enters += 1
                    if empty_enters >= 5:
                        return "back", ""
                    continue
                sys.stdout.write("\n")
                if buf.isdigit() and total and 1 <= int(buf) <= total:
                    return "jump", buf
                break
            if ch in ("\x08", "\x7f"):
                if buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch == "\x1b":
                buf = ""
                redraw("")
                sys.stdout.flush()
                continue

            if ch == "[":
                return "jump", str(step(-1))
            if ch == "]":
                return "jump", str(step(1))
            if ch == "?":
                sys.stdout.write("\n")
                self._show_card(status, marked, current - 1)
                redraw(buf)
                sys.stdout.flush()
                continue

            if ch.isdigit():
                mapped_key = key_for_digit(ch)
                if mapped_key and mapped_key in valid_keys:
                    if single_only:
                        buf = mapped_key
                    elif mapped_key in buf:
                        buf = buf.replace(mapped_key, "")   # 多选：再按一次取消
                    else:
                        buf += mapped_key
                    redraw(buf)
                continue

            if ch == ";":
                sys.stdout.write("\n")
                reveal()
                redraw(buf)
                sys.stdout.flush()
                continue

            if ch == "#":
                n = collect(self._read_number_line(cyan("跳到第 ")))
                if n is None:
                    print(dim("题号无效"))
                else:
                    return "jump", str(n)
                redraw(buf)
                sys.stdout.flush()
                continue

            upper = ch.upper()
            if upper in valid_keys:
                if single_only:
                    buf = upper          # 单选：直接替换，无需退格
                elif upper in buf:
                    buf = buf.replace(upper, "")   # 多选：再按一次取消
                else:
                    buf += upper
                redraw(buf)
                continue
            if upper.isalnum():
                continue              # 不在选项里的字母/数字，直接忽略

        return "answer", buf

    def _pause(self, message="按任意键继续..."):
        """单键继续；重定向时退回回车。"""
        if KeyReader.available():
            sys.stdout.write(dim(message + " "))
            sys.stdout.flush()
            try:
                KeyReader.getch()
            except (KeyboardInterrupt, EOFError):
                pass
            print()
        else:
            try:
                ask(message + " ")
            except (EOFError, KeyboardInterrupt):
                pass

    def _toggle_mark(self, current, marked, quiet=False):
        if marked is None:
            return
        if current in marked:
            marked.discard(current)
            if not quiet:
                print(dim("已取消标记"))
        else:
            marked.add(current)
            if not quiet:
                print(yellow("★ 已标记"))

    def _show_card(self, status, marked, idx):
        if status is None:
            return
        print("\n" + self._render_card(status, marked or set(), idx) + "\n")
        print(dim("图例：绿=答对 红=答错 黄=跳过 ★=标记    · /J 题号 可直接跳题"))

    @staticmethod
    def _confirm(question, default=False):
        """需要确认的动作：单键 y/N。"""
        suffix = "(Y/n) " if default else "(y/N) "
        sys.stdout.write(question + suffix)
        sys.stdout.flush()
        if KeyReader.available():
            try:
                ch = KeyReader.getch().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return default
            print(ch)
        else:
            try:
                ch = ask().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return default
        if not ch:
            return default
        return ch in ("y", "yes", "是")

    def _ask_question(self, q, current, total, is_exam=False, status=None, marked=None, deadline=None):
        """返回 (是否正确, 是否退出, 是否跳过, 跳转目标)。"""
        if q.type in (QuestionType.SHORT, QuestionType.BLANK):
            print(f"\n💡 参考答案: {''.join(q.answer)}")
            if q.analysis:
                print(f"📝 解析: {q.analysis}")
            if KeyReader.available():
                sys.stdout.write(dim("\n按任意键继续，Q 退出 ")); sys.stdout.flush()
                try:
                    ch = KeyReader.getch().lower()
                except (KeyboardInterrupt, EOFError):
                    ch = "q"
                print()
                return True, ch == "q", False, None
            try:
                key = ask("\n回车继续，Q 退出 > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False, True, False, None
            return True, key in ("q", "quit"), False, None

        kind, text = self._read_action(q, current, status, marked, total=total, is_exam=is_exam, deadline=deadline)
        if kind == "back":
            return False, True, False, None
        if kind == "skip":
            return False, False, True, None
        if kind == "timeout":
            return False, True, False, None
        if kind == "quit":
            return False, True, False, None
        if kind == "jump":
            n = int(text) if text.isdigit() else None
            return False, False, False, n

        if not hasattr(self, "_session_answers"):
            self._session_answers = {}
        prev = (self._session_answers.get(q.id) or "").upper()
        repeat = bool(prev) and text.upper() == prev   # 与上次完全一致：只回放结果，不重复计数
        self._session_answers[q.id] = text
        is_correct = self.check_answer(q, text)
        if repeat:
            print(dim("（与上次答案相同，未重复计入）"))
        if is_correct:
            print(green("✅ 正确"))
            if not repeat:
                if q.id in self.wrong_book:
                    self.right_counts[q.id] = self.right_counts.get(q.id, 0) + 1
                    if self.right_counts[q.id] >= 2:
                        self.wrong_status[q.id] = "已掌握"
                    else:
                        self.wrong_status[q.id] = "复习中"
                self.wrong_counts.pop(q.id, None)
        else:
            correct_text = "；".join(f"{o.key}. {o.text}" for o in q.options if o.key in q.answer)
            print(red(f"❌ 错误，正确答案：{''.join(q.answer)}" + (f"（{correct_text}）" if correct_text else "")))
            if not repeat:
                if q.id not in self.wrong_book:
                    self.wrong_book.append(q.id)
                self.wrong_counts[q.id] = self.wrong_counts.get(q.id, 0) + 1
                self.wrong_status[q.id] = "未掌握"
                self.wrong_last[q.id] = time.time()
        if not is_exam and q.analysis:
            for line in textwrap.wrap(q.analysis, width=44):
                print(f"📝 {dim(line)}")
        self.save_state()
        return is_correct, False, False, None

    def _run_practice_loop(self, q_list, mode_name, ask_continue=True):
        total = len(q_list)
        self._session_answers = {}      # 每轮练习重新开始：回看与“重复提交”只在本轮内生效
        status = ["unanswered"] * total
        marked = set()
        start_time = time.time()
        correct_count = 0
        answered = 0
        idx = 0

        while 0 <= idx < total:
            q = q_list[idx]
            self._render_question(q, idx, total, status, marked)
            print(dim(f"⏱ 已用 {int(time.time() - start_time)} 秒"))
            is_correct, quit_flag, skipped, jump = self._ask_question(
                q, idx + 1, total, status=status, marked=marked)

            if quit_flag:
                break
            if jump:
                idx = max(0, min(total - 1, jump - 1))
                self.current_idx = idx
                continue
            if skipped:
                if status[idx] == "unanswered":
                    status[idx] = "skip"
                idx += 1
                self.current_idx = idx
                continue

            old = status[idx]
            if old not in ("ok", "bad"):
                answered += 1
            elif old == "ok":
                correct_count -= 1
            status[idx] = "ok" if is_correct else "bad"
            if is_correct:
                correct_count += 1
            idx += 1
            self.current_idx = idx
            self.save_state()

            need_pause = ask_continue and idx < total and (
                getattr(self, "pause_mode", "smart") == "always"
                or (getattr(self, "pause_mode", "smart") == "smart"
                    and (not is_correct or bool(q.analysis)))
            )
            if need_pause:
                if KeyReader.available():
                    sys.stdout.write(dim("\n回车=下一题  ?=答题卡  #题号=跳题  Q=退出 "))
                    sys.stdout.flush()
                    try:
                        ch = KeyReader.getch()
                    except (KeyboardInterrupt, EOFError):
                        break
                    print()
                    low = ch.lower()
                else:
                    try:
                        low = ask(dim("\n回车下一题 / ? 答题卡 / #题号 跳题 / Q 退出 > ")).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        break
                if low in ("", "\r", "\n"):
                    pass
                elif low in ("q", "quit"):
                    if self._confirm("退出本次练习？"):
                        break
                elif low in ("?", "b", "/b"):
                    self._show_card(status, marked, idx)
                    self._pause("按任意键继续...")
                elif low.isdigit():
                    target = max(1, min(total, int(low)))
                    idx = target - 1
                    self.current_idx = idx
                    continue

        elapsed = time.time() - start_time
        wrong = self._summary(q_list, status, marked, elapsed, mode_name, answered, correct_count)
        try:
            self._auto_sync("练习结束")
        except Exception:
            pass
        if answered:
            details = [{"n": str(q.number), "q": q.question.replace("\n", " ")[:30], "ok": s == "ok"}
                       for q, s in zip(q_list, status) if s in ("ok", "bad")]
            self.save_history(mode_name, answered, correct_count, elapsed, details)
        if wrong and self._confirm(f"重练这 {len(wrong)} 道错题？"):
            self._run_practice_loop([q for _, q in wrong], "错题重练")
            return correct_count, answered
        self._pause("按任意键返回...")
        return correct_count, answered

    @staticmethod
    def _parse_pick(text, limit):
        """解析「1,5,9-12」这类题号选择，返回 1 基序号列表。"""
        picks = []
        for part in re.split(r"[,，\s]+", (text or "").strip()):
            if not part:
                continue
            m = re.match(r"^(\d+)\s*[-~至]\s*(\d+)$", part)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if a > b:
                    a, b = b, a
                picks.extend(range(a, b + 1))
            elif part.isdigit():
                picks.append(int(part))
        seen, out = set(), []
        for p in picks:
            if 1 <= p <= limit and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _summary(self, q_list, status, marked, elapsed, mode_name, answered, correct):
        """统一的结算页：答题卡 + 统计 + 错题明细。返回错题列表。"""
        clear_screen()
        print("=" * 46)
        print(f"           📊 {mode_name} 结束")
        print("=" * 46)
        print(self._render_card(status, marked, -1))
        print("-" * 46)
        rate = (correct / answered * 100) if answered else 0
        print(f"作答 {answered} 题，正确 {correct} 题，正确率 {rate:.1f}%")
        cats = {}
        for q, s in zip(q_list, status):
            if s in ("ok", "bad"):
                name = (q.category or "未分类").strip() or "未分类"
                ok_n, tot = cats.get(name, (0, 0))
                cats[name] = (ok_n + (1 if s == "ok" else 0), tot + 1)
        if len(cats) > 1:
            print("-" * 46)
            print("分类正确率：")
            for name, (ok_n, tot) in sorted(cats.items(), key=lambda kv: -kv[1][1])[:8]:
                pct = ok_n / tot * 100 if tot else 0
                print(f"  {name[:14]:<16} {ok_n}/{tot}  {pct:5.1f}%")
        print(f"耗时 {int(elapsed // 60)} 分 {int(elapsed % 60)} 秒   "
              f"跳过 {sum(1 for s in status if s == 'skip')} 题   "
              f"未答 {sum(1 for s in status if s == 'unanswered')} 题")

        wrong = [(i, q) for i, (q, s) in enumerate(zip(q_list, status)) if s == "bad"]
        if wrong:
            print("-" * 46)
            print(f"错题明细（{len(wrong)} 题）：")
            for i, q in wrong[:15]:
                stem = q.question.replace("\n", " ")
                print(f"  {i + 1:>3}. {stem[:32]}  →  {''.join(q.answer) or '无答案'}")
            if len(wrong) > 15:
                print(f"       …… 还有 {len(wrong) - 15} 题")
        elif answered:
            print(green("\n✨ 本轮全对！"))
        return wrong

    def practice_settings(self):
        if not self.questions:
            print("⚠️ 请先导入题库！")
            ask()
            return

        clear_screen()
        print("=" * 46)
        print("              🎯 自定义练习")
        print("=" * 46)
        src = self.pref_ask("practice", "source", "1", "1. 题目来源: [1]全部  [2]仅错题  [3]仅收藏")
        pool = self.questions
        if src == "2":
            pool = [q for q in self.questions if q.id in self.wrong_book]
        elif src == "3":
            pool = [q for q in self.questions if q.id in self.favorites]
        if not pool:
            print("⚠️ 所选来源为空！")
            ask()
            return

        t_choice = self.pref_ask("practice", "type", "1",
                                 "2. 题型: [1]全部 [2]单选 [3]多选 [4]判断 [5]填空 [6]简答 [7]多选兼容")
        type_filter = {"2": QuestionType.SINGLE, "3": QuestionType.MULTIPLE,
                       "4": QuestionType.JUDGE, "5": QuestionType.BLANK,
                       "6": QuestionType.SHORT, "7": QuestionType.MULTIPLE}.get(t_choice)
        if type_filter:
            pool = [q for q in pool if q.type == type_filter]
        if not pool:
            print("⚠️ 所选题型为空！")
            ask()
            return

        # 3. 分类 / 章节（题库带分类时才出现）
        cats = {}
        for q in pool:
            name = (q.category or "").strip()
            if name:
                cats[name] = cats.get(name, 0) + 1
        if cats:
            ordered = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
            print("\n3. 分类/章节: [0]全部")
            for i, (name, cnt) in enumerate(ordered, 1):
                print(f"   [{i}] {name} ({cnt})")
            pick_cat = ask("请选择 (默认0): ").strip()
            if pick_cat.isdigit() and 1 <= int(pick_cat) <= len(ordered):
                chosen = ordered[int(pick_cat) - 1][0]
                pool = [q for q in pool if (q.category or "").strip() == chosen]
                if not pool:
                    print("⚠️ 该分类下没有题目！")
                    ask()
                    return

        default_count = int(self.pref("practice", "count", 20))
        print(f"\n4. 抽题 (可用 {len(pool)} 题)")
        print(f"   输入题量 / 题号(如 1,5,9-12) / h=一半；留空=上次({default_count})，0=全部，d=默认20")
        q_str = ask("> ").strip()
        if q_str.lower() == "d":
            self.remember("practice", "count", 20)
            q_str = "20"
        picked = []
        if q_str.lower() in ("h", "half", "半"):
            q_num = max(1, len(pool) // 2)
        elif q_str.isdigit():
            q_num = min(int(q_str), len(pool))
            if q_num > 0:
                self.remember("practice", "count", q_num)
        elif q_str:
            picked = self._parse_pick(q_str, len(pool))
            q_num = len(picked)
            if not picked:
                print("⚠️ 题号无效！")
                ask()
                return
        else:
            q_num = min(default_count, len(pool))

        order = self.pref_ask("practice", "order", "1", "5. 顺序: [1]顺序  [2]随机")

        stay = self.pref_ask("practice", "stay", "3",
                             "6. 答题后: [1]智能(答对自动/答错停留)  [2]总是停留  [3]总是自动")
        self.auto_next = (stay == "1")
        self.pause_mode = {"1": "never", "2": "always", "3": "smart"}.get(stay, "never")

        if picked:
            q_list = [pool[i - 1] for i in picked]
        else:
            q_list = pool[:q_num] if order == "1" else random.sample(pool, q_num)

        if not picked and order == "1" and src == "1" and not type_filter and 0 < self.current_idx < len(pool):
            print(f"\n💡 上次进度停在第 {self.current_idx + 1} 题")
            if ask("从上次进度继续？(Y/n，回车=继续): ").strip().lower() != "n":
                q_list = pool[self.current_idx:self.current_idx + q_num] or pool[:q_num]

        if not q_list:
            print("⚠️ 抽题结果为空！")
            ask()
            return
        self.save_state()
        self._run_practice_loop(q_list, "自定义练习")

    def search_questions(self):
        if not self.questions:
            print("⚠️ 请先导入题库！")
            ask()
            return

        clear_screen()
        print("=" * 46)
        print("            🔍 搜索 / 分类浏览")
        print("=" * 46)
        print("1. 关键词搜索    2. 按分类/章节浏览")
        mode = ask("请选择 (默认1): ").strip() or "1"

        hits = []
        if mode == "2":
            cats = {}
            for q in self.questions:
                name = (q.category or "").strip()
                if name:
                    cats[name] = cats.get(name, 0) + 1
            if not cats:
                print("这个题库没有分类信息。")
                ask()
                return
            ordered = sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
            for i, (name, cnt) in enumerate(ordered, 1):
                print(f"  [{i}] {name} ({cnt})")
            pick = ask("选择分类 (0=返回): ").strip()
            if not pick.isdigit() or not (1 <= int(pick) <= len(ordered)):
                return
            chosen = ordered[int(pick) - 1][0]
            hits = [q for q in self.questions if (q.category or "").strip() == chosen]
        else:
            keyword = ask("\n🔍 搜索关键词: ").strip()
            if not keyword:
                return
            hits = [q for q in self.questions
                    if keyword in q.question or any(keyword in o.text for o in q.options)]

        if not hits:
            print("没有匹配的题目。")
            ask()
            return

        while True:
            clear_screen()
            print(f"找到 {len(hits)} 题（显示前 15 条）：")
            for i, q in enumerate(hits[:15], 1):
                star = yellow("★") if q.id in self.favorites else " "
                missed = self.wrong_counts.get(q.id, 0)
                tag = f"  {red('错' + str(missed) + '次')}" if missed else ""
                print(f"  [{i:>2}] {star} {q.question[:36]}{tag}")
            print("\n输入序号练习该题   f序号=收藏开关   回车返回")
            pick = ask("> ").strip().lower()
            if not pick or pick == "0":
                return
            if pick.startswith("f") and pick[1:].isdigit():
                idx = int(pick[1:])
                if 1 <= idx <= len(hits[:15]):
                    q = hits[idx - 1]
                    if q.id in self.favorites:
                        self.favorites.remove(q.id)
                        self.save_state()
                        print(green("✅ 已取消收藏"))
                    else:
                        self.favorites.append(q.id)
                        self.save_state()
                        print(yellow("★ 已收藏"))
                    ask()
                continue
            if pick.isdigit() and 1 <= int(pick) <= len(hits[:15]):
                self._run_practice_loop([hits[int(pick) - 1]], "搜索练习")
                return

    def review_wrong(self):
        pool = [q for q in self.questions if q.id in self.wrong_book]
        if not pool:
            print("🎉 错题本为空")
            ask()
            return
        s_mode = self.pref_ask("wrong", "sort", "2", "错题排序: [1]错误次数  [2]最近答错  [3]掌握状态")
        if s_mode == "2":
            pool.sort(key=lambda x: self.wrong_last.get(x.id, 0), reverse=True)
        elif s_mode == "3":
            order = {"未掌握": 0, "复习中": 1, "已掌握": 2}
            pool.sort(key=lambda x: order.get(self.wrong_status.get(x.id, "未掌握"), 0))
        else:
            pool.sort(key=lambda x: self.wrong_counts.get(x.id, 0), reverse=True)
        clear_screen()
        print("=" * 46)
        print(f"            ❌ 错题本（{len(pool)} 题）")
        print("=" * 46)
        for i, q in enumerate(pool[:10], 1):
            n = self.wrong_counts.get(q.id, 0)
            st = self.wrong_status.get(q.id, "未掌握")
            r = self.right_counts.get(q.id, 0)
            print(f"  {i:>2}. [{st}] 错{n}次 做对{r}次  {q.question[:26]}")
        if len(pool) > 10:
            print(f"      …… 还有 {len(pool) - 10} 题")
        print("\n[1] 全部  [2] 只练未掌握  [3] 只练已掌握  [4] 只练错2次以上")
        print("[5] 指定数量  [6] 清空错题  [7] 只练复习中  [0] 返回")
        print("单题：m3=掌握切换  f3=收藏切换  r3=移出错题  3=只练第3题")
        default_choice = "2" if any(self.wrong_status.get(q.id, "未掌握") == "未掌握" for q in pool) else "1"
        c = ask(f"请选择 (默认{default_choice}): ").strip().lower() or default_choice
        if c and c[0] in ("m", "f", "r") and c[1:].isdigit():
            idx = int(c[1:])
            if 1 <= idx <= len(pool):
                q = pool[idx - 1]
                if c[0] == "m":
                    cur = self.wrong_status.get(q.id, "未掌握")
                    self.wrong_status[q.id] = "未掌握" if cur == "已掌握" else "已掌握"
                    if self.wrong_status[q.id] == "已掌握":
                        self.right_counts[q.id] = max(self.right_counts.get(q.id, 0), 2)
                    self.save_state()
                    print(green(f"✅ 状态：{self.wrong_status[q.id]}"))
                elif c[0] == "f":
                    if q.id in self.favorites:
                        self.favorites.remove(q.id)
                        print(green("✅ 已取消收藏"))
                    else:
                        self.favorites.append(q.id)
                        print(yellow("★ 已收藏"))
                    self.save_state()
                else:
                    if self._confirm(f"把「{q.question[:20]}」移出错题本？"):
                        self.wrong_book = [i for i in self.wrong_book if i != q.id]
                        self.wrong_counts.pop(q.id, None)
                        self.wrong_status.pop(q.id, None)
                        self.wrong_last.pop(q.id, None)
                        self.right_counts.pop(q.id, None)
                        self.save_state()
                        print(green("✅ 已移出错题本"))
                ask()
            return
        if c.isdigit() and c not in ("1", "2", "3", "4", "5", "6", "0"):
            idx = int(c)
            if 1 <= idx <= len(pool):
                self._run_practice_loop([pool[idx - 1]], "错题单题")
                return
        def by_status(status_name):
            return [q for q in pool if self.wrong_status.get(q.id, "未掌握") == status_name]

        if c == "1":
            self._run_practice_loop(pool, "错题回顾")
        elif c == "2":
            sub = by_status("未掌握")
            if not sub:
                print("没有未掌握的错题")
                ask()
                return
            self._run_practice_loop(sub, "未掌握错题")
        elif c == "3":
            sub = by_status("已掌握")
            if not sub:
                print("还没有标记为已掌握的题（答对后自动标记）")
                ask()
                return
            self._run_practice_loop(sub, "已掌握错题")
        elif c == "4":
            hot = [q for q in pool if self.wrong_counts.get(q.id, 0) >= 2]
            if not hot:
                print("没有错 2 次以上的题")
                ask()
                return
            self._run_practice_loop(hot, "高频错题")
        elif c == "7":
            sub = by_status("复习中")
            if not sub:
                print("没有复习中的题（答对一次才会进入复习中）")
                ask()
                return
            self._run_practice_loop(sub, "复习中错题")
        elif c == "5":
            n = ask(f"练多少题 (1-{len(pool)}，回车=20，h=一半): ").strip() or "20"
            if n.lower() in ("h", "half", "半"):
                self._run_practice_loop(pool[:max(1, len(pool) // 2)], "错题回顾")
                return
            if not n.isdigit() or not (1 <= int(n) <= len(pool)):
                return
            self._run_practice_loop(pool[:int(n)], "错题回顾")
        elif c == "6":
            from core.ui import danger_confirm
            if danger_confirm(self._confirm, f"清空全部 {len(pool)} 道错题记录"):
                self.wrong_book = []
                self.wrong_counts = {}
                self.wrong_status = {}
                self.wrong_last = {}
                self.save_state()
                print(green("✅ 已清空错题本"))
                ask()

    def review_favorites(self):
        pool = [q for q in self.questions if q.id in self.favorites]
        if not pool:
            print("🎉 收藏夹为空")
            ask()
            return
        clear_screen()
        print("=" * 46)
        print(f"            ⭐ 收藏夹（{len(pool)} 题）")
        print("=" * 46)
        for i, q in enumerate(pool[:10], 1):
            print(f"  {i:>2}. {q.question[:34]}")
        if len(pool) > 10:
            print(f"      …… 还有 {len(pool) - 10} 题")
        print("\n[1] 练习收藏题  [2] 清空收藏  [0] 返回")
        print("单题：f3=收藏开关（同一键取消）   3=只练第3条")
        c = ask("请选择 (默认1): ").strip().lower() or "1"
        if c.startswith("f") and c[1:].isdigit():
            idx = int(c[1:])
            if 1 <= idx <= len(pool):
                q = pool[idx - 1]
                if q.id in self.favorites:
                    self.favorites.remove(q.id)
                    self.save_state()
                    print(green(f"✅ 已取消收藏：{q.question[:24]}"))
                else:
                    self.favorites.append(q.id)
                    self.save_state()
                    print(yellow(f"★ 已重新收藏：{q.question[:24]}"))
                ask()
            return
        if c.isdigit() and c != "1" and c != "2":
            idx = int(c)
            if 1 <= idx <= len(pool):
                self._run_practice_loop([pool[idx - 1]], "收藏单题")
                return
        if c == "1":
            self._run_practice_loop(pool, "收藏回顾")
        elif c == "2":
            from core.ui import danger_confirm
            if danger_confirm(self._confirm, f"清空全部 {len(pool)} 条收藏"):
                self.favorites = []
                self.save_state()
                print(green("✅ 已清空收藏"))
                ask()
