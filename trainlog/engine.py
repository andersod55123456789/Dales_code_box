"""Progression engine: rules R0-R8. Pure functions, no DB access."""
from decimal import Decimal, ROUND_HALF_UP


# --- R0 rounding ---------------------------------------------------------
def round_half_up(x):
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_to(x, step=2.5):
    return float(round_half_up(x / step) * Decimal(str(step)))


# --- R1 position ---------------------------------------------------------
def program_week(cycle, week):
    return (cycle - 1) * 4 + week


def week_type(cycle, week):
    return "A" if program_week(cycle, week) % 2 == 1 else "B"


def is_deload(week):
    return week == 4


# --- R2 main lift load ---------------------------------------------------
def increment_for(progression, cfg):
    if progression == "lower":
        return float(cfg["increment_lower"])
    if progression == "upper":
        return float(cfg["increment_upper"])
    return 0.0


def cycle_base_load(baseline, progression, cycle, cfg):
    """Cycle N starts where cycle N-1's week 2 left off. Gains carry over."""
    return baseline + increment_for(progression, cfg) * (cycle - 1)


def working_load(baseline, progression, cycle, week, cfg):
    inc = increment_for(progression, cfg)
    base = cycle_base_load(baseline, progression, cycle, cfg)
    if week == 1:
        load = base
    elif week in (2, 3):
        load = base + inc
    else:
        load = (base + inc) * cfg["deload_load_factor"]
    return round_to(load, cfg["round_to"])


# --- R3 back-off sets ----------------------------------------------------
def backoff_load(working, cfg):
    return round_to(working * cfg["backoff_factor"], cfg["round_to"])


def has_backoff(exercise, week):
    """No back-off on deload week, and never on a press."""
    if exercise.get("no_backoff"):
        return False
    return bool(exercise.get("backoff")) and week != 4


# --- R4 OHP shoulder ramp ------------------------------------------------
def ohp_prescription(cycle, week, ohp_cycle_offset, cfg):
    eff = max(1, cycle - ohp_cycle_offset)
    sets = min(eff + 2, 5)
    load = 95.0 + max(0, eff - 3) * 2.5
    if week == 4:
        load = round_to(load * cfg["deload_load_factor"], cfg["round_to"])
    return {"sets": sets, "reps": 5, "load": load}


# --- R5 pull-ups ---------------------------------------------------------
def pullup_total(cycle, week, pu):
    if week == 4:
        return None  # max retest week
    base = pu["cycle_1_base_total"] + pu["per_cycle_increase"] * (cycle - 1)
    return base + (week - 1)


def distribute(total, ratios):
    """Split total across len(ratios) sets, descending, summing exactly."""
    s = [round_half_up(total * r) for r in ratios]
    diff = total - sum(s)
    i = len(s) - 1
    while diff > 0:
        s[i] += 1
        diff -= 1
        i = (i - 1) % len(s)
    while diff < 0:
        if s[i] > 1:
            s[i] -= 1
            diff += 1
        i = (i - 1) % len(s)
    s.sort(reverse=True)
    return s


# --- R6 accessory volume -------------------------------------------------
def accessory_sets(exercise, week, cfg):
    s = exercise.get("sets") or 0
    if week == 3 and exercise.get("week3_extra_set"):
        s += cfg.get("week3_accessory_extra_sets", 1)
    if week == 4 and not exercise.get("protected"):
        s = max(1, round_half_up(s * cfg["deload_volume_factor"]))
    return s


# --- R7 rope and fartlek (progress by cycle, not week) -------------------
def rope_interval(cycle, week, rope):
    if week == 4:
        return rope["deload_week_interval"]
    by = rope["interval_by_cycle"]
    return by.get(cycle, by["default"])


def fartlek(cycle, week, f):
    if week == 4:
        return {"pickups": 0, "pickup_seconds": 0, "placement": None}
    base = min(5 + cycle, 8)
    secs = f["pickup_seconds_by_cycle"].get(
        cycle, f["pickup_seconds_by_cycle"]["default"])
    return {
        "pickups": base + (week - 1),
        "pickup_seconds": secs,
        "placement": "saturday" if week_type(cycle, week) == "A" else "thursday",
    }


# --- R8 landings ---------------------------------------------------------
def landing_count(pairs):
    """pairs: iterable of (exercise_dict, resolved_sets)."""
    total = 0
    for ex, sets in pairs:
        per = ex.get("landings_per_rep", 0)
        if per and isinstance(ex.get("reps"), int):
            total += sets * ex["reps"] * per
    return total


def is_hard_cns_day(weekday, wtype, program):
    g = program["guardrails"]
    if weekday in g.get("hard_cns_days", []):
        return True
    if weekday == "saturday":
        return wtype == "A"
    return False
