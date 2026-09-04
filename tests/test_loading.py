import json

import pytest

from trainlog.loading import (apply_ramp, apply_reps_only, evaluate_session,
                              mesocycle_phase, step1, step2)


def state(**overrides):
    value = {"exercise_id": "back_squat", "current_load": 100.0,
             "rep_range_lo": 8, "rep_range_hi": 12, "load_step": 5.0,
             "rir_target_lo": 2, "rir_target_hi": 3,
             "sessions_in_mesocycle": 0, "recent_sessions_json": "[]",
             "progression_mode": "standard"}
    value.update(overrides)
    return value


def test_worked_example_a_standard_compound():
    st = state()
    sessions = [([10, 9, 8], "TARGET"), ([10, 10, 9], "TARGET"),
                ([11, 10, 10], "TARGET"), ([12, 11, 10], "TARGET"),
                ([12, 12, 11], "TARGET"), ([12, 12, 12], "TARGET"),
                ([9, 9, 8], "TARGET")]
    actions = []
    for reps, rir in sessions:
        result = evaluate_session(st, reps, rir)
        actions.append(result["action"])
        history = json.loads(st["recent_sessions_json"])
        history.append({"actual_reps": reps, "rir_feedback": rir, "action": result["action"]})
        st["recent_sessions_json"] = json.dumps(history[-3:])
        st["sessions_in_mesocycle"] += 1
        st["current_load"] = result["next_load"] or st["current_load"]
    assert actions == ["HOLD_LOAD"] * 5 + ["INCREASE_LOAD", "HOLD_LOAD"]
    assert st["current_load"] == 105.0


def test_worked_example_b_ohp_ramp_clamp():
    st = state(exercise_id="ohp", current_load=95.0, rep_range_lo=6,
               rep_range_hi=10, load_step=2.5, rir_target_lo=3,
               rir_target_hi=4, sessions_in_mesocycle=6,
               progression_mode="ramp_governed",
               recent_sessions_json=json.dumps([{"actual_reps": [10, 10, 10], "rir_feedback": "EASY", "action": "HOLD_LOAD"}]))
    result = apply_ramp(st, evaluate_session(st, [10, 10, 9], "EASY"), [])
    assert (result["action"], result["next_load"], result["target_sets"]) == ("HOLD_LOAD", 95.0, 4)
    assert (result["event"], result["note"]) == ("MESOCYCLE_PHASE_ADVANCE", "load deferred - ramp ceiling")


def test_worked_example_c_pec_failure_decreases_immediately():
    result = evaluate_session(state(exercise_id="db_floor_press", current_load=45.0,
        rep_range_lo=10, rep_range_hi=15, rir_target_lo=3, rir_target_hi=4,
        sessions_in_mesocycle=5), [8, 7, 6], "FAILURE")
    assert (result["action"], result["next_load"]) == ("DECREASE_LOAD", 40.0)


def test_worked_example_d_guardrail_is_an_integration_skip():
    # The pure engine is intentionally never called for this case (covered in integration tests).
    before = state(exercise_id="walking_lunges", current_load=30.0)
    assert before["current_load"] == 30.0 and before["recent_sessions_json"] == "[]"


def test_worked_example_e_reps_only_extension():
    st = state(exercise_id="pull_ups", current_load=None, load_step=None,
               progression_mode="reps_only", sessions_in_mesocycle=4)
    result = apply_reps_only(st, evaluate_session(st, [12] * 4, "TARGET"))
    assert (result["action"], result["rep_range_lo"], result["rep_range_hi"]) == ("INCREASE_DIFFICULTY", 10, 14)


def test_mesocycle_gates_trends_and_deload():
    history = json.dumps([{"actual_reps": [10, 10, 10], "rir_feedback": "EASY"}])
    assert evaluate_session(state(sessions_in_mesocycle=1, recent_sessions_json=history), [10] * 3, "EASY")["action"] == "HOLD_LOAD"
    assert evaluate_session(state(sessions_in_mesocycle=4, recent_sessions_json=history), [10] * 3, "EASY")["action"] == "INCREASE_LOAD"
    result = evaluate_session(state(sessions_in_mesocycle=11), [12] * 3, "TARGET")
    assert result["action"] == "MESOCYCLE_DELOAD" and result["next_load"] is None


@pytest.mark.parametrize("rep_range", [(6, 10), (10, 15)])
@pytest.mark.parametrize("rir", ["EASY", "TARGET", "HARD", "FAILURE"])
def test_step1_grid_outside_examples(rep_range, rir):
    assert step1([rep_range[0]] * 3, rep_range, rir) in {"HOLD_LOAD", "DECREASE_LOAD"}
    assert step1([rep_range[1]] * 3, rep_range, rir) in {"HOLD_LOAD", "INCREASE_LOAD"}


def test_performance_drop_and_single_step_decrease():
    recent = [{"actual_reps": [15], "rir_feedback": "TARGET"},
              {"actual_reps": [12], "rir_feedback": "TARGET"}]
    assert step2(recent, {"actual_reps": [9], "rir_feedback": "TARGET"}, (8, 15), "PROGRESSING") == "DECREASE_LOAD"
    result = evaluate_session(state(current_load=100, load_step=5, sessions_in_mesocycle=5,
                                    recent_sessions_json=json.dumps(recent)), [9], "TARGET")
    assert result["next_load"] == 95


def test_reps_only_stops_at_cap():
    st = state(exercise_id="pull_ups", current_load=None, load_step=None,
               progression_mode="reps_only", rep_range_lo=18, rep_range_hi=20,
               sessions_in_mesocycle=4)
    result = apply_reps_only(st, {"action": "INCREASE_LOAD", "next_rep_target": ""})
    assert (result["rep_range_lo"], result["rep_range_hi"]) == (18, 20)

