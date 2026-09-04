"""Database adapter for the pure loading rules."""
import json

from trainlog import engine
from trainlog.db import execute, now, query, query_one
from trainlog.loading import apply_ramp, apply_reps_only, evaluate_session, mesocycle_phase
from trainlog.loading_config import load_phase2_config
from trainlog.logbook import get_state


def process_exercise_session(date_str, exercise_id):
    row = query_one("SELECT * FROM exercise_state WHERE exercise_id=?", (exercise_id,))
    if not row or row["progression_mode"] == "excluded":
        return {"skipped": "excluded"}
    state = dict(row)
    if query_one("SELECT 1 FROM adjustment WHERE scope_date=? AND status='applied'", (date_str,)):
        return {"skipped": "guardrail"}
    if engine.is_deload(get_state()["week"]):
        return {"skipped": "deload"}
    config_item = load_phase2_config()["exercises"][exercise_id]
    if config_item["muscle_group"] in ("quads_glutes", "hamstrings_glutes") and query_one(
            "SELECT 1 FROM checkin WHERE checkin_date=? AND knee_status IN ('niggle','pain')", (date_str,)):
        return {"skipped": "guardrail"}
    day = query_one("SELECT id FROM day_log WHERE log_date=?", (date_str,))
    if not day:
        return {"skipped": "no_sets"}
    feedback = query_one("SELECT rir_feedback FROM exercise_feedback WHERE day_log_id=? AND exercise_id=?",
                         (day["id"], exercise_id))
    if not feedback:
        return {"skipped": "no_feedback", "action": "HOLD_LOAD"}
    reps = [r["actual_reps"] for r in query(
        "SELECT actual_reps FROM set_log WHERE day_log_id=? AND exercise_id=? AND is_backoff=0 AND completed=1 AND actual_reps IS NOT NULL ORDER BY set_index",
        (day["id"], exercise_id))]
    if not reps:
        return {"skipped": "no_sets"}
    recommendation = evaluate_session(state, reps, feedback["rir_feedback"])
    if state["progression_mode"] == "ramp_governed":
        shoulder = [dict(r) for r in query("SELECT shoulder_status FROM checkin WHERE checkin_date<=? ORDER BY checkin_date DESC LIMIT 12", (date_str,))]
        recommendation = apply_ramp({**state, **config_item}, recommendation, shoulder)
    elif state["progression_mode"] == "reps_only":
        recommendation = apply_reps_only({**state, **config_item}, recommendation)
    old_phase = mesocycle_phase(state["sessions_in_mesocycle"])
    next_counter = (state["sessions_in_mesocycle"] + 1) % 12
    recent = json.loads(state.get("recent_sessions_json") or "[]")
    if recommendation["action"] != "MESOCYCLE_DELOAD":
        recent.append({"actual_reps": reps, "rir_feedback": feedback["rir_feedback"], "action": recommendation["action"]})
        recent = recent[-3:]
    next_load = recommendation.get("next_load")
    if recommendation["action"] == "MESOCYCLE_DELOAD": next_load = state["current_load"]
    execute("UPDATE exercise_state SET current_load=?,added_weight_lb=?,rep_range_lo=?,rep_range_hi=?,target_sets=?,last_action=?,sessions_in_mesocycle=?,recent_sessions_json=?,last_recommendation_json=?,updated_at=? WHERE exercise_id=?",
            (next_load, recommendation.get("added_weight_lb", state["added_weight_lb"]),
             recommendation.get("rep_range_lo", state["rep_range_lo"]), recommendation.get("rep_range_hi", state["rep_range_hi"]),
             recommendation.get("target_sets", state["target_sets"]),
             recommendation["action"] if recommendation["action"] in ("INCREASE_LOAD","DECREASE_LOAD","HOLD_LOAD") else None,
             next_counter, json.dumps(recent), json.dumps(recommendation), now(), exercise_id))
    event = recommendation.get("event")
    if not event and recommendation["action"] in ("INCREASE_LOAD", "DECREASE_LOAD", "MESOCYCLE_DELOAD"):
        event = recommendation["action"]
    if event:
        execute("INSERT INTO progression_event (day_log_id,exercise_id,event_type,detail_json,created_at) VALUES (?,?,?,?,?)",
                (day["id"], exercise_id, event, json.dumps(recommendation), now()))
        # Phase B Task 13: +25 XP on a difficulty increase (source=progression_event,
        # so no double-counting possible). INCREASE_DIFFICULTY is the reps-only increase.
        if recommendation["action"] in ("INCREASE_LOAD", "INCREASE_DIFFICULTY"):
            from trainlog import xp as _xp
            _xp.award("progression_event", _xp.XP_PROGRESSION_EVENT,
                      exercise_id=exercise_id, day_log_id=day["id"],
                      detail=f"{recommendation['action']} {exercise_id}")
    new_phase = mesocycle_phase(next_counter)
    if old_phase != new_phase and not event:
        execute("INSERT INTO progression_event (day_log_id,exercise_id,event_type,detail_json,created_at) VALUES (?,?,?,?,?)",
                (day["id"], exercise_id, "MESOCYCLE_PHASE_ADVANCE", json.dumps({"from": old_phase, "to": new_phase}), now()))
    return recommendation
