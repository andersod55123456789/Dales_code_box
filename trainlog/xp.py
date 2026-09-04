"""XP & account level (Phase B).

Reads existing ledgers and writes xp_event / account_xp. Never writes the
prescription - the engagement layer is read-only against the loading engine.
All arithmetic is locked in PHASE2/06_TASKS.md (Tasks 12-14).
"""
import datetime

from trainlog.db import execute, now, query, query_one

# Award table (locked)
XP_DAY_COMPLETE = 20
XP_GATING_DAY_BONUS = 10        # Mon/Wed/Fri only
XP_EXERCISE_IN_RANGE = 5        # per exercise finished inside rep range
XP_RIR_IN_ZONE = 5              # per exercise whose feedback hit rir_target
XP_PR = 50
XP_PROGRESSION_EVENT = 25       # INCREASE_LOAD / INCREASE_DIFFICULTY
XP_MOMENTUM_WEEK = 40           # once per ISO week
XP_CHALLENGE = 15               # Phase F

GATING_WEEKDAYS = ("monday", "wednesday", "friday")

# Test-battery metric direction for PR detection. Default 'higher is
# better'; timed / distance-as-time metrics are 'lower is better'.
LOWER_IS_BETTER = {"mile_time", "one_mile", "mile", "five_ten_five",
                   "5_10_5", "ladder", "plank_time"}
METRIC_DIRECTION = {}


def T(n):
    """Cumulative XP required to reach level n (n >= 1). T(1) = 0."""
    n = int(n)
    if n <= 1:
        return 0
    return int(round(150 * (n - 1) + 12.5 * (n - 1) * (n - 2)))


def level_for_xp(total):
    """Largest N with T(N) <= total."""
    total = int(total or 0)
    lvl = 1
    while T(lvl + 1) <= total:
        lvl += 1
    return lvl


def xp_into_level(total):
    total = int(total or 0)
    return total - T(level_for_xp(total))


def xp_for_next_level(total):
    """XP span of the current level (cost to go from level N to N+1)."""
    lvl = level_for_xp(total)
    return T(lvl + 1) - T(lvl)


def _direction(metric_key):
    if metric_key in METRIC_DIRECTION:
        return METRIC_DIRECTION[metric_key]
    return "lower" if metric_key in LOWER_IS_BETTER else "higher"


def award(source, amount, exercise_id=None, day_log_id=None, detail=None,
          path=None):
    """Insert an xp_event row, recompute account_xp.

    Returns (xp_awarded, leveled_up, new_level).
    """
    amount = int(amount or 0)
    execute(
        "INSERT INTO xp_event (source, amount, exercise_id, day_log_id,"
        " detail, created_at) VALUES (?,?,?,?,?,?)",
        (source, amount, exercise_id, day_log_id, detail, now()), path=path)
    row = query_one("SELECT total_xp, level FROM account_xp WHERE id=1",
                    path=path)
    old_level = row["level"] if row else 1
    total = (row["total_xp"] if row else 0) + amount
    new_level = level_for_xp(total)
    execute("UPDATE account_xp SET total_xp=?, level=?, updated_at=? WHERE id=1",
            (total, new_level, now()), path=path)
    return amount, new_level > old_level, new_level


def get_state(path=None):
    """(total_xp, level, xp_into_level, xp_for_next_level) for the nav bar."""
    row = query_one("SELECT total_xp, level FROM account_xp WHERE id=1",
                    path=path)
    total = row["total_xp"] if row else 0
    return {
        "total_xp": total,
        "level": row["level"] if row else 1,
        "xp_into_level": xp_into_level(total),
        "xp_for_next_level": xp_for_next_level(total),
    }


def detect_pr(date_str, exercise_id, day_log_id=None, path=None):
    """Award +50 if today's top load strictly beats every earlier day.

    First-ever session cannot be a PR (needs prior history). Returns the
    award tuple or None. Caller must already have skipped guardrail days.
    """
    today = query_one(
        "SELECT MAX(s.actual_load) v FROM set_log s"
        " JOIN day_log d ON d.id=s.day_log_id"
        " WHERE d.log_date=? AND s.exercise_id=? AND s.completed=1",
        (date_str, exercise_id), path=path)
    prior = query_one(
        "SELECT MAX(s.actual_load) v FROM set_log s"
        " JOIN day_log d ON d.id=s.day_log_id"
        " WHERE d.log_date<? AND s.exercise_id=? AND s.completed=1",
        (date_str, exercise_id), path=path)
    if not today or today["v"] is None:
        return None
    if not prior or prior["v"] is None:
        return None  # first-ever session: no baseline to beat
    if today["v"] > prior["v"]:
        return award("pr", XP_PR, exercise_id=exercise_id,
                     day_log_id=day_log_id,
                     detail=f"top load {today['v']} > prior best {prior['v']}",
                     path=path)
    return None


def detect_test_pr(metric_key, value_num, path=None):
    """Award +50 when a saved test-battery value beats its previous best."""
    if value_num is None:
        return None
    direction = _direction(metric_key)
    rows = query(
        "SELECT value_num FROM test_battery WHERE metric_key=?"
        " AND value_num IS NOT NULL", (metric_key,), path=path)
    prior = [r["value_num"] for r in rows]
    if not prior:
        return None  # first recording: no baseline
    best = min(prior) if direction == "lower" else max(prior)
    improved = value_num < best if direction == "lower" else value_num > best
    if improved:
        return award("pr", XP_PR, detail=f"test {metric_key} {value_num}"
                     f" beats {best}", path=path)
    return None


def maybe_award_momentum(date_str, day_log_id=None, path=None):
    """Award +40 once per ISO week when weekly momentum target is hit.

    Task 14 placeholder -> filled by Phase E (reports.momentum). Returns the
    award tuple or None.
    """
    from trainlog.reports import momentum
    m = momentum(date_str)
    if not m["hit"]:
        return None
    iso = datetime.date.fromisoformat(date_str).isocalendar()
    like = f"{iso[0]}-W{iso[1]:02d}"
    rows = query("SELECT detail FROM xp_event WHERE source='momentum'",
                 path=path)
    if any(r["detail"] == like for r in rows):
        return None  # already awarded this ISO week
    return award("momentum", XP_MOMENTUM_WEEK, day_log_id=day_log_id,
                 detail=like, path=path)


def _guardrail_active(date_str, path=None):
    """True if any applied adjustment or a deload week suppresses PR credit.

    Mirrors loading_engine's skip rule (safety wiring G1): a guardrail-affected
    day still completes the mission and earns completion XP, but never earns
    PR/challenge credit for volume it didn't actually do.
    """
    adj = query_one(
        "SELECT 1 FROM adjustment WHERE scope_date=? AND status='applied'",
        (date_str,), path=path)
    if adj:
        return True
    from trainlog.engine import is_deload
    from trainlog.logbook import get_state
    if is_deload(get_state()["week"]):
        return True
    return False


def award_day_complete(date_str, path=None):
    """Award all XP for a completed day. Returns a summary dict for the
    /api/day/complete response: xp_awarded, leveled_up, new_level, breakdown.
    """
    from trainlog.logbook import get_or_create_day_log
    from trainlog.prescription import weekday_of

    d = get_or_create_day_log(date_str)
    day_log_id = d["id"]
    total_awarded = 0
    leveled = False
    new_level = query_one("SELECT level FROM account_xp WHERE id=1",
                          path=path)["level"]
    breakdown = []

    def _add(source, amount, exercise_id=None, detail=None):
        nonlocal total_awarded, leveled, new_level
        a, lu, nl = award(source, amount, exercise_id=exercise_id,
                          day_log_id=day_log_id, detail=detail, path=path)
        total_awarded += a
        leveled = leveled or lu
        new_level = nl
        if detail:
            breakdown.append(detail)

    # Base completion + gating bonus
    wd = weekday_of(date_str)
    _add("day_complete", XP_DAY_COMPLETE, detail=f"+{XP_DAY_COMPLETE} day complete")
    if wd in GATING_WEEKDAYS:
        _add("gating_bonus", XP_GATING_DAY_BONUS,
             detail=f"+{XP_GATING_DAY_BONUS} gating day")

    # Per-engine-exercise bonuses
    engine_rows = query(
        "SELECT exercise_id, rep_range_lo, rep_range_hi, rir_target_lo,"
        " rir_target_hi, progression_mode FROM exercise_state"
        " WHERE progression_mode != 'excluded'", path=path)
    for ex in engine_rows:
        eid = ex["exercise_id"]
        sets = query(
            "SELECT s.actual_reps FROM set_log s"
            " JOIN day_log d ON d.id=s.day_log_id"
            " WHERE d.log_date=? AND s.exercise_id=? AND s.completed=1"
            " AND s.is_backoff=0 ORDER BY s.set_index",
            (date_str, eid), path=path)
        reps = [r["actual_reps"] for r in sets if r["actual_reps"] is not None]
        if reps and all(ex["rep_range_lo"] <= r <= ex["rep_range_hi"]
                        for r in reps):
            _add("exercise_in_range", XP_EXERCISE_IN_RANGE, exercise_id=eid,
                 detail=f"+{XP_EXERCISE_IN_RANGE} {eid} in range")
        fb = query_one(
            "SELECT rir_feedback FROM exercise_feedback"
            " WHERE day_log_id=? AND exercise_id=?", (day_log_id, eid),
            path=path)
        if fb:
            rir_val = {"EASY": 4.0, "TARGET": 2.5, "HARD": 1.0,
                       "FAILURE": 0.0}.get(fb["rir_feedback"])
            if rir_val is not None and \
                    ex["rir_target_lo"] <= rir_val <= ex["rir_target_hi"]:
                _add("rir_in_zone", XP_RIR_IN_ZONE, exercise_id=eid,
                     detail=f"+{XP_RIR_IN_ZONE} {eid} RIR in zone")

    # PR detection - suppressed on guardrail/deload days (safety wiring G1)
    if not _guardrail_active(date_str, path=path):
        for ex in engine_rows:
            res = detect_pr(date_str, ex["exercise_id"],
                            day_log_id=day_log_id, path=path)
            if res:
                a, lu, nl = res
                total_awarded += a
                leveled = leveled or lu
                new_level = nl
                breakdown.append(f"+{a} PR {ex['exercise_id']}")

    # Weekly momentum (Phase E fills the logic; deduped per ISO week)
    res = maybe_award_momentum(date_str, day_log_id=day_log_id, path=path)
    if res:
        a, lu, nl = res
        total_awarded += a
        leveled = leveled or lu
        new_level = nl
        breakdown.append(f"+{a} momentum week")

    return {"xp_awarded": total_awarded, "leveled_up": leveled,
            "new_level": new_level, "breakdown": breakdown}
