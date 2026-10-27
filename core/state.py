# -*- coding: utf-8 -*-
"""状态持久化：错题/收藏/进度/错题次数与状态、历史记录。"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.ui import ask, dim
from core.safe_io import atomic_write_json, atomic_write_text, recover
from core.paths import (
    BASE_DIR, BANKS_DIR, HISTORY_FILE, STATE_FILE, STATE_VERSION,
    bank_abs_path, normalize_bank_key,
)

logger = logging.getLogger("quiz.state")


class StateMixin:
    """只依赖 self 的状态相关方法，由 ShirohaQuiz 继承。"""

    def _fix_progress(self):
        if self.questions and (self.current_idx < 0 or self.current_idx >= len(self.questions)):
            self.current_idx = 0

    def load_state(self):
        for target in (STATE_FILE, HISTORY_FILE):
            try:
                if recover(target):
                    print(dim(f"⚠️ 检测到未完成的写入，已用备份恢复 {target.name}"))
            except Exception:
                pass
        if not STATE_FILE.exists():
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"读取状态失败: {e}")
            return

        if data.get("version") == STATE_VERSION:
            raw_banks = data.get("banks", {}) or {}
            self.bank_path = normalize_bank_key(data.get("bank_path", "") or "")
            self.current_idx = data.get("current_idx", 0) or 0
            self.auto_next = data.get("auto_next", True)
        else:
            # v1 迁移：全局错题/收藏归到当时那本题库名下
            key = normalize_bank_key(data.get("bank_path", "") or "")
            raw_banks = {}
            if key:
                raw_banks[key] = {
                    "wrong": data.get("wrong_book", []),
                    "favorites": data.get("favorites", []),
                    "progress": data.get("current_idx", 0),
                }
            self.bank_path = key
            self.current_idx = data.get("current_idx", 0) or 0

        self.prefs = data.get("prefs") or {"global": {}, "banks": {}}

        # 绝对路径键 -> 相对键（便携化迁移），同键合并
        self.banks_state = {}
        for key, slot in raw_banks.items():
            new_key = normalize_bank_key(key)
            old = self.banks_state.get(new_key)
            if old:
                old["wrong"] = list(dict.fromkeys(list(old.get("wrong", [])) + list(slot.get("wrong", []))))
                old["favorites"] = list(dict.fromkeys(list(old.get("favorites", [])) + list(slot.get("favorites", []))))
                merged_counts = dict(old.get("wrong_counts") or {})
                merged_counts.update(slot.get("wrong_counts") or {})
                old["wrong_counts"] = merged_counts
            else:
                self.banks_state[new_key] = slot

        if self.bank_path:
            target = bank_abs_path(self.bank_path)
            if target.exists():
                self._parse_bank(str(target), silent=True)
            else:
                for cand in (BANKS_DIR / Path(self.bank_path).name, BASE_DIR / Path(self.bank_path).name):
                    if cand.exists():
                        self._parse_bank(str(cand), silent=True)
                        break

    # ---------- 偏好：题库 -> 全局 -> 内置 ----------
    def pref(self, section, key, builtin=None):
        banks = (self.prefs.get("banks") or {}).get(self.bank_key or "", {})
        if key in (banks.get(section) or {}):
            return banks[section][key]
        g = (self.prefs.get("global") or {}).get(section, {})
        return g.get(key, builtin)

    def remember(self, section, key, value):
        self.prefs.setdefault("global", {}).setdefault(section, {})[key] = value
        if self.bank_key:
            self.prefs.setdefault("banks", {}).setdefault(self.bank_key, {}).setdefault(section, {})[key] = value
        self.save_state()

    def pref_ask(self, section, key, builtin, label):
        """带记忆的提示：回车沿用上次，d 恢复内置默认。"""
        cur = self.pref(section, key, builtin)
        print(f"{label}\n   回车=上次({cur})   d=默认({builtin})")
        raw = ask("> ").strip()
        if raw.lower() == "d":
            self.remember(section, key, builtin)
            return str(builtin)
        val = raw or str(cur)
        self.remember(section, key, val)
        return val


    def _note_bank_hash(self, key, digest):
        """记录题库内容哈希；路径变了但内容相同的旧记录会被认领过来。"""
        if not key or not digest:
            return
        slot = self.banks_state.get(key)
        if slot is None:
            slot = {
                "wrong": [], "favorites": [], "progress": 0,
                "wrong_counts": {}, "wrong_status": {}, "wrong_last": {},
                "right_counts": {}, "wrong_numbers": {}, "fav_numbers": {},
            }
            self.banks_state[key] = slot
        if slot.get("content_hash") == digest:
            return
        adopted = False
        if not slot.get("wrong") and not slot.get("favorites"):
            for other_key, other in self.banks_state.items():
                if other_key == key:
                    continue
                if other.get("content_hash") != digest:
                    continue
                if not (other.get("wrong") or other.get("favorites")):
                    continue
                for field in ("wrong", "favorites", "progress", "wrong_counts",
                              "wrong_status", "wrong_last", "right_counts",
                              "wrong_numbers", "fav_numbers"):
                    if field in other:
                        slot[field] = other[field]
                adopted = True
                break
        slot["content_hash"] = digest
        if adopted:
            print(dim("↪️ 识别到同名内容的旧题库记录，已自动继承错题与收藏"))

    def _bank_slot(self):
        if not self.bank_key:
            return {"wrong": [], "favorites": [], "progress": 0}
        return self.banks_state.setdefault(self.bank_key, {"wrong": [], "favorites": [], "progress": 0})

    def _adopt_bank_state(self):
        slot = self._bank_slot()
        valid = {q.id for q in self.questions}
        by_number = {}
        for q in self.questions:
            by_number.setdefault(str(q.number), q.id)

        def remap(ids, numbers):
            fixed = []
            for qid in ids or []:
                if qid in valid:
                    fixed.append(qid)
                    continue
                alt = by_number.get(str((numbers or {}).get(qid, "")))
                if alt:
                    fixed.append(alt)
            return list(dict.fromkeys(fixed))

        self.wrong_book = remap(slot.get("wrong", []), slot.get("wrong_numbers"))
        self.favorites = remap(slot.get("favorites", []), slot.get("fav_numbers"))
        self.wrong_counts = {k: int(v) for k, v in (slot.get("wrong_counts") or {}).items()}
        self.wrong_status = {k: str(v) for k, v in (slot.get("wrong_status") or {}).items()}
        self.wrong_last = {k: float(v) for k, v in (slot.get("wrong_last") or {}).items()}
        self.right_counts = {k: int(v) for k, v in (slot.get("right_counts") or {}).items()}
        if 0 <= slot.get("progress", 0) < len(self.questions):
            self.current_idx = slot["progress"]

    def save_state(self):
        if self.bank_key:
            number_of = {q.id: str(q.number) for q in self.questions}
            _prev = self.banks_state.get(self.bank_key) or {}
            self.banks_state[self.bank_key] = {
                    "content_hash": _prev.get("content_hash", ""),
                    "wrong": list(dict.fromkeys(self.wrong_book)),
                    "favorites": list(dict.fromkeys(self.favorites)),
                    "progress": self.current_idx,
                    "wrong_counts": {k: v for k, v in self.wrong_counts.items() if k in self.wrong_book},
                    "wrong_status": {k: v for k, v in self.wrong_status.items() if k in self.wrong_book},
                    "wrong_last": {k: v for k, v in self.wrong_last.items() if k in self.wrong_book},
                    "right_counts": {k: v for k, v in self.right_counts.items() if k in self.wrong_book},
                    # 便携/缓存重建后题目 id 会变，靠题号兜底恢复
                    "wrong_numbers": {qid: number_of.get(qid, "") for qid in self.wrong_book},
                    "fav_numbers": {qid: number_of.get(qid, "") for qid in self.favorites},
                }
        data = {
            "version": STATE_VERSION,
            "bank_path": self.bank_path,
            "current_idx": self.current_idx,
            "auto_next": self.auto_next,
            "banks": self.banks_state,
            "prefs": self.prefs,
        }
        try:
            atomic_write_json(STATE_FILE, data)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    def _cleanup_records(self):
        if not self.questions:
            return
        valid_ids = {q.id for q in self.questions}
        self.wrong_book = [qid for qid in self.wrong_book if qid in valid_ids]
        self.favorites = [qid for qid in self.favorites if qid in valid_ids]
        self.right_counts = {k: v for k, v in self.right_counts.items() if k in valid_ids}
        self.save_state()

    def save_history(self, mode, total, correct, duration, details=None):
        record = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "bank": self.bank_name,
            "mode": mode,
            "total": total,
            "correct": correct,
            "accuracy": round((correct / total * 100) if total > 0 else 0, 1),
            "duration": int(duration),
        }
        if details:
            record["details"] = details[:120]
        history = []
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                pass
        history.append(record)
        try:
            atomic_write_json(HISTORY_FILE, history[-200:])
        except Exception:
            pass

    @staticmethod
    def _load_history():
        if not HISTORY_FILE.exists():
            return []
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            return []
