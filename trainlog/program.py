import yaml

from trainlog import config

_cache = None
_REQUIRED = ("meta", "config", "guardrails", "anchor", "days",
             "fartlek", "ohp_ramp", "pullups", "test_battery")


def load_program():
    global _cache
    if _cache is not None:
        return _cache
    with open(config.PROGRAM_YAML, "r", encoding="utf-8") as f:
        p = yaml.safe_load(f)
    for k in _REQUIRED:
        if k not in p:
            raise ValueError(f"program.yaml missing top-level key: {k}")
    for wd in config.WEEKDAYS:
        if wd not in p["days"]:
            raise ValueError(f"program.yaml missing day: {wd}")
    for wd, day in p["days"].items():
        for block in (day, day.get("week_a") or {}, day.get("week_b") or {}):
            seen = set()
            for ex in block.get("exercises", []) or []:
                for f in ("id", "name", "kind"):
                    if f not in ex:
                        raise ValueError(f"{wd}: exercise missing '{f}': {ex}")
                if ex["id"] in seen:
                    raise ValueError(f"{wd}: duplicate exercise id {ex['id']}")
                seen.add(ex["id"])
    _cache = p
    return p


def anchor_item(key):
    for item in load_program()["anchor"]:
        if item["key"] == key:
            return item
    return None


def day_exercises(weekday, wtype, cycle):
    """Resolved exercise list for a weekday, honouring week_a/week_b and addons."""
    day = load_program()["days"][weekday]
    block = day
    if wtype == "A" and day.get("week_a"):
        block = day["week_a"]
    elif wtype == "B" and day.get("week_b"):
        block = day["week_b"]
    exercises = list(block.get("exercises", []) or [])
    addon = day.get("cycle3_plus_addon")
    if addon and cycle >= 3:
        a = dict(addon)
        a.setdefault("kind", "cardio")
        a["optional"] = True
        exercises.append(a)
    return exercises, block.get("note") or day.get("note")
