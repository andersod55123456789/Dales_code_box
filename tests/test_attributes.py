"""Phase C attribute formula tests (Task 17)."""
import datetime

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from trainlog import config
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def test_strength_seeded_ratios(app):
    from trainlog import attributes
    with app.app_context():
        attributes.recompute_attributes()
        r = attributes.query_one(
            "SELECT score, level FROM attribute_state WHERE attribute='strength'")
        # all three lifts at start_load -> ratio 1.0 -> 100*1.0/1.5 = 66.7
        assert round(r["score"], 1) == 66.7
        assert r["level"] == 7


def test_strength_scales_with_load(app):
    from trainlog import attributes, db
    with app.app_context():
        # squat +50% (1.5), deadlift & ohp at baseline (1.0) -> mean 1.1667
        db.execute("UPDATE exercise_state SET current_load=277.5"
                   " WHERE exercise_id='back_squat'")
        attributes.recompute_attributes()
        r = attributes.query_one(
            "SELECT score FROM attribute_state WHERE attribute='strength'")
        expected = 100 * min(1.5, (1.5 + 1.0 + 1.0) / 3) / 1.5
        assert round(r["score"], 1) == round(expected, 1)


def test_empty_data_fallbacks(app):
    from trainlog import attributes
    with app.app_context():
        attributes.recompute_attributes()
        rows = {r["attribute"]: r["score"] for r in
                attributes.query("SELECT attribute, score FROM attribute_state")}
        # Endurance: no saturdays, no mile -> 0.6*50 + 0.4*50 = 50
        assert round(rows["endurance"], 1) == 50.0
        # Agility: no drills -> fallback to Tuesday adherence (0 logged) = 0
        assert round(rows["agility"], 1) == 0.0
        # Mobility: no anchor -> 0.7*0 + 0.3*50 = 15
        assert round(rows["mobility"], 1) == 15.0


def test_mobility_counts_anchor_days(app):
    from trainlog import attributes, db
    from trainlog.program import load_program
    with app.app_context():
        n_anchor = len(load_program()["anchor"])
        # 7 of the trailing 14 days fully anchored
        for i in range(7):
            ds = (datetime.date.today() -
                  datetime.timedelta(days=i)).isoformat()
            db.execute(
                "INSERT INTO day_log (log_date,weekday,cycle,week,week_repeat,"
                "week_type,day_complete,created_at) VALUES (?,?,1,1,0,'A',0,'now')",
                (ds, "monday"))
            did = db.query_one("SELECT id FROM day_log WHERE log_date=?", (ds,))["id"]
            for item in load_program()["anchor"]:
                db.execute(
                    "INSERT INTO anchor_log (day_log_id,item_key,field_key,"
                    "completed,created_at) VALUES (?,?,'__done__',1,'now')",
                    (did, item["key"]))
        attributes.recompute_attributes()
        r = attributes.query_one(
            "SELECT score FROM attribute_state WHERE attribute='mobility'")
        # 0.7*(7/14*100) + 0.3*50 (no sit-and-reach) = 35 + 15 = 50
        assert round(r["score"], 1) == 50.0


def test_endurance_with_mile_improvement(app):
    from trainlog import attributes, db
    with app.app_context():
        # baseline mile 600s, then a faster 540s
        db.execute(
            "INSERT INTO test_battery (test_date,cycle,week,metric_key,value_num,"
            "created_at) VALUES ('2026-08-01',1,1,'mile_1',600,'now')")
        db.execute(
            "INSERT INTO test_battery (test_date,cycle,week,metric_key,value_num,"
            "created_at) VALUES ('2026-08-15',1,2,'mile_1',540,'now')")
        attributes.recompute_attributes()
        r = attributes.query_one(
            "SELECT score FROM attribute_state WHERE attribute='endurance'")
        # z2 = 50 (no saturdays); mile = min(1.2,600/540)/1.2*100 = 92.59
        expected = 0.6 * 50 + 0.4 * (min(1.2, 600 / 540) / 1.2 * 100)
        assert round(r["score"], 1) == round(expected, 1)
