"""Fitness attributes - the 'character sheet' (Phase C, Task 16).

Five 0-100 scores recomputed from real logged data on day-complete and
test-battery save. All formulas are locked in PHASE2/06_TASKS.md. This is a
derived rollup, never a hand-tracked counter. Read-only against the engine.
"""
import datetime
import json

from trainlog.db import execute, now, query, query_one
from trainlog.program import load_program

ATTRIBUTES = ("strength", "endurance", "agility", "mobility", "conditioning")

# Strength reference: the three big lifts and their seeded start loads.
STRENGTH_LIFTS = {"back_squat": 185.0, "deadlift": 185.0, "ohp": 95.0}


def _level(score):
    return int(score // 10) + 1


def _strength():
    rows = query(
        "SELECT exercise_id, current_load FROM exercise_state"
        " WHERE exercise_id IN ('back_squat','deadlift','ohp')")
    cur = {r["exercise_id"]: r["current_load"] for r in rows}
    ratios, detail = [], []
    for eid, base in STRENGTH_LIFTS.items():
        load = cur.get(eid) or base
        ratios.append(load / base)
        detail.append(f"{eid} {load:g} / {base:g} baseline")
    score = 100 * min(1.5, sum(ratios) / len(ratios)) / 1.5
    return score, {"inputs": detail}


def _endurance():
    # 60% Saturday Zone-2: trailing avg of last 4 logged Saturdays vs target.
    p = load_program()
    target = None
    sat = p["days"].get("saturday", {})
    for blk in (sat.get("A") or []) + (sat.get("B") or []):
        for ex in blk.get("exercises", []):
            if ex.get("kind") == "cardio":
                for f in ex.get("extra_fields", []):
                    if f.get("key") == "minutes":
                        target = f.get("default")
    target = target or 60
    rows = query(
        "SELECT m.value_num v FROM metric_log m JOIN day_log d"
        " ON d.id=m.day_log_id WHERE d.weekday='saturday'"
        " AND m.field_key='minutes' AND m.value_num IS NOT NULL"
        " ORDER BY d.log_date DESC LIMIT 4")
    if rows:
        actual = sum(r["v"] for r in rows) / len(rows)
        z2 = min(1.2, actual / target) / 1.2 * 100
    else:
        actual = 0
        z2 = 50.0
    # 40% 1-mile test: baseline (first recorded) / best.
    mile = query(
        "SELECT value_num FROM test_battery WHERE metric_key='mile_1'"
        " AND value_num IS NOT NULL ORDER BY test_date")
    if mile:
        baseline, best = mile[0]["value_num"], min(r["value_num"] for r in mile)
        test = min(1.2, baseline / best) / 1.2 * 100
    else:
        baseline = best = None
        test = 50.0
    score = 0.6 * z2 + 0.4 * test
    return score, {"inputs": [
        f"zone2 avg {actual:g} / target {target} min (last {len(rows)} sat)",
        f"mile {('n/a' if best is None else str(best))} vs baseline {baseline}"]}


def _agility():
    # Numeric Tuesday drills if present (5-10-5 etc.), else Tue adherence.
    drills = query(
        "SELECT field_key, value_num FROM metric_log WHERE field_key IN"
        " ('best_time_s','ladder_time_s') AND value_num IS NOT NULL"
        " ORDER BY created_at")
    if drills:
        by = {}
        for r in drills:
            by.setdefault(r["field_key"], []).append(r["value_num"])
        scores = []
        for vals in by.values():
            base, best = vals[0], min(vals)
            scores.append(min(1.2, base / best) / 1.2 * 100)
        return sum(scores) / len(scores), {"inputs": [
            f"{k} best {min(v):g}s vs baseline {v[0]:g}s"
            for k, v in by.items()]}
    since = (datetime.date.today() - datetime.timedelta(days=28)).isoformat()
    r = query_one(
        "SELECT COUNT(*) c FROM day_log WHERE weekday='tuesday'"
        " AND day_complete=1 AND log_date>=?", (since,))
    tot = query_one(
        "SELECT COUNT(*) c FROM day_log WHERE weekday='tuesday'"
        " AND log_date>=?", (since,))
    pct = 100.0 * (r["c"] if r else 0) / max(1, tot["c"] if tot else 1)
    return pct, {"inputs": [f"tuesday adherence {r['c'] if r else 0}"
                            f"/{tot['c'] if tot else 1} last 28d (fallback)"]}


def _mobility():
    # 70% anchor consistency (trailing 14 days fully complete), 30% sit-and-reach.
    p = load_program()
    n_anchor = len(p["anchor"])
    full = {r["log_date"] for r in query(
        "SELECT d.log_date, COUNT(*) c FROM anchor_log a JOIN day_log d"
        " ON d.id=a.day_log_id WHERE a.field_key='__done__' AND a.completed=1"
        " GROUP BY d.log_date HAVING c>=?", (n_anchor,))}
    today = datetime.date.today()
    days = [(today - datetime.timedelta(days=i)).isoformat()
            for i in range(14)]
    anchor_pct = 100.0 * sum(1 for d in days if d in full) / 14
    sr = query(
        "SELECT value_num FROM test_battery WHERE metric_key='sit_and_reach'"
        " AND value_num IS NOT NULL ORDER BY test_date")
    if sr:
        base, best = sr[0]["value_num"], max(r["value_num"] for r in sr)
        reach = min(1.2, best / base) / 1.2 * 100 if base else 50.0
    else:
        base = best = None
        reach = 50.0
    score = 0.7 * anchor_pct + 0.3 * reach
    return score, {"inputs": [
        f"anchor {sum(1 for d in days if d in full)}/14 days full",
        f"sit-and-reach {best} vs baseline {base}"]}


def _conditioning():
    # Weekly adherence: days with any logged content over trailing 28 days,
    # as a fraction of 28 (every day has content in this program).
    today = datetime.date.today()
    since = (today - datetime.timedelta(days=27)).isoformat()
    rows = query(
        "SELECT DISTINCT d.log_date FROM day_log d"
        " LEFT JOIN set_log s ON s.day_log_id=d.id AND s.completed=1"
        " LEFT JOIN anchor_log a ON a.day_log_id=d.id AND a.completed=1"
        " WHERE d.log_date>=?"
        " AND (d.day_complete=1 OR s.id IS NOT NULL OR a.id IS NOT NULL)",
        (since,))
    n = len({r["log_date"] for r in rows})
    return 100.0 * n / 28, {"inputs": [f"{n}/28 days with any logged content"]}


_COMPUTERS = {"strength": _strength, "endurance": _endurance,
              "agility": _agility, "mobility": _mobility,
              "conditioning": _conditioning}


def recompute_attributes(path=None):
    """Recompute all five attributes and upsert attribute_state rows. Called
    from day-complete and test-battery save - never on page load."""
    out = {}
    for attr in ATTRIBUTES:
        score, detail = _COMPUTERS[attr]()
        score = round(max(0.0, min(100.0, score)), 1)
        # keep a short dated history for the sparkline (cap 30)
        prior = query_one(
            "SELECT detail_json FROM attribute_state WHERE attribute=?",
            (attr,), path=path)
        history = []
        if prior and prior["detail_json"]:
            try:
                history = json.loads(prior["detail_json"]).get("history", [])
            except (ValueError, TypeError):
                history = []
        history.append({"date": datetime.date.today().isoformat(),
                        "score": score})
        detail["history"] = history[-30:]
        execute(
            "INSERT INTO attribute_state (attribute, score, level,"
            " detail_json, last_computed_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT(attribute) DO UPDATE SET score=excluded.score,"
            " level=excluded.level, detail_json=excluded.detail_json,"
            " last_computed_at=excluded.last_computed_at",
            (attr, score, _level(score), json.dumps(detail), now()),
            path=path)
        out[attr] = score
    return out


def get_attributes(path=None):
    """All five attributes with parsed detail for the character sheet."""
    rows = query("SELECT * FROM attribute_state", path=path)
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(r["detail_json"]) if r["detail_json"] else {}
        except (ValueError, TypeError):
            d["detail"] = {}
        out.append(d)
    order = {a: i for i, a in enumerate(ATTRIBUTES)}
    return sorted(out, key=lambda x: order.get(x["attribute"], 99))
