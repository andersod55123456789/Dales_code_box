import html

PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 16, 34


def _scale(v, vmin, vmax, lo, hi):
    if vmax == vmin:
        return (lo + hi) / 2
    return lo + (v - vmin) * (hi - lo) / (vmax - vmin)


def line_chart(series, width=820, height=260, y_min=None, y_max=None,
               y_label="", x_labels=None, y_fmt="{:.0f}", sparkline=False):
    ys = [p["y"] for s in series for p in s["points"] if p.get("y") is not None]
    if not ys:
        return '<p class="empty">No data yet.</p>'
    lo = y_min if y_min is not None else min(ys)
    hi = y_max if y_max is not None else max(ys)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    n = max(len(s["points"]) for s in series)
    pl = 4 if sparkline else PAD_L
    pb = 4 if sparkline else PAD_B
    pt = 4 if sparkline else PAD_T
    x0, x1 = pl, width - (4 if sparkline else PAD_R)
    y0, y1 = height - pb, pt
    o = [f'<svg class="chart{" spark" if sparkline else ""}" '
         f'viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
         f'role="img" aria-label="{html.escape(y_label)}">']
    if not sparkline:
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            y = _scale(v, lo, hi, y0, y1)
            o.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                     f'stroke="var(--gridline)" stroke-width="1"/>')
            o.append(f'<text x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'class="tick">{y_fmt.format(v)}</text>')
        o.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" '
                 f'stroke="var(--baseline)" stroke-width="1"/>')
        if x_labels:
            step = max(1, len(x_labels) // 8)
            for i in range(0, len(x_labels), step):
                x = _scale(i, 0, max(1, n - 1), x0, x1)
                o.append(f'<text x="{x:.1f}" y="{height - 12}" '
                         f'text-anchor="middle" class="tick">'
                         f'{html.escape(str(x_labels[i]))}</text>')
    for s in series:
        pts = [p for p in s["points"] if p.get("y") is not None]
        if not pts:
            continue
        co = [(_scale(p["x"], 0, max(1, n - 1), x0, x1),
               _scale(p["y"], lo, hi, y0, y1)) for p in pts]
        o.append('<polyline points="%s" fill="none" stroke="%s" '
                 'stroke-width="2" stroke-linejoin="round" '
                 'stroke-linecap="round"/>'
                 % (" ".join(f"{x:.1f},{y:.1f}" for x, y in co), s["color"]))
        if not sparkline:
            for (x, y), p in zip(co, pts):
                hollow = p.get("hollow")
                fill = "var(--surface)" if hollow else s["color"]
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" '
                         f'fill="{fill}" stroke="{s["color"]}" '
                         f'stroke-width="2"><title>'
                         f'{html.escape(str(p.get("label", "")))}</title></circle>')
    o.append("</svg>")
    return "".join(o)


def bar_chart(bars, width=820, height=200, y_fmt="{:.0f}",
              color="var(--series-1)"):
    vals = [b["value"] for b in bars if b.get("value") is not None]
    if not vals:
        return '<p class="empty">No data yet.</p>'
    hi = max(vals) or 1
    x0, x1 = PAD_L, width - PAD_R
    y0, y1 = height - PAD_B, PAD_T
    slot = (x1 - x0) / max(1, len(bars))
    bw = max(4.0, slot - 2)
    o = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']
    for i in range(5):
        v = hi * i / 4
        y = _scale(v, 0, hi, y0, y1)
        o.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                 f'stroke="var(--gridline)" stroke-width="1"/>')
        o.append(f'<text x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end" '
                 f'class="tick">{y_fmt.format(v)}</text>')
    o.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" '
             f'stroke="var(--baseline)" stroke-width="1"/>')
    step = max(1, len(bars) // 12)
    for i, b in enumerate(bars):
        if b.get("value") is None:
            continue
        x = x0 + i * slot + (slot - bw) / 2
        y = _scale(b["value"], 0, hi, y0, y1)
        o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                 f'height="{max(0.0, y0 - y):.1f}" rx="4" ry="4" '
                 f'fill="{b.get("color") or color}"><title>'
                 f'{html.escape(str(b.get("title", "")))}</title></rect>')
        if i % step == 0:
            o.append(f'<text x="{x + bw / 2:.1f}" y="{height - 12}" '
                     f'text-anchor="middle" class="tick">'
                     f'{html.escape(str(b.get("label", "")))}</text>')
    o.append("</svg>")
    return "".join(o)
