from pathlib import Path
import yaml

_phase2_config = None
_ALLOWED_MODES = {"standard", "reps_only", "ramp_governed", "excluded"}

def load_phase2_config():
    global _phase2_config
    if _phase2_config is not None:
        return _phase2_config
    path = Path(__file__).resolve().parent.parent / "phase2_exercise_config.yaml"
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    exercises = data.get("exercises") or {}
    if len(exercises) != 20:
        raise ValueError(f"Expected 20 exercises, got {len(exercises)}")
    for exercise_id, item in exercises.items():
        missing = {"category", "muscle_group", "sets", "progression_mode"} - item.keys()
        if missing:
            raise ValueError(f"Exercise {exercise_id} missing {', '.join(sorted(missing))}")
        if item["progression_mode"] not in _ALLOWED_MODES:
            raise ValueError(f"Exercise {exercise_id} has invalid progression_mode")
        if item["progression_mode"] != "excluded" and not item.get("rep_range"):
            raise ValueError(f"Exercise {exercise_id} missing rep_range")
    ceilings = data.get("muscle_group_ceilings") or {}
    if len(ceilings) != 8:
        raise ValueError(f"Expected exactly 8 muscle groups, got {len(ceilings)}")
    _phase2_config = data
    return data

def seed_exercise_state(path=None):
    from trainlog.db import execute, now
    data = load_phase2_config()
    for exercise_id, item in data["exercises"].items():
        rep_range = item.get("rep_range") or (0, 0)
        rir = item.get("rir_target") or (0, 0)
        execute("INSERT OR IGNORE INTO exercise_state "
                "(exercise_id,current_load,added_weight_lb,rep_range_lo,rep_range_hi,target_sets,load_step,rir_target_lo,rir_target_hi,progression_mode,recent_sessions_json,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (exercise_id, item.get("start_load"), 0, rep_range[0], rep_range[1], item["sets"],
                 item.get("load_step"), rir[0], rir[1], item["progression_mode"], "[]", now()), path=path)
    for group, item in data["muscle_group_ceilings"].items():
        execute("INSERT OR IGNORE INTO muscle_group_state "
                "(muscle_group,current_weekly_sets,last_increase_date,cooldown_sessions_left) VALUES (?,?,NULL,0)",
                (group, item["baseline_weekly_sets"]), path=path)
