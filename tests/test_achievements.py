"""Phase F achievement tests (Task 26)."""
import datetime

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from trainlog import config
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def test_first_pr_fires_exactly_once(app):
    from trainlog import achievements, db
    with app.app_context():
        assert achievements.evaluate_achievements("2026-09-07") == []
        db.execute("INSERT INTO xp_event (source,amount,created_at)"
                   " VALUES ('pr',50,'now')")
        first = achievements.evaluate_achievements("2026-09-07")
        assert any(a["key"] == "first_pr" for a in first)
        # second qualifying day does not re-unlock
        second = achievements.evaluate_achievements("2026-09-08")
        assert not any(a["key"] == "first_pr" for a in second)


def test_first_load_increase(app):
    from trainlog import achievements, db
    with app.app_context():
        db.execute(
            "INSERT INTO progression_event (exercise_id,event_type,created_at)"
            " VALUES ('back_squat','INCREASE_LOAD','now')")
        out = achievements.evaluate_achievements("2026-09-07")
        assert any(a["key"] == "first_load_increase" for a in out)


def test_guardrail_clean_week_needs_no_pending(app):
    from trainlog import achievements, db
    today = datetime.date.today().isoformat()
    with app.app_context():
        # a pending adjustment blocks it
        db.execute(
            "INSERT INTO adjustment(scope_date,rule_key,message,suggestion,"
            "status,created_at) VALUES (?,'knee','m','s','pending','now')",
            (today,))
        assert not any(a["key"] == "guardrail_clean_week"
                       for a in achievements.evaluate_achievements(today))
        # resolving it (applied) unlocks
        db.execute("UPDATE adjustment SET status='applied'"
                   " WHERE scope_date=?", (today,))
        out = achievements.evaluate_achievements(today)
        assert any(a["key"] == "guardrail_clean_week" for a in out)


def test_momentum_3x_needs_three_distinct_weeks(app):
    from trainlog import achievements, db
    with app.app_context():
        for wk in ("2026-W01", "2026-W02", "2026-W03"):
            db.execute("INSERT INTO xp_event (source,amount,detail,created_at)"
                       " VALUES ('momentum',40,?,'now')", (wk,))
        out = achievements.evaluate_achievements("2026-09-07")
        assert any(a["key"] == "momentum_3x" for a in out)
