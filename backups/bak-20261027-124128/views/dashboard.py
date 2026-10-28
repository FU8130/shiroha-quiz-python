# -*- coding: utf-8 -*-
"""统计总览：累计数据、最近 7 天、学习建议。"""
from datetime import datetime

from core.paths import BANKS_DIR
from core.ui import ask, clear_screen, dim, green


class DashboardMixin:
    def _study_suggestions(self, history, answered, correct, days):
        """根据最近的练习情况给几条能直接执行的建议。"""
        tips = []
        acc = (correct / answered * 100) if answered else 0
        active_days = sum(1 for _, n in days if n > 0)

        fresh = [q for q in self.questions if q.id in self.wrong_book
                 and self.wrong_status.get(q.id, "未掌握") == "未掌握"]
        if fresh:
            tips.append(f"还有 {len(fresh)} 道未掌握的错题，先按「4 → 2」只练未掌握")
        if acc and acc < 60 and answered > 10:
            tips.append(f"累计正确率 {acc:.0f}%，建议把每轮题量降到 20 题以内，先吃透解析")
        if answered == 0:
            tips.append("还没开始练习：按 2 选 20 题热身，再按 3 考一次看看水平")
        if days and days[-1][1] == 0 and history:
            tips.append("今天还没练，做一轮 10 题的错题回顾就行")
        if active_days == 0 and history:
            tips.append("最近 7 天没有练习记录，先恢复每天 10 分钟")

        cats = {}
        for rec in history[-20:]:
            for d in rec.get("details") or []:
                if d.get("ok"):
                    cats["__ok__"] = cats.get("__ok__", 0) + 1
        if acc >= 85 and answered >= 30 and not fresh:
            tips.append("正确率不错：可以去「3 模拟考试」按真实时长练一次")
        if not tips:
            tips.append("保持节奏：每天 20 题练习 + 1 次错题回顾")
        return tips[:4]

    def show_dashboard(self):
        history = self._load_history()
        exts = {".txt", ".csv", ".tsv", ".json"}
        banks = [f for f in BANKS_DIR.iterdir() if f.is_file() and f.suffix.lower() in exts] if BANKS_DIR.exists() else []

        runs = len(history)
        answered = sum(int(r.get("total", 0)) for r in history)
        correct = sum(int(r.get("correct", 0)) for r in history)
        secs = sum(int(r.get("duration", 0)) for r in history)
        acc = (correct / answered * 100) if answered else 0
        wrong_n = len(self.wrong_book)
        fav_n = len(self.favorites)

        clear_screen()
        print("=" * 46)
        print("              📊 统计总览")
        print("=" * 46)
        today = datetime.now().strftime("%Y-%m-%d")
        today_recs = [r for r in history if str(r.get("time", "")).startswith(today)]
        today_q = sum(int(r.get("total", 0)) for r in today_recs)
        today_ok = sum(int(r.get("correct", 0)) for r in today_recs)
        today_acc = (today_ok / today_q * 100) if today_q else 0
        print(f"今日练习 {len(today_recs)} 次 · 作答 {today_q} 题 · 正确率 {today_acc:.1f}%")
        print(f"题库 {len(banks)} 个 · 当前库 {len(self.questions)} 题（{self.bank_name or '未加载'}）")
        print(f"错题 {wrong_n} 题 · 收藏 {fav_n} 题 · 进度 {min(self.current_idx + 1, max(len(self.questions), 1))}/{len(self.questions)}")
        print("-" * 46)
        print(f"累计练习 {runs} 次 · 作答 {answered} 题 · 正确率 {acc:.1f}% · 用时 {int(secs // 60)} 分")
        if self.wrong_counts:
            top = sorted(self.wrong_counts.items(), key=lambda kv: -kv[1])[:3]
            by_id = {q.id: q for q in self.questions}
            print("错得最多：")
            for qid, n in top:
                q = by_id.get(qid)
                if q:
                    print(f"  · {q.question[:30]}（{n} 次）")
        print("-" * 46)

        # 最近 7 天
        from collections import Counter
        by_day = Counter(r.get("time", "")[:10] for r in history)
        days = []
        today = datetime.now().date()
        for k in range(6, -1, -1):
            d = today.fromordinal(today.toordinal() - k).isoformat()
            days.append((d, by_day.get(d, 0)))
        peak = max([n for _, n in days] + [1])
        print("最近 7 天：")
        for d, n in days:
            bar = "█" * int(n / peak * 18) if n else ""
            print(f"  {d[5:]}  {n:>2} {green(bar) if n else dim('·')}")
        tips = self._study_suggestions(history, answered, correct, days)
        if tips:
            print("-" * 46)
            print("学习建议：")
            for tip in tips:
                print(f"  · {tip}")
        print("=" * 46)
        ask("按回车返回...")
