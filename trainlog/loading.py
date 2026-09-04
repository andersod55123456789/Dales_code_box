"""Pure Phase 2 loading rules (no Flask or database access)."""
import copy
import json

RIR_MAP = {"EASY": 4.0, "TARGET": 2.5, "HARD": 1.0, "FAILURE": 0.0}

def mesocycle_phase(counter):
    counter %= 12
    if counter <= 2: return "BASELINE"
    if counter <= 6: return "PROGRESSING"
    if counter <= 9: return "CONTINUING"
    if counter == 10: return "HARDEST"
    return "MESOCYCLE_DELOAD"

def step1(actual_reps, rep_range, rir_feedback, pec_affected=False):
    lo, hi = rep_range
    band = ("EASY", "TARGET") if pec_affected else ("TARGET", "HARD")
    if actual_reps and all(rep >= hi for rep in actual_reps) and rir_feedback in band:
        return "INCREASE_LOAD"
    if pec_affected and rir_feedback == "FAILURE":
        return "DECREASE_LOAD"
    if any(rep < lo for rep in actual_reps) and rir_feedback == "FAILURE":
        return "DECREASE_LOAD"
    return "HOLD_LOAD"

def step2(recent_sessions, session, rep_range, phase, pec_affected=False):
    if phase == "BASELINE": return None
    history = list(recent_sessions) + [session]
    last2 = history[-2:]
    if pec_affected and session["rir_feedback"] == "FAILURE": return "DECREASE_LOAD"
    if len(last2) == 2 and pec_affected and all(s["rir_feedback"] == "HARD" for s in last2): return "DECREASE_LOAD"
    if len(last2) == 2 and all(s["rir_feedback"] == "FAILURE" for s in last2): return "DECREASE_LOAD"
    midpoint = sum(rep_range) / 2
    if len(last2) == 2 and all(s["rir_feedback"] == "EASY" for s in last2) and all(min(s["actual_reps"]) >= midpoint for s in last2):
        return "INCREASE_LOAD"
    last3 = history[-3:]
    if len(last3) == 3:
        tops = [max(s["actual_reps"]) for s in last3]
        if tops[2] < tops[1] - 2 and tops[1] < tops[0] - 2: return "DECREASE_LOAD"
    return None

def evaluate_session(state, actual_reps, rir_feedback):
    counter = int(state.get("sessions_in_mesocycle", 0)) % 12
    phase = mesocycle_phase(counter)
    base = {"exercise_id": state["exercise_id"], "mesocycle_phase": phase, "sessions_in_mesocycle": counter}
    if phase == "MESOCYCLE_DELOAD":
        return {**base, "action": "MESOCYCLE_DELOAD", "reason": "Mesocycle deload session.",
                "next_load": None, "next_rep_target": "use the programmed deload prescription"}
    recent = json.loads(state.get("recent_sessions_json") or "[]")
    rep_range = (state["rep_range_lo"], state["rep_range_hi"])
    pec = (state.get("rir_target_lo"), state.get("rir_target_hi")) == (3, 4)
    session = {"actual_reps": list(actual_reps), "rir_feedback": rir_feedback}
    action = step1(actual_reps, rep_range, rir_feedback, pec)
    if action == "HOLD_LOAD": action = step2(recent, session, rep_range, phase, pec) or action
    load, load_step = state.get("current_load"), state.get("load_step")
    next_load = load
    if action == "INCREASE_LOAD" and load is not None and load_step is not None:
        next_load, reason = load + load_step, f"All {len(actual_reps)} sets reached {rep_range[1]} reps at {rir_feedback.lower()} effort."
        target = f"expect a drop toward {rep_range[0]}-{rep_range[0] + 1} reps at the new weight"
    elif action == "DECREASE_LOAD" and load is not None and load_step is not None:
        next_load, reason = max(0, load - load_step), "Failure or a sustained performance drop called for one load-step decrease."
        target = f"rebuild within {rep_range[0]}-{rep_range[1]} reps"
    else:
        reason, target = "Hold the current load and continue progressing reps.", f"continue toward {rep_range[1]} reps on every set"
    return {**base, "action": action, "reason": reason, "next_load": next_load, "next_rep_target": target}

def apply_ramp(state, recommendation, checkin_history):
    out = copy.deepcopy(recommendation)
    if state.get("progression_mode") != "ramp_governed": return out
    counter = int(state.get("sessions_in_mesocycle", 0)) % 12
    out["target_sets"] = 3 if counter <= 3 else (4 if counter <= 10 else 5)
    ceiling = float(state.get("ramp_load_ceiling", state.get("start_load", 95.0)))
    ceiling += int(state.get("completed_mesocycles", 0)) * float(state.get("load_step") or 0)
    if out["action"] == "INCREASE_LOAD" and (out.get("next_load") or 0) > ceiling:
        out.update(action="HOLD_LOAD", next_load=state.get("current_load"), event="MESOCYCLE_PHASE_ADVANCE",
                   note="load deferred - ramp ceiling", reason="Load increase deferred by the shoulder ramp ceiling.")
    return out

def apply_reps_only(state, recommendation):
    out = copy.deepcopy(recommendation)
    if state.get("progression_mode") != "reps_only": return out
    lo, hi = int(state["rep_range_lo"]), int(state["rep_range_hi"])
    configured_range = state.get("rep_range") or (lo, hi)
    cap = int(state.get("rep_range_ceiling") or (20 if state["exercise_id"] == "pull_ups" else 30))
    if out["action"] == "INCREASE_LOAD":
        out["action"] = "INCREASE_DIFFICULTY"
        if state.get("vest_progression_enabled") and state.get("added_weight_lb", 0) + 5 <= state.get("vest_max_lb", 0):
            out["added_weight_lb"] = state.get("added_weight_lb", 0) + 5
        else:
            out["rep_range_hi"] = min(cap, hi + 2)
            out["rep_range_lo"] = min(out["rep_range_hi"] - (hi - lo), lo + 2)
            if out["rep_range_hi"] == cap:
                out["next_rep_target"] = "swap to a heavier band" if state["exercise_id"] == "band_pull_aparts" else "extend further or consider added resistance"
    elif out["action"] == "DECREASE_LOAD":
        out["action"] = "DECREASE_DIFFICULTY"
        out["rep_range_lo"] = max(int(state.get("seed_rep_range_lo", configured_range[0])), lo - 2)
        out["rep_range_hi"] = max(int(state.get("seed_rep_range_hi", configured_range[1])), hi - 2)
    return out
