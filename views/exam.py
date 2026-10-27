# -*- coding: utf-8 -*-
"""考试：设置、计时、交卷、评分。"""
import random
import time

from quiz_parser.models import QuestionType

from core.ui import ask, clear_screen, dim, green, red, yellow


class ExamMixin:
    def start_exam(self):
        if not self.questions:
            print("⚠️ 请先导入题库！")
            ask()
            return
        try:
            exam_name = self.pref_ask("exam", "name", "模拟考试", "考试名称")
            exam_size = int(self.pref_ask("exam", "size", "50", "考试题量"))
            time_limit = int(self.pref_ask("exam", "minutes", "60", "限时分钟数")) * 60
            pass_line = int(self.pref_ask("exam", "pass", "60", "及格线百分比"))
        except ValueError:
            print("❌ 输入无效！")
            return

        # 按题型配分（与网页版一致：单选1 多选2 判断1 填空1 简答5）
        raw_points = self.pref_ask("exam", "points", "1,2,1,1,5", "配分 单选,多选,判断,填空,简答")
        try:
            parts = [int(x) for x in raw_points.replace("，", ",").split(",")]
            if len(parts) != 5 or any(x <= 0 for x in parts):
                raise ValueError
            p_single, p_multi, p_judge, p_blank, p_short = parts
        except ValueError:
            print("配分无效，使用默认 1,2,1,1,5")
            p_single, p_multi, p_judge, p_blank, p_short = 1, 2, 1, 1, 5

        def points_of(q):
            if q.type == QuestionType.SINGLE:
                return p_single
            if q.type == QuestionType.MULTIPLE:
                return p_multi
            if q.type == QuestionType.JUDGE:
                return p_judge
            if q.type == QuestionType.BLANK:
                return p_blank
            return p_short

        e_type = self.pref_ask("exam", "type", "1",
                               "考试题型: [1]全部 [2]单选 [3]多选 [4]判断 [5]填空 [6]简答")
        e_filter = {"2": QuestionType.SINGLE, "3": QuestionType.MULTIPLE,
                    "4": QuestionType.JUDGE, "5": QuestionType.BLANK,
                    "6": QuestionType.SHORT}.get(e_type)
        exam_pool = [q for q in self.questions if q.type == e_filter] if e_filter else list(self.questions)
        if not exam_pool:
            print("⚠️ 该题型没有题目")
            ask()
            return
        e_order = self.pref_ask("exam", "order", "1", "抽题顺序: [1]随机  [2]顺序")
        exam_size = min(exam_size, len(exam_pool))
        if e_order == "2":
            q_list = exam_pool[:exam_size]
        else:
            q_list = random.sample(exam_pool, exam_size)
        full_score = sum(points_of(q) for q in q_list)
        print(f"\n📝 {exam_name}：共 {len(q_list)} 题，满分 {full_score} 分，限时 {time_limit // 60} 分钟。")
        ask("按回车开始计时...")

        start_time = time.time()
        status = ["unanswered"] * len(q_list)
        marked = set()
        correct_count = 0
        answered = 0
        idx = 0
        timed_out = False

        while True:
            while idx < len(q_list):
                if time.time() - start_time > time_limit:
                    print(red("\n⏰ 时间到，自动交卷！"))
                    timed_out = True
                    break
                q = q_list[idx]
                self._render_question(q, idx, len(q_list), status, marked)
                print(dim(f"⏱ 剩余 {int((time_limit - (time.time() - start_time)) // 60)} 分"))
                is_correct, quit_flag, skipped, jump = self._ask_question(
                    q, idx + 1, len(q_list), is_exam=True, status=status, marked=marked)
                if quit_flag:
                    if not self._confirm("确定交卷？"):
                        continue
                    timed_out = True
                    break
                if jump:
                    idx = max(0, min(len(q_list) - 1, jump - 1))
                    continue
                if not skipped:
                    old = status[idx]
                    if old not in ("ok", "bad"):
                        answered += 1
                    elif old == "ok":
                        correct_count -= 1
                    status[idx] = "ok" if is_correct else "bad"
                    if is_correct:
                        correct_count += 1
                idx += 1

            if timed_out:
                break
            remaining = [i for i, s in enumerate(status) if s == "unanswered"]
            if remaining:
                if self._confirm(f"还有 {len(remaining)} 题未答，确认交卷？"):
                    break
                idx = remaining[0]
                continue
            break

        elapsed = time.time() - start_time
        score = sum(points_of(q) for q, s in zip(q_list, status) if s == "ok")
        rate = (score / full_score * 100) if full_score else 0
        wrong = self._summary(q_list, status, marked, elapsed, exam_name, answered, correct_count)
        verdict = green("✅ 及格") if rate >= pass_line else red("❌ 不及格")
        print(f"得分 {score}/{full_score} 分（{rate:.1f}%，及格线 {pass_line}%） {verdict}")
        print(f"题库: {self.bank_name}   交卷 {answered}/{len(q_list)}")
        details = [{"n": str(q.number), "q": q.question.replace("\n", " ")[:30], "ok": s == "ok"}
                   for q, s in zip(q_list, status) if s in ("ok", "bad")]
        self.save_history(exam_name, len(q_list), correct_count, elapsed, details)
        try:
            self._auto_sync("考试结束")
        except Exception:
            pass
        if wrong and self._confirm(f"立刻重练这 {len(wrong)} 道错题？"):
            self._run_practice_loop([q for _, q in wrong], "错题重练")
        else:
            self._pause("按任意键返回主菜单...")
