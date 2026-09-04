"""Turn report data into ready-to-embed SVG strings."""
from trainlog import reports
from trainlog.svg import bar_chart, line_chart

S1, S2, S3 = "var(--series-1)", "var(--series-2)", "var(--series-3)"


def _wk(t):
    return f"C{t['cycle']}W{t['week']}"


def build(rng="12w"):
    strength = reports.strength_series(rng)
    tonnage = reports.weekly_tonnage(rng)
    wellness = reports.wellness_series(rng)

    lifts = []
    for s in strength:
        pts = [{"x": i, "y": p["top_load"],
                "hollow": p["is_deload"],
                "label": f"{p['date']} C{p['cycle']}W{p['week']} "
                         f"{p['top_load']} lb"
                         + (" (deload)" if p["is_deload"] else "")}
               for i, p in enumerate(s["points"])]
        first = s["points"][0]["top_load"] if s["points"] else None
        last = s["points"][-1]["top_load"] if s["points"] else None
        delta = (last - first) if (first is not None and last is not None) else None
        lifts.append({
            "name": s["name"], "id": s["exercise_id"], "points": s["points"],
            "first": first, "last": last, "delta": delta,
            "pct": (round(100.0 * delta / first, 1)
                    if delta is not None and first else None),
            "svg": line_chart([{"name": s["name"], "color": S1, "points": pts}],
                              height=200, y_label=f"{s['name']} top set load",
                              x_labels=[f"C{p['cycle']}W{p['week']}"
                                        for p in s["points"]]),
        })

    ton_bars = [{"label": _wk(t), "value": t["tonnage"],
                 "color": "var(--status-warning)" if t.get("hot") else S1,
                 "title": f"Cycle {t['cycle']} Week {t['week']} - "
                          f"{t['tonnage']:,.0f} lb"
                          + (" (deload)" if t["is_deload"] else "")}
                for t in tonnage]

    wl_labels = [d["date"][5:] for d in wellness]
    wl = [
        {"name": "sleep quality", "color": S1,
         "points": [{"x": i, "y": d["sleep_quality"],
                     "label": f"{d['date']} sleep {d['sleep_quality']}"}
                    for i, d in enumerate(wellness)]},
        {"name": "energy", "color": S2,
         "points": [{"x": i, "y": d["energy"],
                     "label": f"{d['date']} energy {d['energy']}"}
                    for i, d in enumerate(wellness)]},
        {"name": "soreness", "color": S3,
         "points": [{"x": i, "y": d["soreness"],
                     "label": f"{d['date']} soreness {d['soreness']}"}
                    for i, d in enumerate(wellness)]},
    ]

    sparks = {}
    for m in reports.test_metrics():
        pts = [{"x": i, "y": h["value"]} for i, h in enumerate(m["history"])]
        sparks[m["key"]] = (line_chart(
            [{"name": m["name"], "color": S1, "points": pts}],
            width=120, height=32, sparkline=True) if len(pts) > 1 else "")

    return {
        "lifts": lifts,
        "tonnage_svg": bar_chart(ton_bars, height=180),
        "tonnage_rows": tonnage,
        "wellness_svg": line_chart(wl, height=220, y_min=1, y_max=5,
                                   y_label="Wellness 1-5",
                                   x_labels=wl_labels, y_fmt="{:.0f}"),
        "wellness_legend": [{"name": s["name"], "color": s["color"]} for s in wl],
        "wellness_rows": wellness,
        "sparks": sparks,
    }
