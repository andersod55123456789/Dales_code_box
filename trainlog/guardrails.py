"""Six guardrail rules. Each returns a warning dict or None."""
import datetime
import json

from trainlog import engine as E
from trainlog.db import execute, now, query, query_one
from trainlog.program import load_program


def _checkin(date):
    r = query_one("SELECT * FROM checkin WHERE checkin_date=?", (date,))
    return dict(r) if r else None


def _recent_checkins(date, days):
    start = (datetime.date.fromisoformat(date) -
             datetime.timedelta(days=days)).isoformat()
    return [dict(r) for r in query(
        "SELECT * FROM checkin WHERE checkin_date<=? AND checkin_date>=? "
        "ORDER BY checkin_date DESC", (date, start))]


def _presses(day):
    p = load_program()
    ids = set()
    for wd, d in p["days"].items():
        for block in (d, d.get("week_a") or {}, d.get("week_b") or {}):
            for ex in block.get("exercises", []) or []:
                if ex.get("is_press"):
                    ids.add(ex["id"])
    return [e["id"] for e in day["exercises"] if e["id"] in ids and not e["skipped"]]


def _landing_exercises(day):
    return [e for e in day["exercises"]
            if e.get("landings_per_rep") and not e["skipped"]]


def knee_landings(date, day):
    c = _checkin(date)
    if not c:
        return None
    status = c.get("knee_status")
    if status not in ("niggle", "pain"):
        return None
    count = day["landings"]["count"]
    if count == 0:
        return None
    exs = _landing_exercises(day)
    msg = (f"Knee flagged this morning ({status}). "
           f"{count} high-force landings planned.")
    if status == "pain":
        return {"rule_key": "knee_landings", "severity": "serious",
                "message": msg,
                "suggestion": "Skip the jumps today. Keep the sled and KB swings.",
                "payload": {"skip": [e["id"] for e in exs]}}
    parts, new = [], 0
    for e in exs:
        s2 = max(1, E.round_half_up(e["sets"] * 0.5))
        parts.append(f"{e['name'].lower()} {e['sets']} -> {s2}")
        new += s2 * (e["target_reps"] or 0) * e["landings_per_rep"]
    return {"rule_key": "knee_landings", "severity": "warning", "message": msg,
            "suggestion": f"Cut the landing sets: {', '.join(parts)}. "
                          f"New count: {new}.",
            "payload": {"scale_sets": {e["id"]: 0.5 for e in exs}}}


def pec_pressing(date, day):
    c = _checkin(date)
    if not c:
        return None
    status = c.get("pec_status")
    if status not in ("niggle", "pain"):
        return None
    presses = _presses(day)
    if not presses:
        return None
    msg = (f"Pec flagged this morning ({status}). "
           f"{len(presses)} pressing movements planned today.")
    if status == "pain":
        return {"rule_key": "pec_pressing", "severity": "critical", "message": msg,
                "suggestion": "Skip all pressing today. Keep the pulling work - "
                              "it is pain-free.",
                "payload": {"skip": presses}}
    bodyweight = [i for i in presses if i in ("push_ups",)]
    loaded = [i for i in presses if i not in bodyweight]
    pl = {"scale_load": {i: 0.8 for i in loaded}}
    if bodyweight:
        pl["skip"] = bodyweight
    sug = "Drop pressing loads 20%"
    if bodyweight:
        sug += " and cut the push-up finisher"
    return {"rule_key": "pec_pressing", "severity": "warning", "message": msg,
            "suggestion": sug + ".", "payload": pl}


def shoulder_ohp_backoff(date, day):
    p = load_program()
    g = p["guardrails"]
    recent = _recent_checkins(date, 28)
    n = sum(1 for c in recent if c.get("shoulder_status") == "pain")
    if n < g.get("shoulder_pain_events_per_cycle", 2):
        return None
    start = (datetime.date.fromisoformat(date) -
             datetime.timedelta(days=28)).isoformat()
    if query_one("SELECT 1 FROM adjustment WHERE rule_key='shoulder_ohp_backoff'"
                 " AND status='applied' AND scope_date>=?", (start,)):
        return None
    st = query_one("SELECT * FROM program_state WHERE id=1")
    off = st["ohp_cycle_offset"] if st else 0
    cfg = p["config"]
    a = E.ohp_prescription(day["cycle"], day["week"], off, cfg)
    b = E.ohp_prescription(day["cycle"], day["week"], off + 1, cfg)
    return {"rule_key": "shoulder_ohp_backoff", "severity": "serious",
            "message": f"Shoulder pain logged {n} times in the last 4 weeks.",
            "suggestion": f"Back OHP off one cycle: {a['sets']}x5 @ {a['load']} "
                          f"-> {b['sets']}x5 @ {b['load']}.",
            "payload": {"ohp_cycle_offset_delta": 1}}


def soreness_repeat_week(date, day):
    from trainlog.logbook import gating_progress, get_state
    p = load_program()
    g = p["guardrails"]
    if not day["is_gating_day"] or day["day_complete"]:
        return None
    st = get_state()
    gp = gating_progress(st)
    if gp["complete"] != gp["of"] - 1 or gp.get(day["weekday"]):
        return None
    thr = g.get("soreness_flag_threshold", 4)
    need = g.get("soreness_flag_days", 3)
    recent = _recent_checkins(date, 7)
    n = sum(1 for c in recent if (c.get("soreness") or 0) >= thr)
    if n < need:
        return None
    nxt = (f"Cycle {day['cycle']} Week {day['week'] + 1}" if day["week"] < 4
           else f"Cycle {day['cycle'] + 1} Week 1")
    return {"rule_key": "soreness_repeat_week", "severity": "warning",
            "message": f"Soreness has been {thr}+ on {n} of the last 7 days. "
                       f"Completing today advances you to {nxt}.",
            "suggestion": f"Repeat Week {day['week']} instead of advancing. "
                          f"Same loads, another week.",
            "payload": {"repeat_week": True}}


def resting_hr_elevated(date, day):
    g = load_program()["guardrails"]
    base = g.get("resting_hr_baseline", 55)
    delta = g.get("resting_hr_flag_delta", 5)
    if not day["exercises"]:
        return None
    recent = [c for c in _recent_checkins(date, 14)
              if c.get("resting_hr") is not None][:3]
    if len(recent) < 3 or not all(c["resting_hr"] >= base + delta for c in recent):
        return None
    vs = ", ".join(str(c["resting_hr"]) for c in recent)
    return {"rule_key": "resting_hr_elevated", "severity": "warning",
            "message": f"Resting HR {vs} over the last 3 check-ins - "
                       f"baseline is {base}.",
            "suggestion": "Make today anchor + Zone 2 only. Skip the main work.",
            "payload": {"convert_to_zone2": True}}


def evening_cutoff(date, day, clock=None):
    p = load_program()
    cfg, g = p["config"], p["guardrails"]
    if not day["is_hard_cns_day"] or day["day_complete"]:
        return None
    if date != datetime.date.today().isoformat():
        return None
    bed = cfg.get("bedtime", "22:30")
    bh, bm = (int(x) for x in bed.split(":"))
    hours = g.get("evening_cutoff_hours_before_bed", 3)
    cutoff = bh * 60 + bm - hours * 60
    tnow = clock or datetime.datetime.now().strftime("%H:%M")
    th, tm = (int(x) for x in tnow.split(":"))
    if th * 60 + tm < cutoff:
        return None
    return {"rule_key": "evening_cutoff", "severity": "warning",
            "message": f"It is {tnow}. Inside the {hours}-hour window before "
                       f"your {bed} bedtime, and today is a hard CNS day.",
            "suggestion": "Anchor, Zone 2 or skill work only tonight. "
                          "Leave the main work for tomorrow.",
            "payload": {"anchor_only": True}}


RULES = (knee_landings, pec_pressing, shoulder_ohp_backoff,
         soreness_repeat_week, resting_hr_elevated, evening_cutoff)
_SEV = {"critical": 0, "serious": 1, "warning": 2}


def evaluate(date, day, persist=True):
    """Run all rules. Returns existing resolved rows plus fresh pending ones."""
    existing = {r["rule_key"]: dict(r) for r in query(
        "SELECT * FROM adjustment WHERE scope_date=?", (date,))}
    out = []
    for rule in RULES:
        try:
            w = rule(date, day)
        except Exception:
            w = None
        prior = existing.get(rule.__name__)
        if prior and prior["status"] in ("applied", "ignored"):
            out.append({"id": prior["id"], "rule_key": prior["rule_key"],
                        "severity": "warning", "message": prior["message"],
                        "suggestion": prior["suggestion"],
                        "status": prior["status"], "payload": {}})
            continue
        if not w:
            continue
        if persist:
            execute(
                "INSERT INTO adjustment (scope_date, rule_key, message,"
                " suggestion, status, payload_json, created_at)"
                " VALUES (?,?,?,?,'pending',?,?) "
                "ON CONFLICT (scope_date, rule_key) DO UPDATE SET"
                " message=excluded.message, suggestion=excluded.suggestion,"
                " payload_json=excluded.payload_json",
                (date, w["rule_key"], w["message"], w["suggestion"],
                 json.dumps(w["payload"]), now()))
            row = query_one("SELECT id FROM adjustment WHERE scope_date=? "
                            "AND rule_key=?", (date, w["rule_key"]))
            w["id"] = row["id"] if row else None
        w["status"] = "pending"
        out.append(w)
    out.sort(key=lambda x: _SEV.get(x.get("severity", "warning"), 3))
    return out


def resolve(adj_id, status):
    row = query_one("SELECT * FROM adjustment WHERE id=?", (adj_id,))
    if not row:
        return False
    if status == "applied" and row["payload_json"]:
        try:
            pl = json.loads(row["payload_json"])
        except ValueError:
            pl = {}
        if pl.get("ohp_cycle_offset_delta"):
            execute("UPDATE program_state SET ohp_cycle_offset="
                    "ohp_cycle_offset+?, updated_at=? WHERE id=1",
                    (int(pl["ohp_cycle_offset_delta"]), now()))
    execute("UPDATE adjustment SET status=?, resolved_at=? WHERE id=?",
            (status, now(), adj_id))
    return True
