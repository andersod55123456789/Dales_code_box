import os
import sqlite3
from datetime import datetime

from flask import g

from trainlog import config
from trainlog.program import load_program


def _db_path(path=None):
    return path or config.DATABASE_PATH


def get_db(path=None):
    """Connection with row_factory = sqlite3.Row.

    With no argument, returns the request-scoped connection stored on
    Flask ``g`` (created on first use). With ``path``, returns a fresh
    standalone connection for that file (used by verifies/tests against a
    temp DB - see PHASE2/06_TASKS.md rule 2b); the caller closes it.
    """
    if path is not None:
        conn = sqlite3.connect(_db_path(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    if "db" not in g:
        g.db = sqlite3.connect(config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path=None):
    """Create data/, run the schema, seed program_state from meta.started_on.

    ``path`` overrides the database file (temp DB for verifies/tests).
    Every schema statement is IF NOT EXISTS and the seed is
    INSERT OR IGNORE, so this is safe to run on every boot.
    """
    db_file = _db_path(path)
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    with open(config.SCHEMA_SQL, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    started_on = load_program()["meta"]["started_on"]
    conn.execute(
        "INSERT OR IGNORE INTO program_state "
        "(id, cycle, week, week_repeat, ohp_cycle_offset, reassess_banner,"
        " started_on, updated_at) VALUES (1, 1, 1, 0, 0, NULL, ?, ?)",
        (started_on, now()),
    )
    conn.commit()
    conn.close()


def query(sql, args=(), path=None):
    """Run a SELECT, return a list of sqlite3.Row."""
    return get_db(path).execute(sql, args).fetchall()


def query_one(sql, args=(), path=None):
    """Run a SELECT, return the first row or None."""
    return get_db(path).execute(sql, args).fetchone()


def execute(sql, args=(), path=None):
    """Run a write statement and commit. Returns the cursor."""
    db = get_db(path)
    cur = db.execute(sql, args)
    db.commit()
    return cur


def now():
    """'YYYY-MM-DD HH:MM:SS' local time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
