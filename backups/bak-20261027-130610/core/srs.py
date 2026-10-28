# -*- coding: utf-8 -*-
"""FSRS-6 调度核心（Anki 25.x 默认算法），纯公式、零依赖。

参数与公式对照 open-spaced-repetition/fsrs-rs 的 `model_v6.rs` / `inference_v6.rs`：
- 21 个参数，w[20] 同时是遗忘曲线衰减（decay = -w[20]）
- 经过的天数按整天四舍五入；0 天（同一天）走短期记忆公式
- 成功/失败、短期三条稳定性公式与官方一致

卡片字段（纯 dict，直接 JSON 存储）：
    state  : "new" / "review" / "relearning"
    d      : 难度 1..10
    s      : 稳定度（天）
    due    : 下次到期（epoch 秒）
    last   : 上次复习（epoch 秒），0 表示没复习过
    reps   : 累计复习次数
    lapses : 遗忘（评 1）次数
"""
import math
import time

# FSRS-6 官方默认参数（inference_v6.rs）
PARAMS = (
    0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001,
    1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
    1.8729, 0.5425, 0.0912, 0.0658, 0.1542,
)
W20 = 20

S_MIN = 0.01
S_MAX = 36500.0
D_MIN = 1.0
D_MAX = 10.0
MAX_INTERVAL = 36500
RELEARN_SECONDS = 600      # 评 1（重来）后 10 分钟再来
RETENTION = 0.9            # 目标记忆率


def decay(params=PARAMS):
    return -float(params[W20])


def factor(params=PARAMS):
    return 0.9 ** (1.0 / decay(params)) - 1.0


def _clamp(v, lo=S_MIN, hi=S_MAX):
    return max(lo, min(hi, v))


def retrievability(elapsed_days, stability, params=PARAMS):
    """经过 elapsed_days 天后仍记得的概率（天数取整，与官方一致）。"""
    s = max(S_MIN, float(stability))
    t = max(0.0, round(float(elapsed_days)))
    return (1.0 + factor(params) * t / s) ** decay(params)


def interval_days(stability, retention=RETENTION, params=PARAMS,
                  max_interval=MAX_INTERVAL):
    """按目标记忆率反推间隔天数（保留小数，落盘时再取整）。"""
    s = max(S_MIN, float(stability))
    r = max(0.0001, min(0.9999, float(retention)))
    d = decay(params)
    return max(1.0, min(float(max_interval),
                        s / factor(params) * (r ** (1.0 / d) - 1.0)))


def init_stability(rating, params=PARAMS):
    return _clamp(float(params[int(rating) - 1]))


def init_difficulty(rating, params=PARAMS):
    d = params[4] - math.exp(params[5] * (int(rating) - 1)) + 1.0
    return max(D_MIN, min(D_MAX, d))


def next_difficulty(d, rating, params=PARAMS):
    delta = -params[6] * (int(rating) - 3)
    nd = d + (10.0 - d) / 9.0 * delta
    nd = params[7] * init_difficulty(4, params) + (1 - params[7]) * nd
    return max(D_MIN, min(D_MAX, nd))


def stability_after_success(s, r, d, rating, params=PARAMS):
    hard = params[15] if int(rating) == 2 else 1.0
    easy = params[16] if int(rating) == 4 else 1.0
    gain = (math.exp(params[8]) * (11.0 - d) * s ** (-params[9]) *
            (math.exp((1.0 - r) * params[10]) - 1.0) * hard * easy)
    return _clamp(s * (1.0 + gain))


def stability_after_failure(s, r, d, params=PARAMS):
    new_s_min = s / math.exp(params[17] * params[18])
    new_s = (params[11] * d ** (-params[12]) *
             ((s + 1.0) ** params[13] - 1.0) * math.exp((1.0 - r) * params[14]))
    return _clamp(min(new_s_min, new_s))


def stability_short_term(s, rating, params=PARAMS):
    """同一天内的再次复习。"""
    sinc = (math.exp(params[17] * (int(rating) - 3 + params[18])) *
            s ** (-params[19]))
    if int(rating) >= 2:
        sinc = max(sinc, 1.0)
    return _clamp(s * sinc)


def new_card(now=None):
    now = time.time() if now is None else float(now)
    return {"state": "new", "d": 0.0, "s": 0.0, "due": now, "last": 0.0,
            "reps": 0, "lapses": 0}


def review(card, rating, now=None, retention=RETENTION, params=PARAMS,
           max_interval=MAX_INTERVAL):
    """按 1..4 评分更新卡片，返回新卡片（不修改入参）。"""
    rating = int(rating)
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating 必须是 1..4")
    now = time.time() if now is None else float(now)
    c = dict(card or new_card(now))
    reps = int(c.get("reps", 0))
    last = float(c.get("last", 0.0))
    s = float(c.get("s", 0.0))
    d = float(c.get("d", 0.0))

    if reps == 0 or c.get("state") in (None, "", "new"):
        s = init_stability(rating, params)
        d = init_difficulty(rating, params)
    else:
        delta_t = max(0, int(round((now - last) / 86400.0))) if last else 0
        r = retrievability(delta_t, s, params)
        if delta_t == 0:
            s = stability_short_term(s, rating, params)
        elif rating == 1:
            s = stability_after_failure(s, r, d, params)
        else:
            s = stability_after_success(s, r, d, rating, params)
        d = next_difficulty(d, rating, params)

    c["reps"] = reps + 1
    c["last"] = now
    c["d"] = d
    c["s"] = s
    if rating == 1:
        c["lapses"] = int(c.get("lapses", 0)) + 1
        c["state"] = "relearning"
        c["due"] = now + RELEARN_SECONDS
    else:
        ivl = int(round(interval_days(s, retention, params, max_interval)))
        c["state"] = "review"
        c["due"] = now + max(1, ivl) * 86400.0
    return c


def due_now(card, now=None):
    now = time.time() if now is None else float(now)
    return float(card.get("due", 0)) <= now


def human_interval(card, now=None):
    """给界面用的“下次 N 天 / N 分钟”文案。"""
    now = time.time() if now is None else float(now)
    secs = float(card.get("due", now)) - now
    if secs <= 0:
        return "现在"
    if secs < 3600:
        return f"{max(1, int(secs // 60))} 分钟"
    if secs < 86400:
        return f"{int(secs // 3600)} 小时"
    return f"{int(secs // 86400)} 天"


def build_queue(cards, questions, now=None, new_limit=20):
    """返回 [(qid, is_new)]：到期的先来，再补最多 new_limit 张新卡。"""
    now = time.time() if now is None else float(now)
    due, new = [], []
    for q in questions:
        card = cards.get(q.id)
        if card is None:
            new.append(q.id)
        elif due_now(card, now):
            due.append(q.id)
    due.sort(key=lambda qid: float(cards[qid].get("due", 0)))
    return [(qid, False) for qid in due] + [(qid, True) for qid in new[:new_limit]]
