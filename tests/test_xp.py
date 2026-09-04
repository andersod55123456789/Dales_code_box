"""Phase B XP tests (Tasks 13, 14, 22)."""
import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from trainlog import config
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def test_level_curve_reference_table():
    from trainlog import xp
    assert [xp.level_for_xp(x) for x in
            (0, 149, 150, 324, 325, 1000, 2249, 2250, 5000)] == \
           [1, 1, 2, 2, 3, 6, 9, 10, 16]
    assert [xp.T(n) for n in range(1, 11)] == \
           [0, 150, 325, 525, 750, 1000, 1275, 1575, 1900, 2250]


def test_award_accumulates_and_levels_up(app):
    from trainlog import xp, db
    with app.app_context():
        a, lu, nl = xp.award("day_complete", 20)
        assert (a, lu, nl) == (20, False, 1)
        a, lu, nl = xp.award("pr", 50)
        a, lu, nl = xp.award("progression_event", 25)
        assert db.query_one("SELECT total_xp FROM account_xp WHERE id=1")["total_xp"] == 95
        # cross the 150 boundary exactly
        a, lu, nl = xp.award("momentum", 55)
        assert db.query_one("SELECT total_xp FROM account_xp WHERE id=1")["total_xp"] == 150
        assert lu is True and nl == 2


def _complete_monday(client, date="2026-09-07"):
    r = client.post("/api/day/complete", json={"date": date, "complete": True})
    return r.get_json()


def test_day_complete_awards_base_and_gating_bonus(app):
    client = app.test_client()
    d = _complete_monday(client)
    assert d["ok"] and "xp_awarded" in d and "leveled_up" in d and "new_level" in d
    # Monday is gating: 20 base + 10 gating (no exercises logged yet)
    assert d["xp_awarded"] == 30


def test_gating_bonus_only_mon_wed_fri(app):
    client = app.test_client()
    # 2026-09-08 is a Tuesday - not gating
    d = client.post("/api/day/complete",
                    json={"date": "2026-09-08", "complete": True}).get_json()
    assert d["xp_awarded"] == 20


def test_pr_requires_prior_history(app):
    from trainlog import xp, db
    with app.app_context():
        db.execute(
            "INSERT INTO day_log (log_date,weekday,cycle,week,week_repeat,"
            "week_type,day_complete,created_at) VALUES "
            "('2026-09-07','monday',1,1,0,'A',1,'now')")
        d = db.query_one("SELECT id FROM day_log WHERE log_date='2026-09-07'")
        # first-ever session for the lift: no PR
        assert xp.detect_pr("2026-09-07", "back_squat", d["id"]) is None
        # log a prior (earlier) day at a lower load, then today beats it
        db.execute(
            "INSERT INTO day_log (log_date,weekday,cycle,week,week_repeat,"
            "week_type,day_complete,created_at) VALUES "
            "('2026-08-31','monday',1,1,0,'A',1,'now')")
        d0 = db.query_one("SELECT id FROM day_log WHERE log_date='2026-08-31'")
        db.execute(
            "INSERT INTO set_log (day_log_id,exercise_id,exercise_name,"
            "set_index,is_backoff,actual_reps,actual_load,completed,created_at)"
            " VALUES (?,?,?,?,0,10,180.0,1,'now')",
            (d0["id"], "back_squat", "Back squat", 1))
        db.execute(
            "INSERT INTO set_log (day_log_id,exercise_id,exercise_name,"
            "set_index,is_backoff,actual_reps,actual_load,completed,created_at)"
            " VALUES (?,?,?,?,0,10,190.0,1,'now')",
            (d["id"], "back_squat", "Back squat", 1))
        res = xp.detect_pr("2026-09-07", "back_squat", d["id"])
        assert res is not None and res[0] == xp.XP_PR


def test_pr_suppressed_but_day_xp_awarded_on_guardrail(app):
    client = app.test_client()
    from trainlog import db
    # log a Monday with reps in range
    for i in range(1, 5):
        client.post("/api/set", json={"date": "2026-09-07",
                    "exercise_id": "back_squat", "set_index": i,
                    "actual_reps": 8, "actual_load": 190.0, "completed": True})
    with app.app_context():
        db.execute(
            "INSERT INTO adjustment(scope_date,rule_key,message,suggestion,"
            "status,created_at) VALUES ('2026-09-07','knee','m','s','applied','now')")
    d = client.post("/api/day/complete",
                    json={"date": "2026-09-07", "complete": True}).get_json()
    # day XP still awarded (base + gating + in-range), but no PR event
    assert d["xp_awarded"] >= 30
    with app.app_context():
        assert db.query_one(
            "SELECT 1 FROM xp_event WHERE source='pr'") is None


def test_momentum_awards_once_per_iso_week(app):
    from trainlog import xp, db
    with app.app_context():
        # log 5 active days in the trailing 7 ending 2026-09-07
        for i, day in enumerate(["2026-09-03", "2026-09-04", "2026-09-05",
                                 "2026-09-06", "2026-09-07"]):
            db.execute(
                "INSERT INTO day_log (log_date,weekday,cycle,week,week_repeat,"
                "week_type,day_complete,created_at) VALUES (?,?,1,1,0,'A',1,'now')",
                (day, "monday"))
        res = xp.maybe_award_momentum("2026-09-07")
        assert res is not None and res[0] == xp.XP_MOMENTUM_WEEK
        # second call same ISO week awards nothing
        assert xp.maybe_award_momentum("2026-09-07") is None
