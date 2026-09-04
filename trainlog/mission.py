"""Mission framing (Phase D, Tasks 19-20).

A mission spans the WHOLE day (anchor + main work), not just lifting. The
mission summary is additive alongside the existing prescription - the
exercise list is unchanged. Categories: Strength / Endurance / Agility /
Mobility / Conditioning.
"""
from trainlog.loading_config import load_phase2_config
from trainlog.prescription import weekday_of
from trainlog import xp as _xp

# Minutes fallbacks per block type when program.yaml has no explicit duration.
ANCHOR_ITEM_MINUTES = 5
DRILL_BLOCK_MINUTES = 10


def _categorize(ex, weekday, engine_ids):
    """Map a main-work exercise block to a mission category. Priority order
    per Task 19. Returns None for blocks that are not mission content."""
    eid = ex.get("id")
    if eid == "core_finisher":
        return "Conditioning"
    if eid in engine_ids:
        return "Strength"
    if ex.get("kind") == "cardio":
        return "Endurance"
    if weekday == "tuesday" and ex.get("kind") in ("drill", "plyo", "main"):
        return "Agility"
    if ex.get("kind") in ("drill", "plyo"):
        return "Agility"
    return None


def mission_summary(date_str, day=None):
    """Build the mission object for a date. ``day`` is the existing built day
    payload (from logbook.get_day) - pass it in to avoid rebuilding."""
    if day is None:
        from trainlog.logbook import get_day
        day = get_day(date_str)
    weekday = weekday_of(date_str)
    engine_ids = set(load_phase2_config()["exercises"].keys())

    cats = {}

    def add(cat, count=1, minutes=0):
        c = cats.setdefault(cat, {"count": 0, "minutes": 0})
        c["count"] += count
        c["minutes"] += int(round(minutes))

    # Main work
    for ex in day.get("exercises", []):
        cat = _categorize(ex, weekday, engine_ids)
        if not cat:
            continue
        if cat == "Strength":
            sets = ex.get("sets") or 0
            minutes = sets * (45 + ex.get("rest_seconds", 90)) / 60.0
            add(cat, 1, minutes)
        else:
            minutes = ex.get("minutes") or (
                DRILL_BLOCK_MINUTES if cat in ("Agility",) else
                next((f.get("target") for f in ex.get("extra_fields", [])
                      if f.get("key") == "minutes"), 0) or 0)
            add(cat, 1, minutes)

    # Anchor -> Mobility
    for item in day.get("anchor", []):
        minutes = next((f.get("target") for f in item.get("fields", [])
                        if f.get("key") == "minutes"), None)
        add("Mobility", 1, minutes or ANCHOR_ITEM_MINUTES)

    reward = _reward_text(weekday)
    return {"categories": cats, "reward_text": reward}


def _reward_text(weekday):
    parts = [f"+{_xp.XP_DAY_COMPLETE} XP"]
    if weekday in _xp.GATING_WEEKDAYS:
        parts.append(f"+{_xp.XP_GATING_DAY_BONUS} gating bonus")
    parts.append(f"up to +{_xp.XP_EXERCISE_IN_RANGE + _xp.XP_RIR_IN_ZONE}"
                 " per-exercise bonuses")
    return ", ".join(parts)
