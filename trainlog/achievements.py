"""Achievements & variable rewards (Phase F, Tasks 25-26).

Evaluation runs on day-complete, sourced entirely from existing ledgers
(xp_event / progression_event / adherence_stats / adjustment) - never any
duplicate tracking of 'did X just happen'. Unlock rows land in
achievement_unlocked; returns the list newly unlocked this call.
"""
import datetime
import os

import yaml

from trainlog.db import execute, now, query, query_one
from trainlog import config

_CATALOG = None


def load_catalog():
    global _CATALOG
    if _CATALOG is None:
        path = os.path.join(config.APP_DIR, "achievements.yaml")
        with open(path, "r", encoding="utf-8") as f:
            _CATALOG = yaml.safe_load(f)
    return _CATALOG


def _already_unlocked(path=None):
    return {r["achievement_key"] for r in
            query("SELECT achievement_key FROM achievement_unlocked", path=path)}


def _check(key, path=None):
    """Return (unlocked: bool, detail: str) for one achievement."""
    if key == "first_pr":
        r = query_one("SELECT 1 FROM xp_event WHERE source='pr' LIMIT 1",
                      path=path)
        return bool(r), "first PR logged"
    if key == "first_load_increase":
        r = query_one(
            "SELECT 1 FROM progression_event WHERE event_type IN"
            " ('INCREASE_LOAD','INCREASE_DIFFICULTY') LIMIT 1", path=path)
        return bool(r), "first engine increase"
    if key == "first_mesocycle":
        r = query_one(
            "SELECT 1 FROM progression_event WHERE event_type='MESOCYCLE_DELOAD'"
            " LIMIT 1", path=path)
        return bool(r), "a full 12-session mesocycle completed"
    if key == "momentum_3x":
        rows = query("SELECT detail FROM xp_event WHERE source='momentum'",
                     path=path)
        weeks = {r["detail"] for r in rows if r["detail"]}
        return len(weeks) >= 3, f"{len(weeks)} momentum weeks"
    if key == "deload_3x":
        rows = query(
            "SELECT DISTINCT cycle||'-'||week w FROM day_log"
            " WHERE day_complete=1 AND week=4"
            " AND weekday IN ('monday','wednesday','friday')", path=path)
        return len(rows) >= 3, f"{len(rows)} deload weeks with a gating day done"
    if key == "anchor_30":
        from trainlog.reports import adherence_stats
        s = adherence_stats()["anchor_best_streak"]
        return s >= 30, f"anchor streak {s}"
    if key == "guardrail_clean_week":
        since = (datetime.date.today() -
                 datetime.timedelta(days=7)).isoformat()
        created = query_one(
            "SELECT COUNT(*) c FROM adjustment WHERE scope_date>=?", (since,),
            path=path)
        pending = query_one(
            "SELECT COUNT(*) c FROM adjustment WHERE scope_date>=?"
            " AND status='pending'", (since,), path=path)
        n = created["c"] if created else 0
        p = pending["c"] if pending else 0
        return (n >= 1 and p == 0), f"{n} adjustments, {p} pending"
    return False, ""


def evaluate_achievements(date_str=None, path=None):
    """Unlock any newly-earned achievements. Returns list of unlocked dicts."""
    catalog = load_catalog()
    done = _already_unlocked(path=path)
    newly = []
    for key, meta in catalog.items():
        if key in done:
            continue
        ok, detail = _check(key, path=path)
        if ok:
            execute(
                "INSERT OR IGNORE INTO achievement_unlocked"
                " (achievement_key, unlocked_at, detail) VALUES (?,?,?)",
                (key, now(), detail), path=path)
            newly.append({"key": key, "title": meta.get("title", key),
                          "detail": detail})
    return newly


def trophy_case(path=None):
    """Every catalog entry with unlock state for the /trophies page."""
    catalog = load_catalog()
    unlocked = {r["achievement_key"]: dict(r) for r in
                query("SELECT * FROM achievement_unlocked", path=path)}
    out = []
    for key, meta in catalog.items():
        u = unlocked.get(key)
        out.append({"key": key, "title": meta.get("title", key),
                    "condition": meta.get("condition", ""),
                    "unlocked": bool(u),
                    "unlocked_at": u["unlocked_at"] if u else None,
                    "detail": u["detail"] if u else None})
    return out
