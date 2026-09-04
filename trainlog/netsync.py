"""Network-share sync for the training database.

Copies the live training.db to a (possibly intermittent) network share using
SQLite's online .backup() API, which is safe against a live, WAL-mode source.
Behavior:
- If the share is reachable: write the live training.db AND a timestamped
  snapshot, then clear any queued retry marker.
- If not: drop a 'pending' marker locally; the next successful sync (or app
  startup) retries. Never raises - sync must never break logging.

Config lives in program.yaml under `netsync:` so the path is data, not code.
"""
import datetime
import os
import sqlite3

from trainlog import config
from trainlog.program import load_program

PENDING_NAME = ".netsync_pending"


def _cfg():
    """Return (share_dir, enabled). Reads program.yaml's optional netsync block."""
    try:
        ns = load_program().get("netsync") or {}
    except Exception:
        return None, False
    return ns.get("share_dir"), bool(ns.get("enabled", True))


def _pending_path():
    return os.path.join(config.DATA_DIR, PENDING_NAME)


def _mark_pending():
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_pending_path(), "w") as f:
            f.write(datetime.datetime.now().isoformat())
    except OSError:
        pass


def _clear_pending():
    try:
        if os.path.exists(_pending_path()):
            os.remove(_pending_path())
    except OSError:
        pass


def share_reachable(share_dir):
    return bool(share_dir) and os.path.isdir(share_dir)


def _copy_db(dest_path):
    """Online-backup the live DB to dest_path via SQLite's .backup() API.

    Opens a fresh connection straight to the DB file rather than the Flask-g
    request connection, so this works both inside requests and standalone
    (startup retry, CLI) with no app context required. Safe against a live,
    WAL-mode source.
    """
    src = sqlite3.connect(config.DATABASE_PATH)
    tgt = sqlite3.connect(dest_path)
    try:
        with tgt:
            src.backup(tgt)
    finally:
        tgt.close()
        src.close()


def sync_now(keep_snapshots=True, max_snapshots=30):
    """Attempt one sync. Returns a status dict; never raises."""
    share_dir, enabled = _cfg()
    if not enabled:
        return {"ok": False, "status": "disabled", "share": share_dir}
    if not share_dir:
        return {"ok": False, "status": "no_share_configured", "share": None}
    if not share_reachable(share_dir):
        _mark_pending()
        return {"ok": False, "status": "unreachable_queued", "share": share_dir}
    try:
        os.makedirs(share_dir, exist_ok=True)
        live = os.path.join(share_dir, "training.db")
        _copy_db(live)
        snap = None
        if keep_snapshots:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
            snap = os.path.join(share_dir, f"training-{stamp}.db")
            _copy_db(snap)
            _prune_snapshots(share_dir, max_snapshots)
        _clear_pending()
        return {"ok": True, "status": "synced", "share": share_dir,
                "live": live, "snapshot": snap}
    except OSError as e:
        _mark_pending()
        return {"ok": False, "status": f"error_queued: {e}", "share": share_dir}


def _prune_snapshots(share_dir, keep):
    try:
        snaps = sorted(f for f in os.listdir(share_dir)
                       if f.startswith("training-") and f.endswith(".db"))
        for old in snaps[:-keep]:
            try:
                os.remove(os.path.join(share_dir, old))
            except OSError:
                pass
    except OSError:
        pass


def pending():
    """True if a previous sync was queued and not yet completed."""
    return os.path.exists(_pending_path())


def status():
    share_dir, enabled = _cfg()
    return {"enabled": enabled, "share": share_dir,
            "reachable": share_reachable(share_dir), "pending": pending()}
