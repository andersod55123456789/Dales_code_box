import datetime

from flask import Blueprint, redirect, render_template, request, url_for

from trainlog import logbook, reports
from trainlog.engine import (fartlek, ohp_prescription, rope_interval,
                             week_type, working_load, accessory_sets)
from trainlog.program import load_program, day_exercises
from trainlog.routes.api import day_payload, resolve_date, state_payload
from trainlog.config import WEEKDAYS

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return redirect(url_for("pages.day", date="today"))


@bp.get("/day/<date>")
def day(date):
    try:
        date = resolve_date(date)
    except ValueError:
        return redirect(url_for("pages.day", date="today"))
    d = datetime.date.fromisoformat(date)
    return render_template(
        "day.html", day=day_payload(date), state=state_payload(),
        pretty=d.strftime("%a %d %b %Y"),
        prev=(d - datetime.timedelta(days=1)).isoformat(),
        next=(d + datetime.timedelta(days=1)).isoformat(),
        checkin_done=logbook.load_logged_for_day(date)["checkin_done"])


@bp.get("/checkin")
def checkin():
    date = resolve_date(request.args.get("date"))
    from trainlog.db import query_one
    r = query_one("SELECT * FROM checkin WHERE checkin_date=?", (date,))
    p = load_program()
    return render_template(
        "checkin.html", date=date, checkin=dict(r) if r else None,
        baseline_hr=p["guardrails"].get("resting_hr_baseline", 55),
        pretty=datetime.date.fromisoformat(date).strftime("%a %d %b %Y"),
        checkin_done=r is not None)


@bp.get("/progress")
def progress():
    rng = request.args.get("range", "12w")
    from trainlog.charts import build
    return render_template(
        "progress.html", rng=rng, c=build(rng),
        adherence=reports.adherence_stats(rng),
        metrics=reports.test_metrics(),
        checkin_done=True)


@bp.get("/tests")
def tests():
    st = logbook.get_state()
    ms = reports.test_metrics()
    for m in ms:
        if m.get("auto_from_log"):
            m["auto_value"] = reports.auto_test_value(m["key"])
    return render_template("tests.html", metrics=ms, state=state_payload(),
                           today=datetime.date.today().isoformat(),
                           checkin_done=True)


@bp.get("/program")
def program_view():
    p = load_program()
    st = logbook.get_state()
    cycle, week = st["cycle"], st["week"]
    cfg = p["config"]
    wtype = week_type(cycle, week)
    days = []
    for wd in WEEKDAYS:
        raw, note = day_exercises(wd, wtype, cycle)
        rows = []
        for ex in raw:
            prog = ex.get("progression", "none")
            sets = ex.get("sets")
            load = ex.get("load")
            if prog in ("lower", "upper"):
                load = working_load(ex["load"], prog, cycle, week, cfg)
            elif prog == "ramp_ohp":
                o = ohp_prescription(cycle, week, st.get("ohp_cycle_offset", 0), cfg)
                sets, load = o["sets"], o["load"]
            elif ex.get("kind") in ("accessory", "drill"):
                sets = accessory_sets(ex, week, cfg)
            rows.append({"name": ex["name"], "sets": sets,
                         "reps": ex.get("reps"), "load": load,
                         "kind": ex.get("kind")})
        days.append({"weekday": wd, "name": p["days"][wd]["name"],
                     "note": note, "rows": rows})
    from trainlog.sync_check import run_sync_check
    return render_template("program.html", program=p, state=state_payload(),
                           days=days, rope=rope_interval(
                               cycle, week, next(i for i in p["anchor"]
                                                 if i["key"] == "jump_rope")),
                           fart=fartlek(cycle, week, p["fartlek"]),
                           sync=run_sync_check(), checkin_done=True)
