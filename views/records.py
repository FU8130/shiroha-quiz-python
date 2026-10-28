# -*- coding: utf-8 -*-
"""历史战绩：列表、筛选、逐题明细、导出与清空。"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from core.paths import BASE_DIR, HISTORY_FILE
from core.ui import KeyReader, ask, clear_screen, dim, green, red, yellow


class RecordsMixin:
    def show_history(self):
        if not HISTORY_FILE.exists():
            print("📭 暂无历史战绩。")
            ask()
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            return
        if not history:
            print("📭 暂无历史战绩。")
            ask()
            return

        mode_filter = "1"
        limit = 30
        while True:
            pool = history
            if mode_filter == "2":
                pool = [r for r in history if "考试" not in r.get("mode", "")]
            elif mode_filter == "3":
                pool = [r for r in history if "考试" in r.get("mode", "")]
            shown = list(reversed(pool[-limit:] if limit else pool))

            clear_screen()
            total_q = sum(int(r.get("total", 0)) for r in history)
            total_ok = sum(int(r.get("correct", 0)) for r in history)
            total_sec = sum(int(r.get("duration", 0)) for r in history)
            acc_all = (total_ok / total_q * 100) if total_q else 0
            print("=" * 66)
            print("                        📚 历史战绩")
            print("=" * 66)
            print(f"累计 {len(history)} 次 · 作答 {total_q} 题 · 正确率 {acc_all:.1f}% · 用时 {int(total_sec // 60)} 分")
            print(f"错题 {len(self.wrong_book)} 题 · 收藏 {len(self.favorites)} 题")
            print("-" * 66)
            print(f"{'#':>2} | {'时间':<17} | {'模式':<10} | {'题数':>4} | {'正确率':>6} | {'耗时':>6}")
            print("-" * 66)
            for i, rec in enumerate(shown, 1):
                acc = rec.get("accuracy", 0)
                acc_text = green(f"{acc:>5.1f}%") if acc >= 80 else (yellow(f"{acc:>5.1f}%") if acc >= 60 else red(f"{acc:>5.1f}%"))
                print(f"{i:>2} | {rec.get('time', ''):<17} | {rec.get('mode', ''):<10} | {rec.get('total', 0):>4} | "
                      f"{acc_text} | {int(rec.get('duration', 0) // 60)}m{int(rec.get('duration', 0) % 60)}s")
            print("=" * 66)
            print("输入序号看明细  [e]导出CSV  [f]筛选  [c]清空记录  回车返回")
            pick = ask("> ").strip().lower()

            if pick == "f":
                m = ask("筛选 [1]全部 [2]练习 [3]考试 (默认1): ").strip() or "1"
                n = ask("显示条数 (30/100/全部，0=全部，默认30): ").strip().lower() or "30"
                mode_filter = m if m in ("1", "2", "3") else "1"
                if n in ("a", "all", "全部", "0"):
                    limit = 0
                elif n.isdigit():
                    limit = int(n)
                else:
                    limit = 30
                continue
            if pick == "e":
                self._export_history(pool)
                return
            if pick == "c":
                from core.ui import danger_confirm
                if danger_confirm(self._confirm, f"清空全部 {len(history)} 条记录"):
                    try:
                        HISTORY_FILE.write_text("[]", encoding="utf-8")
                        print(green("✅ 已清空记录"))
                    except Exception as e:
                        print(red(f"清空失败: {e}"))
                    ask()
                return
            if pick.isdigit() and 1 <= int(pick) <= len(shown):
                self._show_record_details(shown[int(pick) - 1])
                return
            return

    def _show_record_details(self, rec, only_wrong=False):
        details = rec.get("details") or []
        while True:
            shown_items = [d for d in details if (not only_wrong or not d.get("ok"))]
            clear_screen()
            print("=" * 46)
            print(f"  {rec.get('time', '')} · {rec.get('mode', '')} · 正确率 {rec.get('accuracy', 0)}%")
            print("=" * 46)
            if not details:
                print("这条记录没有逐题明细（旧版本记录的）。")
            else:
                by_number = {}
                for q in self.questions:
                    by_number.setdefault(str(q.number), q)
                if only_wrong:
                    print(f"只看错题（{len(shown_items)}/{len(details)} 题）")
                for d in shown_items:
                    mark = green("✔") if d.get("ok") else red("✘")
                    hit = by_number.get(str(d.get("n", "")))
                    missed = self.wrong_counts.get(hit.id, 0) if hit else 0
                    tag = f"   {red('累计错 ' + str(missed) + ' 次')}" if missed else ""
                    print(f"  {mark} {str(d.get('n', '')):>3}. {d.get('q', '')}{tag}")
            print("=" * 46)
            if not details:
                self._pause("按任意键返回...")
                return
            sys.stdout.write(dim("[w]只看错题  [a]全部题目  其它键返回 "))
            sys.stdout.flush()
            if KeyReader.available():
                try:
                    ch = KeyReader.getch().lower()
                except (KeyboardInterrupt, EOFError):
                    ch = "q"
                print()
            else:
                try:
                    ch = ask().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ch = "q"
            if ch == "w":
                only_wrong = True
                continue
            if ch == "a":
                only_wrong = False
                continue
            return
