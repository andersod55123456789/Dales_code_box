import json

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from trainlog import config
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def _post_sets(client, date="2026-09-07", reps=(10, 10, 10, 10)):
    for index, count in enumerate(reps, 1):
        response = client.post("/api/set", json={"date": date, "exercise_id": "back_squat",
            "set_index": index, "actual_reps": count, "actual_load": 185, "completed": True})
        assert response.get_json()["ok"]


def test_feedback_updates_state_and_writes_event(app):
    client = app.test_client()
    _post_sets(client)
    response = client.post("/api/exercise/feedback", json={"date": "2026-09-07",
        "exercise_id": "back_squat", "rir_feedback": "TARGET"})
    assert response.status_code == 200 and response.get_json()["action"] == "INCREASE_LOAD"
    from trainlog import db
    with app.app_context():
        state = db.query_one("SELECT * FROM exercise_state WHERE exercise_id='back_squat'")
        assert state["current_load"] == 190 and state["sessions_in_mesocycle"] == 1
        assert db.query_one("SELECT event_type FROM progression_event WHERE exercise_id='back_squat'")["event_type"] == "INCREASE_LOAD"


def test_applied_guardrail_leaves_state_byte_identical(app):
    client = app.test_client()
    _post_sets(client, date="2026-09-14", reps=(8, 6, 6, 6))
    from trainlog import db
    with app.app_context():
        before = tuple(db.query_one("SELECT * FROM exercise_state WHERE exercise_id='back_squat'"))
        db.execute("INSERT INTO adjustment(scope_date,rule_key,message,suggestion,status,created_at) VALUES (?,?,?,?,?,?)",
                   ("2026-09-14", "test", "test", "test", "applied", db.now()))
    response = client.post("/api/exercise/feedback", json={"date": "2026-09-14",
        "exercise_id": "back_squat", "rir_feedback": "FAILURE"})
    assert response.get_json()["skipped"] == "guardrail"
    with app.app_context():
        after = tuple(db.query_one("SELECT * FROM exercise_state WHERE exercise_id='back_squat'"))
        assert before == after


def test_seed_is_idempotent_and_prescription_reads_live_state(app):
    from trainlog import db
    with app.app_context():
        db.init_db()
        assert db.query_one("SELECT COUNT(*) c FROM exercise_state")["c"] == 20
        assert db.query_one("SELECT COUNT(*) c FROM muscle_group_state")["c"] == 8
        db.execute("UPDATE exercise_state SET current_load=192.5 WHERE exercise_id='back_squat'")
    day = app.test_client().get("/api/day/2026-09-07").get_json()
    squat = next(ex for ex in day["exercises"] if ex["id"] == "back_squat")
    assert (squat["target_load"], squat["sets"]) == (192.5, 4)


def test_rir_prompt_and_route_exist(app):
    client = app.test_client()
    html = client.get("/day/2026-09-07").get_data(as_text=True)
    assert "Could have done 4+ more" in html
    response = client.post("/api/exercise/feedback", json={"date": "2026-09-07",
        "exercise_id": "back_squat", "rir_feedback": "TARGET"})
    assert response.status_code == 200 and response.get_json()["ok"]
