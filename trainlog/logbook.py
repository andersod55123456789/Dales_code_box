import json

from trainlog import engine as E
from trainlog.db import execute, now, query, query_one
from trainlog.prescription import build_day, weekday_of
from trainlog.program import load_program


def get_state():
    r = query_one("SELECT * FROM program_state WHERE id=1")
    return dict(r) if r else {"cycle": 1, "week": 1, "week_repeat": 0,
                              "ohp_cycle_offset": 0, "reassess_banner": None}


def gating_progress(state):
    p = load_program()
    gd = p["config"]["gating_days"]
    rows = query(
        "SELECT DISTINCT weekday FROM day_log WHERE cycle=? AND week=? "
        "AND week_repeat=? AND day_complete=1",
        (state["cycle"], state["week"], state.get("week_repeat", 0)))
    done = {r["weekday"] for r in rows}
    out = {d: (d in done) for d in gd}
    out["complete"] = len(done & set(gd))
    out["of"] = len(gd)
    return out


def get_or_create_day_log(date_str):
    r = query_one("SELECT * FROM day_log WHERE log_date=?", (date_str,))
    if r:
        return dict(r)
    st = get_state()
    wd = weekday_of(date_str)
    execute(
        "INSERT INTO day_log (log_date, weekday, cycle, week, week_repeat,"
        " week_type, day_complete, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (date_str, wd, st["cycle"], st["week"], st.get("week_repeat", 0),
         E.week_type(st["cycle"], st["week"]), now()))
    return dict(query_one("SELECT * FROM day_log WHERE log_date=?", (date_str,)))


def _prescribed(date_str, exercise_id, set_index, is_backoff):
    day = build_day(date_str, get_state())
    for ex in day["exercises"]:
        if ex["id"] == exercise_id:
            for row in ex["set_rows"]:
                if row["set_index"] == set_index and \
                        int(row["is_backoff"]) == int(is_backoff):
                    return ex["name"], row["target_reps"], row["target_load"]
            return ex["name"], ex["target_reps"], ex["target_load"]
    return exercise_id, None, None


def upsert_set(date_str, exercise_id, set_index, is_backoff,
               actual_reps, actual_load, completed):
    d = get_or_create_day_log(date_str)
    name, t_reps, t_load = _prescribed(date_str, exercise_id, set_index, is_backoff)
    execute(
        "INSERT INTO set_log (day_log_id, exercise_id, exercise_name, set_index,"
        " is_backoff, target_reps, actual_reps, target_load, actual_load,"
        " completed, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT (day_log_id, exercise_id, set_index, is_backoff) DO UPDATE SET"
        " actual_reps=excluded.actual_reps, actual_load=excluded.actual_load,"
        " completed=excluded.completed",
        (d["id"], exercise_id, name, set_index, int(bool(is_backoff)),
         t_reps, actual_reps, t_load, actual_load, int(bool(completed)), now()))


def accept_exercise(date_str, exercise_id):
    """One-click accept: log every set at its prescribed target."""
    day = build_day(date_str, get_state(), load_logged_for_day(date_str))
    ex = next((e for e in day["exercises"] if e["id"] == exercise_id), None)
    if not ex:
        return 0
    n = 0
    for row in ex["set_rows"]:
        if row["actual_reps"] is not None:
            continue  # respect an existing manual edit
        upsert_set(date_str, exercise_id, row["set_index"], row["is_backoff"],
                   row["target_reps"], row["target_load"], True)
        n += 1
    return n


def upsert_anchor(date_str, item_key, fields, completed):
    d = get_or_create_day_log(date_str)
    prog_item = next((i for i in load_program()["anchor"]
                      if i["key"] == item_key), {})
    defaults = {f["key"]: f.get("default")
                for f in prog_item.get("fields", []) or []}
    for k, v in (fields or {}).items():
        execute(
            "INSERT INTO anchor_log (day_log_id, item_key, field_key,"
            " target_value, actual_value, completed, created_at)"
            " VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT (day_log_id, item_key, field_key) DO UPDATE SET"
            " actual_value=excluded.actual_value, completed=excluded.completed",
            (d["id"], item_key, k,
             None if defaults.get(k) is None else str(defaults.get(k)),
             None if v is None else str(v), int(bool(completed)), now()))
    execute(
        "INSERT INTO anchor_log (day_log_id, item_key, field_key,"
        " target_value, actual_value, completed, created_at)"
        " VALUES (?,?,'__done__',NULL,NULL,?,?) "
        "ON CONFLICT (day_log_id, item_key, field_key) DO UPDATE SET"
        " completed=excluded.completed",
        (d["id"], item_key, int(bool(completed)), now()))


def accept_all_anchor(date_str):
    n = 0
    logged = load_logged_for_day(date_str)
    for item in load_program()["anchor"]:
        if logged["anchor"].get((item["key"], "__done__")):
            continue
        fields = {f["key"]: f.get("default")
                  for f in item.get("fields", []) or []
                  if f.get("default") is not None}
        upsert_anchor(date_str, item["key"], fields, True)
        n += 1
    return n


def upsert_metric(date_str, exercise_id, field_key, value_num, value_text):
    d = get_or_create_day_log(date_str)
    execute(
        "INSERT INTO metric_log (day_log_id, exercise_id, field_key,"
        " value_num, value_text, created_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT (day_log_id, exercise_id, field_key) DO UPDATE SET"
        " value_num=excluded.value_num, value_text=excluded.value_text",
        (d["id"], exercise_id, field_key, value_num, value_text, now()))


def load_logged_for_day(date_str):
    out = {"sets": {}, "anchor": {}, "metrics": {}, "day_log": None,
           "adjustments": [], "checkin_done": False}
    d = query_one("SELECT * FROM day_log WHERE log_date=?", (date_str,))
    out["checkin_done"] = query_one(
        "SELECT 1 FROM checkin WHERE checkin_date=?", (date_str,)) is not None
    for a in query("SELECT payload_json FROM adjustment "
                   "WHERE scope_date=? AND status='applied'", (date_str,)):
        if a["payload_json"]:
            try:
                out["adjustments"].append(json.loads(a["payload_json"]))
            except ValueError:
                pass
    if not d:
        return out
    out["day_log"] = dict(d)
    for r in query("SELECT * FROM set_log WHERE day_log_id=?", (d["id"],)):
        out["sets"][(r["exercise_id"], r["set_index"], r["is_backoff"])] = dict(r)
    for r in query("SELECT * FROM anchor_log WHERE day_log_id=?", (d["id"],)):
        key = (r["item_key"], r["field_key"])
        out["anchor"][key] = (r["completed"] if r["field_key"] == "__done__"
                              else r["actual_value"])
    for r in query("SELECT * FROM metric_log WHERE day_log_id=?", (d["id"],)):
        out["metrics"][(r["exercise_id"], r["field_key"])] = (
            r["value_text"] if r["value_text"] is not None else r["value_num"])
    return out


def get_day(date_str):
    return build_day(date_str, get_state(), load_logged_for_day(date_str))


def set_day_complete(date_str, complete):
    get_or_create_day_log(date_str)
    execute("UPDATE day_log SET day_complete=?, completed_at=? WHERE log_date=?",
            (int(bool(complete)), now() if complete else None, date_str))
    if complete:
        return advance_check(date_str)
    return {"advanced": False, "week_repeated": False,
            "message": "Day un-completed. The program does not roll backward."}


def advance_check(date_str):
    p = load_program()
    st = get_state()
    wd = weekday_of(date_str)
    gd = p["config"]["gating_days"]
    quiet = {"advanced": False, "week_repeated": False, "message": "Day saved."}
    if wd not in gd:
        return quiet

    rows = query(
        "SELECT DISTINCT weekday FROM day_log WHERE cycle=? AND week=? "
        "AND week_repeat=? AND day_complete=1 AND weekday IN (?,?,?)",
        (st["cycle"], st["week"], st["week_repeat"], *gd))
    if len({r["weekday"] for r in rows}) < len(gd):
        n = len({r["weekday"] for r in rows})
        return {"advanced": False, "week_repeated": False,
                "message": f"Day saved. {n} of {len(gd)} lifting days done."}

    if query_one("SELECT 1 FROM week_completion WHERE cycle=? AND week=? "
                 "AND repeat_index=?",
                 (st["cycle"], st["week"], st["week_repeat"])):
        return quiet

    execute("INSERT OR IGNORE INTO week_completion "
            "(cycle, week, repeat_index, completed_at) VALUES (?,?,?,?)",
            (st["cycle"], st["week"], st["week_repeat"], now()))

    repeat = query_one(
        "SELECT 1 FROM adjustment WHERE scope_date=? "
        "AND rule_key='soreness_repeat_week' AND status='applied'", (date_str,))
    if repeat:
        execute("UPDATE program_state SET week_repeat=week_repeat+1,"
                " updated_at=? WHERE id=1", (now(),))
        return {"advanced": False, "week_repeated": True,
                "message": f"Week held. Repeating Cycle {st['cycle']} "
                           f"Week {st['week']} at the same loads."}

    cycle, week = st["cycle"], st["week"]
    if week < 4:
        week += 1
    else:
        cycle, week = cycle + 1, 1
    banner = None
    if week == 1 and (cycle - 1) in (p["meta"].get("reassess_after_cycles") or []):
        banner = f"End of Cycle {cycle - 1} - reassess program structure"
    execute("UPDATE program_state SET cycle=?, week=?, week_repeat=0,"
            " reassess_banner=COALESCE(?, reassess_banner), updated_at=?"
            " WHERE id=1", (cycle, week, banner, now()))
    return {"advanced": True, "week_repeated": False,
            "message": f"Week complete. Advanced to Cycle {cycle} Week {week}."}
