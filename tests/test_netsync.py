"""netsync tests: reachable sync writes live+snapshot, unreachable queues."""
import os
import sqlite3

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from trainlog import config
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "training.db"))
    from trainlog import create_app
    return create_app()


def _set_share(monkeypatch, path):
    from trainlog import netsync
    monkeypatch.setattr(netsync, "_cfg",
                        lambda: (str(path) if path else None, True))


def test_sync_writes_live_and_snapshot(app, tmp_path, monkeypatch):
    share = tmp_path / "share"
    share.mkdir()
    with app.app_context():
        from trainlog import db, netsync
        _set_share(monkeypatch, share)
        # put something in the DB so the copy is verifiable
        db.execute("INSERT INTO xp_event (source,amount,created_at)"
                   " VALUES ('day_complete',20,'now')")
        res = netsync.sync_now()
        assert res["ok"] and res["status"] == "synced"
        assert os.path.exists(share / "training.db")
        snaps = [f for f in os.listdir(share)
                 if f.startswith("training-") and f.endswith(".db")]
        assert len(snaps) == 1
        # the live copy actually has the row
        con = sqlite3.connect(str(share / "training.db"))
        n = con.execute("SELECT COUNT(*) FROM xp_event").fetchone()[0]
        con.close()
        assert n == 1
        assert not netsync.pending()


def test_unreachable_share_queues_then_recovers(app, tmp_path, monkeypatch):
    missing = tmp_path / "no_such_dir_xyz"
    with app.app_context():
        from trainlog import db, netsync
        _set_share(monkeypatch, missing)
        res = netsync.sync_now()
        assert not res["ok"] and res["status"] == "unreachable_queued"
        assert netsync.pending()
        # bring the share "up" and retry
        missing.mkdir()
        res2 = netsync.sync_now()
        assert res2["ok"]
        assert not netsync.pending()


def test_sync_endpoint_and_status(app, tmp_path, monkeypatch):
    share = tmp_path / "share"
    share.mkdir()
    with app.app_context():
        from trainlog import netsync
        _set_share(monkeypatch, share)
    client = app.test_client()
    r = client.post("/api/sync_now").get_json()
    assert r["ok"]
    s = client.get("/api/sync_status").get_json()
    assert s["reachable"] and not s["pending"]


def test_day_complete_triggers_sync(app, tmp_path, monkeypatch):
    share = tmp_path / "share"
    share.mkdir()
    with app.app_context():
        from trainlog import netsync
        _set_share(monkeypatch, share)
    client = app.test_client()
    d = client.post("/api/day/complete",
                    json={"date": "2026-09-07", "complete": True}).get_json()
    assert "netsync" in d and d["netsync"]["ok"]
    assert os.path.exists(share / "training.db")
