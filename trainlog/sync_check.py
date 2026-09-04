"""Compare program.yaml against the markdown tables in PROGRAM.md.

Reports only - never edits either file, never raises. Rows it cannot parse are
reported under "skipped" so a silent parse failure stays visible.
"""
import re

from trainlog import config
from trainlog.program import load_program

_DAY_HEAD = re.compile(r"^###\s+(\w+day)\b", re.I)
_LOAD = re.compile(r"([\d.]+)\s*lb")
# "5x5", "4×8", "3 x 10-12", "4×10–12"  (en dash or hyphen)
_SETS = re.compile(r"(\d+)\s*[x×]\s*(\d+)(?:\s*[-–]\s*(\d+))?")
_TRACKED = ("monday", "wednesday", "friday")


def _md_tables():
    """{(weekday, lowercase name): {sets, reps_lo, reps_hi, load}}"""
    try:
        with open(config.PROGRAM_MD, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    out, day = {}, None
    for line in text.splitlines():
        head = _DAY_HEAD.match(line.strip())
        if head:
            day = head.group(1).lower()
            continue
        if not line.strip().startswith("|") or day is None:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or set(cells[0]) <= set("-: "):
            continue
        if cells[0].lower() in ("exercise", "item", "#", "metric", "week"):
            continue
        name = cells[0].strip("*").strip()
        blob = " ".join(cells[1:])
        sm = _SETS.search(blob)
        if not sm:
            continue
        lm = _LOAD.search(blob)
        lo = int(sm.group(2))
        out[(day, name.lower())] = {
            "sets": int(sm.group(1)),
            "reps_lo": lo,
            "reps_hi": int(sm.group(3)) if sm.group(3) else lo,
            "load": float(lm.group(1)) if lm else None,
        }
    return out


def run_sync_check():
    md = _md_tables()
    if md is None:
        return {"in_sync": True, "mismatches": [], "skipped": [],
                "note": "PROGRAM.md not readable - check skipped"}
    if not md:
        return {"in_sync": True, "mismatches": [], "skipped": [],
                "note": "no parsable tables found in PROGRAM.md"}

    p = load_program()
    mismatches, skipped = [], []
    for wd in _TRACKED:
        for ex in p["days"][wd].get("exercises", []) or []:
            m = md.get((wd, ex["name"].lower()))
            if not m:
                skipped.append({"exercise": ex["name"], "weekday": wd,
                                "reason": "no matching markdown row"})
                continue
            if isinstance(ex.get("sets"), int) and ex["sets"] != m["sets"]:
                mismatches.append({"exercise": ex["name"], "weekday": wd,
                                   "field": "sets", "yaml": ex["sets"],
                                   "markdown": m["sets"]})
            reps = ex.get("reps")
            if isinstance(reps, int) and not (m["reps_lo"] <= reps <= m["reps_hi"]):
                shown = (str(m["reps_lo"]) if m["reps_lo"] == m["reps_hi"]
                         else f"{m['reps_lo']}-{m['reps_hi']}")
                mismatches.append({"exercise": ex["name"], "weekday": wd,
                                   "field": "reps", "yaml": reps,
                                   "markdown": shown})
            load = ex.get("load")
            if (m["load"] is not None and isinstance(load, (int, float))
                    and float(load) != m["load"]):
                mismatches.append({"exercise": ex["name"], "weekday": wd,
                                   "field": "load", "yaml": load,
                                   "markdown": m["load"]})
    return {"in_sync": not mismatches, "mismatches": mismatches,
            "skipped": skipped}
