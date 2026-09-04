import csv
import datetime
import io
import json
import os
import shutil
import sqlite3

from flask import Blueprint, jsonify, request, Response

from trainlog import config, guardrails, logbook, reports
from trainlog.db import execute, get_db, now, query, query_one
from trainlog.engine import is_deload, program_week, week_type
from trainlog.program import load_program

bp = Blueprint("api", __name__, url_prefix="/api")


def resolve_date(d):
    if not d or d == "today":
        return datetime.date.today().isoformat()
    datetime.date.fromisoformat(d)  # raises on garbage
    return d


def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def state_payload():
    st = logbook.get_state()
    c, w = st["cycle"], st["week"]
    return {"ok": True, "cycle": c, "week": w,
            "week_repeat": st.get("week_repeat", 0),
            "week_type": week_type(c, w), "program_week": program_week(c, w),
            "is_deload": is_deload(w),
            "ohp_cycle_offset": st.get("ohp_cycle_offset", 0),
            "started_on": st.get("started_on"),
            "reassess_banner": st.get("reassess_banner"),
            "gating_progress": logbook.gating_progress(st)}


@bp.get("/state")
def get_state():
    return jsonify(state_payload())


@bp.post("/state/override")
def override_state():
    b = request.get_json(silent=True) or {}
    try:
        c, w = int(b["cycle"]), int(b["week"])
    except (KeyError, TypeError, ValueError):
        return err("cycle and week required")
    if c < 1 or not 1 <= w <= 4:
        return err("cycle >= 1 and week 1-4")
    execute("UPDATE program_state SET cycle=?, week=?, week_repeat=0,"
            " updated_at=? WHERE id=1", (c, w, now()))
    return jsonify(state_payload())


@bp.post("/state/dismiss_banner")
def dismiss_banner():
    execute("UPDATE program_state SET reassess_banner=NULL WHERE id=1")
    return jsonify({"ok": True})


def day_payload(date):
    day = logbook.get_day(date)
    if date == datetime.date.today().isoformat():
        day["warnings"] = guardrails.evaluate(date, day, persist=True)
    else:
        day["warnings"] = [dict(r) for r in query(
            "SELECT id, rule_key, message, suggestion, status"
            " FROM adjustment WHERE scope_date=?", (date,))]
    return day


@bp.get("/day/<date>")
def get_day(date):
    try:
        date = resolve_date(date)
    except ValueError:
        return err("bad date", 404)
    d = day_payload(date)
    d["ok"] = True
    return jsonify(d)


@bp.post("/set")
def post_set():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
        eid = b["exercise_id"]
        idx = int(b["set_index"])
    except (KeyError, TypeError, ValueError):
        return err("date, exercise_id, set_index required")
    logbook.upsert_set(date, eid, idx, bool(b.get("is_backoff")),
                       b.get("actual_reps"), b.get("actual_load"),
                       bool(b.get("completed")))
    day = logbook.get_day(date)
    ex = next((e for e in day["exercises"] if e["id"] == eid), None)
    return jsonify({
        "ok": True,
        "rest_seconds": (ex or {}).get("rest_seconds", 90),
        "exercise_complete": bool(ex) and all(
            r["completed"] for r in ex["set_rows"]) and bool(ex["set_rows"]),
        "day_landings": day["landings"]["count"]})


@bp.post("/exercise/done")
def exercise_done():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
        eid = b["exercise_id"]
    except (KeyError, TypeError, ValueError):
        return err("date and exercise_id required")
    return jsonify({"ok": True, "sets_written": logbook.accept_exercise(date, eid)})


@bp.post("/anchor")
def post_anchor():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
        key = b["item_key"]
    except (KeyError, TypeError, ValueError):
        return err("date and item_key required")
    logbook.upsert_anchor(date, key, b.get("fields") or {},
                          bool(b.get("completed")))
    return jsonify({"ok": True})


@bp.post("/anchor/done_all")
def anchor_done_all():
    try:
        date = resolve_date((request.get_json(silent=True) or {}).get("date"))
    except ValueError:
        return err("bad date")
    return jsonify({"ok": True, "items_written": logbook.accept_all_anchor(date)})


@bp.post("/metric")
def post_metric():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
        eid, fk = b["exercise_id"], b["field_key"]
    except (KeyError, TypeError, ValueError):
        return err("date, exercise_id, field_key required")
    logbook.upsert_metric(date, eid, fk, b.get("value_num"), b.get("value_text"))
    return jsonify({"ok": True})


@bp.post("/day/complete")
def day_complete():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
    except ValueError:
        return err("bad date")
    res = logbook.set_day_complete(date, bool(b.get("complete", True)))
    res.update({"ok": True, "state": state_payload()})
    return jsonify(res)


@bp.post("/day/notes")
def day_notes():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
    except ValueError:
        return err("bad date")
    logbook.get_or_create_day_log(date)
    execute("UPDATE day_log SET notes=? WHERE log_date=?",
            (b.get("notes") or "", date))
    return jsonify({"ok": True})


@bp.get("/checkin/<date>")
def get_checkin(date):
    try:
        date = resolve_date(date)
    except ValueError:
        return err("bad date", 404)
    r = query_one("SELECT * FROM checkin WHERE checkin_date=?", (date,))
    return jsonify({"ok": True, "checkin": dict(r) if r else None})


_STATUS = ("ok", "niggle", "pain")


@bp.post("/checkin")
def post_checkin():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
    except ValueError:
        return err("bad date")
    for k in ("sleep_quality", "energy", "soreness", "mood"):
        v = b.get(k)
        if v is not None and not (isinstance(v, int) and 1 <= v <= 5):
            return err(f"{k} must be an integer 1-5")
    for k in ("pec_status", "knee_status", "shoulder_status"):
        if b.get(k) is not None and b[k] not in _STATUS:
            return err(f"{k} must be one of {_STATUS}")
    execute(
        "INSERT INTO checkin (checkin_date, sleep_hours, sleep_quality, energy,"
        " soreness, mood, resting_hr, pec_status, knee_status, shoulder_status,"
        " notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT (checkin_date) DO UPDATE SET"
        " sleep_hours=excluded.sleep_hours,"
        " sleep_quality=excluded.sleep_quality, energy=excluded.energy,"
        " soreness=excluded.soreness, mood=excluded.mood,"
        " resting_hr=excluded.resting_hr, pec_status=excluded.pec_status,"
        " knee_status=excluded.knee_status,"
        " shoulder_status=excluded.shoulder_status, notes=excluded.notes,"
        " updated_at=excluded.updated_at",
        (date, b.get("sleep_hours"), b.get("sleep_quality"), b.get("energy"),
         b.get("soreness"), b.get("mood"), b.get("resting_hr"),
         b.get("pec_status"), b.get("knee_status"), b.get("shoulder_status"),
         b.get("notes"), now(), now()))
    warnings = []
    if date == datetime.date.today().isoformat():
        warnings = guardrails.evaluate(date, logbook.get_day(date), persist=True)
    return jsonify({"ok": True, "warnings": warnings})


@bp.get("/warnings/<date>")
def get_warnings(date):
    try:
        date = resolve_date(date)
    except ValueError:
        return err("bad date", 404)
    return jsonify({"ok": True,
                    "warnings": guardrails.evaluate(date, logbook.get_day(date),
                                                    persist=False)})


@bp.post("/adjustment/<int:adj_id>/apply")
def apply_adjustment(adj_id):
    if not guardrails.resolve(adj_id, "applied"):
        return err("no such adjustment", 404)
    row = query_one("SELECT scope_date FROM adjustment WHERE id=?", (adj_id,))
    return jsonify({"ok": True, "day": day_payload(row["scope_date"])})


@bp.post("/adjustment/<int:adj_id>/ignore")
def ignore_adjustment(adj_id):
    if not guardrails.resolve(adj_id, "ignored"):
        return err("no such adjustment", 404)
    return jsonify({"ok": True})


def _parse_test(m, raw):
    if raw is None or raw == "":
        return None, None
    if m.get("is_time"):
        s = str(raw)
        if ":" in s:
            mm, ss = s.split(":")[:2]
            return int(mm) * 60 + float(ss), s
        return float(s), None
    return float(raw), None


@bp.get("/tests")
def get_tests():
    return jsonify({"ok": True, "metrics": reports.test_metrics()})


@bp.post("/tests")
def post_tests():
    b = request.get_json(silent=True) or {}
    try:
        date = resolve_date(b.get("date"))
    except ValueError:
        return err("bad date")
    st = logbook.get_state()
    battery = {m["key"]: m for m in load_program()["test_battery"]}
    n = 0
    for key, raw in (b.get("values") or {}).items():
        m = battery.get(key)
        if not m:
            continue
        try:
            vnum, vtext = _parse_test(m, raw)
        except ValueError:
            return err(f"bad value for {key}: {raw!r}")
        if vnum is None:
            continue
        execute("INSERT INTO test_battery (test_date, cycle, week, metric_key,"
                " value_num, value_text, created_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT (test_date, metric_key) DO UPDATE SET"
                " value_num=excluded.value_num, value_text=excluded.value_text",
                (date, st["cycle"], st["week"], key, vnum, vtext, now()))
        n += 1
    return jsonify({"ok": True, "saved": n})


@bp.get("/progress/strength")
def progress_strength():
    r = request.args.get("range", "12w")
    return jsonify({"ok": True, "series": reports.strength_series(r),
                    "weekly_tonnage": reports.weekly_tonnage(r)})


@bp.get("/progress/wellness")
def progress_wellness():
    r = request.args.get("range", "12w")
    return jsonify({"ok": True, "days": reports.wellness_series(r),
                    "weekly_tonnage": reports.weekly_tonnage(r)})


@bp.get("/progress/adherence")
def progress_adherence():
    return jsonify({"ok": True,
                    **reports.adherence_stats(request.args.get("range", "12w"))})


@bp.post("/backup")
def backup():
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    dest = os.path.join(config.BACKUP_DIR, f"training-{stamp}.db")
    tgt = sqlite3.connect(dest)
    with tgt:
        get_db().backup(tgt)
    tgt.close()
    return jsonify({"ok": True, "path": os.path.relpath(dest, config.APP_DIR)})


@bp.get("/export/sets.csv")
def export_sets():
    rows = query(
        "SELECT d.log_date, d.weekday, d.cycle, d.week, s.exercise_id,"
        " s.exercise_name, s.set_index, s.is_backoff, s.target_reps,"
        " s.actual_reps, s.target_load, s.actual_load, s.completed"
        " FROM set_log s JOIN day_log d ON d.id=s.day_log_id"
        " ORDER BY d.log_date, s.exercise_id, s.is_backoff, s.set_index")
    buf = io.StringIO()
    cols = ["log_date", "weekday", "cycle", "week", "exercise_id",
            "exercise_name", "set_index", "is_backoff", "target_reps",
            "actual_reps", "target_load", "actual_load", "completed"]
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=sets.csv"})


@bp.get("/sync_check")
def sync_check():
    from trainlog.sync_check import run_sync_check
    return jsonify({"ok": True, **run_sync_check()})
