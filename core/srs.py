# -*- coding: utf-8 -*-
"""FSRS-6 调度核心（Anki 25.x 默认算法）+ 学习步长 / Leech。

公式与参数对照 open-spaced-repetition/fsrs-rs：
- `model_v6.rs`：21 参数、decay=-w[20]、成功/失败/同日三条稳定性公式
- `inference_v6.rs`：FSRS6_DEFAULT_PARAMETERS
- 学习步长与 Leech 按 Anki 默认行为在调度层实现（不改 FSRS 公式）

卡片字段（纯 dict）：
    state  : "new" / "learning" / "review" / "relearning"
    step   : 当前学习步长下标（0 起）
    d, s   : FSRS 难度 / 稳定度
    due    : 下次到期（epoch 秒）
    last   : 上次复习（epoch 秒）
    reps   : 累计复习次数
    lapses : 遗忘（评 1）次数
    leech  : 是否已暂停（连续遗忘达到阈值）
"""
import math
import random
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
RETENTION = 0.9

# 学习步长（秒）：新卡 1 分钟、10 分钟；重新学习 10 分钟
STEPS_DEFAULT = (60.0, 600.0)
RELEARN_DEFAULT = 600.0
LEECH_DEFAULT = 8

# 对齐 Anki：默认凌晨 4 点换天、复习间隔 ±5% 模糊、提前 20 分钟可学
DAY_START_DEFAULT = 4
FUZZ_DEFAULT = 0.05
LEARN_AHEAD_DEFAULT = 1200.0


def decay(params=PARAMS):
    return -float(params[W20])


def factor(params=PARAMS):
    return 0.9 ** (1.0 / decay(params)) - 1.0


def _clamp(v, lo=S_MIN, hi=S_MAX):
    return max(lo, min(hi, v))


def retrievability(elapsed_days, stability, params=PARAMS):
    s = max(S_MIN, float(stability))
    t = max(0.0, round(float(elapsed_days)))
    return (1.0 + factor(params) * t / s) ** decay(params)


def interval_days(stability, retention=RETENTION, params=PARAMS,
                  max_interval=MAX_INTERVAL):
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
    sinc = (math.exp(params[17] * (int(rating) - 3 + params[18])) *
            s ** (-params[19]))
    if int(rating) >= 2:
        sinc = max(sinc, 1.0)
    return _clamp(s * sinc)


def new_card(now=None):
    now = time.time() if now is None else float(now)
    return {"state": "new", "step": 0, "d": 0.0, "s": 0.0, "due": now,
            "last": 0.0, "reps": 0, "lapses": 0, "leech": False}


def _advance_memory(c, rating, now, params):
    """按 FSRS 公式推进 s/d（学习步长与复习共用）。"""
    reps = int(c.get("reps", 0))
    last = float(c.get("last", 0.0))
    s = float(c.get("s", 0.0))
    d = float(c.get("d", 0.0))
    if reps == 0 or s <= 0:
        s = init_stability(rating, params)
        d = init_difficulty(rating, params)
    else:
        delta_t = max(0, int(round((now - last) / 86400.0))) if last else 0
        r = retrievability(delta_t, s, params)
        if delta_t == 0:
            s = stability_short_term(s, rating, params)
        elif int(rating) == 1:
            s = stability_after_failure(s, r, d, params)
        else:
            s = stability_after_success(s, r, d, rating, params)
        d = next_difficulty(d, rating, params)
    return s, d


def is_learning(card):
    return str(card.get("state")) in ("learning", "relearning")


def review(card, rating, now=None, retention=RETENTION, params=PARAMS,
           max_interval=MAX_INTERVAL, steps=STEPS_DEFAULT,
           relearn=RELEARN_DEFAULT, leech=LEECH_DEFAULT,
           fuzz=0.0, rng=None):
    """按 1..4 评分更新卡片，返回新卡片（不修改入参）。"""
    rating = int(rating)
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating 必须是 1..4")
    now = time.time() if now is None else float(now)
    steps = tuple(float(x) for x in (steps or STEPS_DEFAULT))
    relearn = float(relearn)

    c = dict(card or new_card(now))
    state = str(c.get("state") or "new")
    step = int(c.get("step", 0))
    reps = int(c.get("reps", 0))

    s, d = _advance_memory(c, rating, now, params)
    c["s"] = s
    c["d"] = d
    c["reps"] = reps + 1
    c["last"] = now

    def graduate():
        ivl = fuzz_interval(interval_days(s, retention, params, max_interval),
                            fuzz, rng)
        c["state"] = "review"
        c["step"] = 0
        c["due"] = now + max(1, ivl) * 86400.0

    if state == "new" or reps == 0:
        if rating in (1, 2):
            c["state"] = "learning"
            c["step"] = 0
            c["due"] = now + steps[0]
        elif rating == 4:
            graduate()
        else:
            if len(steps) > 1:
                c["state"] = "learning"
                c["step"] = 1
                c["due"] = now + steps[1]
            else:
                graduate()
        c["leech"] = False
        return c

    if state in ("learning", "relearning"):
        if rating == 1:
            c["state"] = state
            c["step"] = 0
            c["due"] = now + (steps[0] if state == "learning" else relearn)
        elif rating == 2:
            c["state"] = state
            if state == "learning" and step < len(steps):
                c["due"] = now + steps[step]
            else:
                c["due"] = now + (steps[-1] if steps else relearn)
        elif rating == 3:
            if state == "learning" and step + 1 < len(steps):
                c["step"] = step + 1
                c["due"] = now + steps[c["step"]]
            else:
                graduate()
        else:
            graduate()
        return c

    # 复习阶段
    if rating == 1:
        c["lapses"] = int(c.get("lapses", 0)) + 1
        c["state"] = "relearning"
        c["step"] = 0
        c["due"] = now + relearn
        if int(c["lapses"]) >= int(leech):
            c["leech"] = True
    else:
        ivl = fuzz_interval(interval_days(s, retention, params, max_interval),
                            fuzz, rng)
        c["state"] = "review"
        c["step"] = 0
        c["due"] = now + max(1, ivl) * 86400.0
    return c


def day_key(now=None, day_start=DAY_START_DEFAULT):
    """按“日切点”返回学习日日期串（默认凌晨 4 点前算前一天）。"""
    now = time.time() if now is None else float(now)
    shifted = now - float(day_start) * 3600.0
    return time.strftime("%Y-%m-%d", time.localtime(shifted))


def day_start_ts(now=None, day_start=DAY_START_DEFAULT):
    """当前学习日的起点时间戳。"""
    now = time.time() if now is None else float(now)
    shifted = now - float(day_start) * 3600.0
    lt = time.localtime(shifted)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            0, 0, 0, 0, 0, -1))
    return midnight + float(day_start) * 3600.0


def fuzz_interval(interval, fuzz=FUZZ_DEFAULT, rng=None):
    """复习间隔 ±fuzz 随机（Anki 默认 ±5%）；小于 3 天不动。"""
    ivl = max(1, int(round(float(interval))))
    fuzz = float(fuzz or 0.0)
    if fuzz <= 0 or ivl < 3:
        return ivl
    delta = max(1, int(round(ivl * fuzz)))
    r = rng or random
    return max(1, ivl + r.randint(-delta, delta))


def due_now(card, now=None):
    now = time.time() if now is None else float(now)
    return float(card.get("due", 0)) <= now


def human_interval(card, now=None):
    now = time.time() if now is None else float(now)
    secs = float(card.get("due", now)) - now
    if secs <= 0:
        return "现在"
    if secs < 3600:
        return f"{max(1, int(secs // 60))} 分钟"
    if secs < 86400:
        return f"{int(secs // 3600)} 小时"
    return f"{int(secs // 86400)} 天"


def human_state(card):
    st = str(card.get("state") or "new")
    return {"new": "新卡", "learning": "学习中", "review": "复习",
            "relearning": "重新学习"}.get(st, st)


def build_queue(cards, questions, now=None, new_limit=20, review_limit=200,
                learn_ahead=0.0):
    """到期的先来（最多 review_limit），再补新卡（最多 new_limit）。

    已暂停（leech）的卡片不进入队列；`learn_ahead` > 0 且队列里已有
    到期/新卡时，把该窗口内到期的学习中卡片排在队尾（Anki 的“提前学习”）。
    """
    now = time.time() if now is None else float(now)
    ahead_limit = now + max(0.0, float(learn_ahead or 0.0))
    due, new, ahead = [], [], []
    for q in questions:
        card = cards.get(q.id)
        if card is None or str(card.get("state") or "new") == "new":
            new.append(q.id)
        elif card.get("leech"):
            continue
        elif due_now(card, now):
            due.append(q.id)
        elif (learn_ahead and is_learning(card)
              and float(card.get("due", 0)) <= ahead_limit):
            ahead.append(q.id)
    key = lambda qid: float(cards[qid].get("due", 0))
    due.sort(key=key)
    ahead.sort(key=key)
    queue = ([(qid, False) for qid in due[:max(0, int(review_limit))]] +
             [(qid, True) for qid in new[:max(0, int(new_limit))]])
    if queue and learn_ahead:
        queue += [(qid, False) for qid in ahead]
    return queue
