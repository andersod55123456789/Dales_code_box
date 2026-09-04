import datetime

from trainlog.db import query, query_one
from trainlog.program import load_program

MAIN_LIFTS = [("back_squat", "Back squat"), ("deadlift", "Deadlift"),
              ("front_squat", "Front squat"), ("rdl", "Romanian deadlift"),
              ("barbell_row", "Barbell row")]


def _since(range_key):
    days = {"4w": 28, "12w": 84}.get(range_key)
    if days is None:
        return "0000-01-01"
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def strength_series(range_key="12w"):
    since = _since(range_key)
    out = []
    for eid, name in MAIN_LIFTS:
        rows = query(
            "SELECT d.log_date, d.cycle, d.week,"
            " MAX(s.actual_load) top_load,"
            " SUM(COALESCE(s.actual_reps,0)*COALESCE(s.actual_load,0)) tonnage"
            " FROM set_log s JOIN day_log d ON d.id=s.day_log_id"
            " WHERE s.exercise_id=? AND s.completed=1 AND d.log_date>=?"
            " GROUP BY d.log_date ORDER BY d.log_date", (eid, since))
        pts = [{"date": r["log_date"], "cycle": r["cycle"], "week": r["week"],
                "top_load": r["top_load"], "tonnage": r["tonnage"],
                "is_deload": r["week"] == 4} for r in rows if r["top_load"]]
        out.append({"exercise_id": eid, "name": name, "points": pts})
    return out


def weekly_tonnage(range_key="12w"):
    since = _since(range_key)
    rows = query(
        "SELECT d.cycle, d.week, d.week_repeat,"
        " SUM(COALESCE(s.actual_reps,0)*COALESCE(s.actual_load,0)) tonnage,"
        " MIN(d.log_date) first_date FROM set_log s"
        " JOIN day_log d ON d.id=s.day_log_id"
        " WHERE s.completed=1 AND d.log_date>=?"
        " GROUP BY d.cycle, d.week, d.week_repeat"
        " ORDER BY d.cycle, d.week, d.week_repeat", (since,))
    return [{"cycle": r["cycle"], "week": r["week"],
             "tonnage": r["tonnage"] or 0, "first_date": r["first_date"],
             "is_deload": r["week"] == 4} for r in rows]


def wellness_series(range_key="12w"):
    since = _since(range_key)
    rows = query("SELECT * FROM checkin WHERE checkin_date>=? "
                 "ORDER BY checkin_date", (since,))
    return [{"date": r["checkin_date"], "sleep_quality": r["sleep_quality"],
             "energy": r["energy"], "soreness": r["soreness"],
             "mood": r["mood"], "resting_hr": r["resting_hr"]} for r in rows]


def adherence_stats(range_key="12w"):
    since = _since(range_key)
    p = load_program()
    n_anchor = len(p["anchor"])
    full = {r["log_date"] for r in query(
        "SELECT d.log_date, COUNT(*) c FROM anchor_log a"
        " JOIN day_log d ON d.id=a.day_log_id"
        " WHERE a.field_key='__done__' AND a.completed=1"
        " GROUP BY d.log_date HAVING c>=?", (n_anchor,))}

    def streak_from(start):
        s, cur = 0, start
        while cur.isoformat() in full:
            s += 1
            cur -= datetime.timedelta(days=1)
        return s

    today = datetime.date.today()
    streak = max(streak_from(today),
                 streak_from(today - datetime.timedelta(days=1)))
    best, run, prev = 0, 0, None
    for ds in sorted(full):
        d = datetime.date.fromisoformat(ds)
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    weeks = query("SELECT COUNT(DISTINCT cycle||'-'||week||'-'||week_repeat) n"
                  " FROM day_log WHERE log_date>=?", (since,))
    possible = max(1, weeks[0]["n"] if weeks else 1)
    by_weekday = []
    for wd in ["monday", "tuesday", "wednesday", "thursday",
               "friday", "saturday", "sunday"]:
        r = query_one("SELECT COUNT(*) c FROM day_log WHERE weekday=?"
                      " AND day_complete=1 AND log_date>=?", (wd, since))
        c = r["c"] if r else 0
        by_weekday.append({"weekday": wd, "logged": c, "possible": possible,
                           "pct": round(100.0 * c / possible, 1)})
    cal = []
    for i in range(83, -1, -1):
        d = (today - datetime.timedelta(days=i))
        ds = d.isoformat()
        r = query_one("SELECT COUNT(*) c FROM anchor_log a"
                      " JOIN day_log d ON d.id=a.day_log_id"
                      " WHERE d.log_date=? AND a.field_key='__done__'"
                      " AND a.completed=1", (ds,))
        c = r["c"] if r else 0
        cal.append({"date": ds, "count": c,
                    "state": "full" if c >= n_anchor else
                             ("partial" if c else "none")})
    gating = query_one(
        "SELECT COUNT(*) c FROM day_log WHERE day_complete=1"
        " AND weekday IN ('monday','wednesday','friday') AND log_date>=?",
        (since,))
    return {"anchor_streak": streak, "anchor_best_streak": best,
            "by_weekday": by_weekday, "calendar": cal,
            "gating_done": gating["c"] if gating else 0,
            "gating_possible": possible * 3}


def _fmt_time(secs):
    if secs is None:
        return None
    secs = int(round(secs))
    return f"{secs // 60}:{secs % 60:02d}"


def test_metrics():
    out = []
    for m in load_program()["test_battery"]:
        rows = query("SELECT * FROM test_battery WHERE metric_key=?"
                     " ORDER BY test_date", (m["key"],))
        hist = [{"date": r["test_date"], "value": r["value_num"],
                 "text": r["value_text"], "cycle": r["cycle"],
                 "week": r["week"]} for r in rows]
        latest = hist[-1] if hist else None
        base = m.get("baseline")
        base_num = base
        if m.get("is_time") and isinstance(base, str) and ":" in base:
            mm, ss = base.split(":")
            base_num = int(mm) * 60 + int(ss)
        delta, good = None, None
        if latest and base_num is not None:
            delta = latest["value"] - base_num
            d = m.get("direction")
            if d == "up":
                good = delta > 0
            elif d == "down":
                good = delta < 0
            elif d == "hold":
                lo, hi = (m.get("target_range") or [None, None])
                good = (lo is None or latest["value"] >= lo) and \
                       (hi is None or latest["value"] <= hi)
        out.append({
            "key": m["key"], "name": m["name"], "unit": m.get("unit"),
            "direction": m.get("direction"), "is_time": bool(m.get("is_time")),
            "reference_only": bool(m.get("reference_only")),
            "auto_from_log": m.get("auto_from_log"),
            "baseline": base, "baseline_num": base_num,
            "latest": latest["value"] if latest else None,
            "latest_text": (latest.get("text") if latest else None) or
                           (_fmt_time(latest["value"]) if latest and
                            m.get("is_time") else
                            (latest["value"] if latest else None)),
            "latest_date": latest["date"] if latest else None,
            "delta": delta, "good": good, "history": hist,
        })
    return out


def auto_test_value(key):
    m = next((x for x in load_program()["test_battery"]
              if x["key"] == key), None)
    if not m or not m.get("auto_from_log"):
        return None
    since = (datetime.date.today() - datetime.timedelta(days=28)).isoformat()
    r = query_one("SELECT MAX(s.actual_load) v FROM set_log s"
                  " JOIN day_log d ON d.id=s.day_log_id"
                  " WHERE s.exercise_id=? AND s.completed=1 AND d.log_date>=?",
                  (m["auto_from_log"], since))
    return r["v"] if r else None


# --- Phase E: momentum, near-wins, next-goal ---------------------------


def _days_with_activity(start, end):
    """Set of log_dates in [start, end] that 'count' for momentum: day
    complete OR any completed set OR any completed anchor item (locked
    definition - anchor-only days count equally)."""
    rows = query(
        "SELECT DISTINCT d.log_date FROM day_log d"
        " LEFT JOIN set_log s ON s.day_log_id=d.id AND s.completed=1"
        " LEFT JOIN anchor_log a ON a.day_log_id=d.id AND a.completed=1"
        " WHERE d.log_date>=? AND d.log_date<=?"
        " AND (d.day_complete=1 OR s.id IS NOT NULL OR a.id IS NOT NULL)",
        (start, end))
    return {r["log_date"] for r in rows}


def momentum(date_str=None):
    """Weekly momentum rollup (Phase E). Trailing 7 days ending at date_str
    (default today). Target: any 5 of 7 days logged."""
    end = date_str or datetime.date.today().isoformat()
    end_d = datetime.date.fromisoformat(end)
    start_d = end_d - datetime.timedelta(days=6)
    active = _days_with_activity(start_d.isoformat(), end)
    return {"days_logged": len(active), "target": 5,
            "window": [start_d.isoformat(), end],
            "hit": len(active) >= 5}


def near_win(date_str):
    """One concrete near-win, computed at render time (Phase E). Priority:
    closest attribute level boundary, XP to next level, test metric within
    5% of best, else the momentum fallback."""
    # 1. attribute closest to next level
    row = query_one(
        "SELECT attribute, score, level FROM attribute_state"
        " ORDER BY (score - (CAST(score AS INTEGER) / 10) * 10) DESC LIMIT 1")
    if row and row["score"] > 0:
        remainder = row["score"] % 10
        if remainder > 0:
            away = int(round(10 - remainder))
            if away > 0:
                return (f"{away} points from {row['attribute'].capitalize()}"
                        f" level {row['level'] + 1}")
    # 2. XP to next account level
    from trainlog import xp as _xp
    st = _xp.get_state()
    need = st["xp_for_next_level"] - st["xp_into_level"]
    if need > 0:
        return f"{need} XP from level {st['level'] + 1}"
    # 3. test metric within 5% of all-time best
    for m in test_metrics():
        hist = [h["value"] for h in m["history"] if h["value"] is not None]
        if len(hist) < 2 or m["latest"] is None:
            continue
        best = min(hist) if m["direction"] == "down" else max(hist)
        if best and abs(m["latest"] - best) / abs(best) <= 0.05:
            if m["is_time"]:
                return f"{_fmt_time(abs(m['latest']-best))} from your best {m['name']}"
            return f"{abs(m['latest']-best):g} {m.get('unit') or ''} from your best {m['name']}".strip()
    # 4. fallback
    return "Log today to keep momentum alive"


def next_goal(date_str):
    """Post-workout next-goal line (Phase E, Task 24): the near-win plus,
    when a progression event fired today, the engine's next-session target."""
    base = near_win(date_str)
    ev = query_one(
        "SELECT e.last_recommendation_json rec FROM exercise_state e"
        " JOIN progression_event p ON p.exercise_id=e.exercise_id"
        " WHERE p.created_at LIKE ? ORDER BY p.id DESC LIMIT 1",
        (date_str + "%",))
    if ev and ev["rec"]:
        import json as _json
        try:
            rec = _json.loads(ev["rec"])
            tgt = rec.get("next_rep_target")
            if tgt:
                return f"{base} | Next: {rec.get('exercise_id', '')} - {tgt}"
        except (ValueError, TypeError):
            pass
    return base
