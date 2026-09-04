import datetime

from trainlog import engine as E
from trainlog.config import WEEKDAYS
from trainlog.program import load_program, day_exercises


def weekday_of(date_str):
    y, m, d = (int(x) for x in date_str.split("-"))
    return WEEKDAYS[datetime.date(y, m, d).weekday()]


def _reps_display(ex, target_reps):
    r = ex.get("reps")
    if isinstance(r, str):
        return r
    if target_reps is None:
        return "-"
    return f"{target_reps}/side" if ex.get("per_side") else str(target_reps)


def _extra_fields(ex, logged_metrics):
    out = []
    for f in ex.get("extra_fields", []) or []:
        got = logged_metrics.get((ex["id"], f["key"]))
        out.append({
            "key": f["key"], "label": f.get("label", f["key"]),
            "type": f.get("type", "number"), "unit": f.get("unit"),
            "options": f.get("options"), "target": f.get("default"),
            "actual": got,
        })
    return out


def build_day(date_str, state, logged=None):
    p = load_program()
    cfg, pu = p["config"], p["pullups"]
    cycle, week = state["cycle"], state["week"]
    offset = state.get("ohp_cycle_offset", 0)
    wtype = E.week_type(cycle, week)
    weekday = weekday_of(date_str)
    day_meta = p["days"][weekday]
    logged = logged or {}
    lsets = logged.get("sets", {})
    lanchor = logged.get("anchor", {})
    lmetrics = logged.get("metrics", {})
    adjustments = logged.get("adjustments", [])

    # ---- collapse applied adjustment payloads --------------------------
    scale_sets, scale_load, skip = {}, {}, set()
    anchor_only = False
    day_note_extra = None
    for adj in adjustments:
        pl = adj or {}
        scale_sets.update(pl.get("scale_sets", {}) or {})
        scale_load.update(pl.get("scale_load", {}) or {})
        skip.update(pl.get("skip", []) or [])
        if pl.get("anchor_only"):
            anchor_only = True
        if pl.get("convert_to_zone2"):
            anchor_only = True
            day_note_extra = "Anchor + Zone 2 only - elevated resting HR"

    # ---- anchor --------------------------------------------------------
    anchor = []
    for item in sorted(p["anchor"], key=lambda i: i.get("order", 99)):
        fields = []
        for f in item.get("fields", []) or []:
            fields.append({
                "key": f["key"], "label": f.get("label", f["key"]),
                "type": f.get("type", "number"), "unit": f.get("unit"),
                "target": f.get("default"),
                "actual": lanchor.get((item["key"], f["key"])),
            })
        entry = {
            "key": item["key"], "name": item["name"], "note": item.get("note"),
            "fields": fields,
            "completed": bool(lanchor.get((item["key"], "__done__"))),
        }
        if item["key"] == "jump_rope":
            entry["interval"] = E.rope_interval(cycle, week, item)
            entry["rounds"] = next(
                (f.get("default") for f in item.get("fields", [])
                 if f["key"] == "rounds"), 5)
        if item["key"] == "core":
            ar = item.get("anti_rotation") or {}
            if weekday in (ar.get("days") or []):
                entry["anti_rotation"] = ar.get("items", [])
        anchor.append(entry)

    # ---- exercises -----------------------------------------------------
    raw, day_note = day_exercises(weekday, wtype, cycle)
    exercises, landing_pairs = [], []

    for ex in raw:
        eid, prog = ex["id"], ex.get("progression", "none")
        sets = ex.get("sets") or 0
        target_reps = ex["reps"] if isinstance(ex.get("reps"), int) else None
        load = ex.get("load")
        pull_sets = None

        if prog in ("lower", "upper"):
            load = E.working_load(ex["load"], prog, cycle, week, cfg)
        elif prog == "ramp_ohp":
            o = E.ohp_prescription(cycle, week, offset, cfg)
            sets, target_reps, load = o["sets"], o["reps"], o["load"]
        elif prog == "pullup_total":
            total = E.pullup_total(cycle, week, pu)
            if total is None:
                sets, target_reps = 1, None
            else:
                pull_sets = E.distribute(total, pu["distribution_ratios"])
                sets = len(pull_sets)
        elif ex.get("kind") == "pullup":
            target_reps = ex.get("submax_target", target_reps)
            sets = ex.get("sets") or 0
        elif ex.get("kind") in ("accessory", "drill"):
            sets = E.accessory_sets(ex, week, cfg)

        if eid in scale_sets:
            sets = max(1, E.round_half_up(sets * scale_sets[eid]))
        if load is not None and eid in scale_load:
            load = E.round_to(load * scale_load[eid], cfg["round_to"])

        skipped = eid in skip or (anchor_only and ex.get("kind") != "cardio")
        if skipped:
            sets = 0

        rows = []
        for i in range(1, sets + 1):
            tr = pull_sets[i - 1] if pull_sets else target_reps
            got = lsets.get((eid, i, 0), {})
            rows.append({
                "set_index": i, "is_backoff": False, "target_reps": tr,
                "target_load": load, "reps_display": _reps_display(ex, tr),
                "actual_reps": got.get("actual_reps"),
                "actual_load": got.get("actual_load"),
                "completed": bool(got.get("completed")),
            })
        if E.has_backoff(ex, week) and not skipped and load is not None:
            got = lsets.get((eid, 1, 1), {})
            rows.append({
                "set_index": 1, "is_backoff": True, "target_reps": None,
                "target_load": E.backoff_load(load, cfg),
                "reps_display": "AMRAP-2",
                "actual_reps": got.get("actual_reps"),
                "actual_load": got.get("actual_load"),
                "completed": bool(got.get("completed")),
            })

        entry = {
            "id": eid, "name": ex["name"], "kind": ex.get("kind", "accessory"),
            "sets": sets, "target_reps": target_reps, "target_load": load,
            "reps_display": _reps_display(ex, target_reps),
            "rest_seconds": ex.get("rest_seconds", 90),
            "per_side": bool(ex.get("per_side")),
            "optional": bool(ex.get("optional")),
            "protected": bool(ex.get("protected")),
            "skipped": skipped, "note": ex.get("note"),
            "unit_label": ex.get("unit_label"),
            "landings_per_rep": ex.get("landings_per_rep", 0),
            "minutes": ex.get("minutes"),
            "set_rows": rows,
            "extra_fields": _extra_fields(ex, lmetrics),
        }
        exercises.append(entry)
        if not skipped:
            landing_pairs.append((ex, sets))

    count = E.landing_count(landing_pairs)
    cap = p["guardrails"]["max_high_force_landings"]
    dlog = logged.get("day_log") or {}

    return {
        "date": date_str, "weekday": weekday,
        "day_name": day_meta["name"], "focus": day_meta.get("focus"),
        "cycle": cycle, "week": week,
        "week_repeat": state.get("week_repeat", 0),
        "week_type": wtype, "program_week": E.program_week(cycle, week),
        "is_deload": E.is_deload(week),
        "is_gating_day": weekday in cfg["gating_days"],
        "is_hard_cns_day": E.is_hard_cns_day(weekday, wtype, p),
        "day_complete": bool(dlog.get("day_complete")),
        "notes": dlog.get("notes") or "",
        "note": day_note_extra or day_note,
        "anchor": anchor, "exercises": exercises,
        "landings": {"count": count, "cap": cap, "over": count > cap},
        "fartlek": E.fartlek(cycle, week, p["fartlek"]),
        "warnings": [], "checkin_done": logged.get("checkin_done", False),
        "show_test_battery": week == 4,
        "reassess_banner": state.get("reassess_banner"),
    }
