"""Phase G safety wiring audit (Task 28).

1. Import direction: engagement modules may import the engine, never reverse.
2. Credit suppression: guardrail days earn completion XP but no PR/event credit.
3. No easier-target branch: engagement layer never writes the prescription.
"""
import ast
import os

import pytest

from trainlog import config

# Engine/prescription side (must never depend on engagement layer).
ENGINE_SIDE = {"engine", "prescription", "loading", "loading_engine",
               "guardrails"}
# Engagement layer (may import engine side).
ENGAGEMENT = {"xp", "attributes", "mission", "achievements", "reports"}


def _imports_of(path):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _trainlog_module_name(imp):
    # 'trainlog.xp' -> 'xp'; 'xp' -> 'xp'
    parts = imp.split(".")
    if parts[0] == "trainlog" and len(parts) > 1:
        return parts[1]
    return parts[0]


def test_engine_never_imports_engagement():
    pkg = config.PKG_DIR
    offenders = []
    for fname in os.listdir(pkg):
        if not fname.endswith(".py"):
            continue
        mod = fname[:-3]
        if mod not in ENGINE_SIDE:
            continue
        imps = {_trainlog_module_name(i) for i in
                _imports_of(os.path.join(pkg, fname))}
        bad = imps & ENGAGEMENT
        if bad:
            offenders.append((mod, sorted(bad)))
    assert not offenders, f"engine-side importing engagement layer: {offenders}"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def test_credit_suppression_on_guardrail_day(app):
    """Applied adjustment: day XP still awarded, but NO volume-based credit -
    no pr xp_event, no progression_event, and no PR/progression achievement
    unlocks. (guardrail_clean_week MAY legitimately unlock - it rewards
    resolving warnings, not volume.)"""
    client = app.test_client()
    from trainlog import db
    for i in range(1, 5):
        client.post("/api/set", json={"date": "2026-09-07",
                    "exercise_id": "back_squat", "set_index": i,
                    "actual_reps": 12, "actual_load": 250.0, "completed": True})
    with app.app_context():
        db.execute(
            "INSERT INTO adjustment(scope_date,rule_key,message,suggestion,"
            "status,created_at) VALUES ('2026-09-07','knee','m','s','applied','now')")
    d = client.post("/api/day/complete",
                    json={"date": "2026-09-07", "complete": True}).get_json()
    assert d["xp_awarded"] > 0  # completion XP still earned
    with app.app_context():
        # no volume-based credit for volume it didn't actually do
        assert db.query_one("SELECT 1 FROM xp_event WHERE source='pr'") is None
        assert db.query_one(
            "SELECT 1 FROM progression_event WHERE exercise_id='back_squat'") is None
        # no PR/progression achievement unlocked by this suppressed day
        unlocked = {r["achievement_key"] for r in
                    db.query("SELECT achievement_key FROM achievement_unlocked")}
        assert not ({"first_pr", "first_load_increase"} & unlocked)


def test_no_easier_target_branch(app):
    """20 HOLD days: current_load and rep_range never reduced by the engine
    or the engagement layer. Prescription is read-only input."""
    client = app.test_client()
    from trainlog import db
    with app.app_context():
        start = db.query_one(
            "SELECT current_load, rep_range_lo, rep_range_hi FROM exercise_state"
            " WHERE exercise_id='back_squat'")
    # 20 mid-range, TARGET sessions -> HOLD each time
    for n in range(20):
        date = f"2026-09-{7 + (n % 20):02d}" if 7 + n <= 30 else "2026-09-30"
        for i in range(1, 5):
            client.post("/api/set", json={"date": date,
                        "exercise_id": "back_squat", "set_index": i,
                        "actual_reps": 8, "actual_load": 185.0, "completed": True})
        client.post("/api/exercise/feedback", json={"date": date,
                    "exercise_id": "back_squat", "rir_feedback": "TARGET"})
    with app.app_context():
        end = db.query_one(
            "SELECT current_load, rep_range_lo, rep_range_hi FROM exercise_state"
            " WHERE exercise_id='back_squat'")
    assert end["current_load"] == start["current_load"]
    assert end["rep_range_lo"] == start["rep_range_lo"]
    assert end["rep_range_hi"] == start["rep_range_hi"]
