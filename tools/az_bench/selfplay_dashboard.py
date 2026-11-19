#!/usr/bin/env python3
"""Live dashboard page for a stage 1 self-play run: reads <out-dir>/metrics.jsonl (selfplay.py) and writes one
self-contained HTML page (inline SVG charts, light and dark theme) to publish as an artifact.

usage: selfplay_dashboard.py OUT_DIR PAGE.html [--title "Stage 1 self-play"] [--started "2026-11-17 10:30 CET"]
"""

import argparse
import html
import json
import os
import time


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass   # a line being written
    return rows


def smooth(xs, k):
    """Mean of the last k non-missing values (None where none is available yet)."""
    out, acc, q = [], 0.0, []
    for x in xs:
        if x is None:
            out.append(acc / len(q) if q else None)
            continue
        q.append(x)
        acc += x
        if len(q) > k:
            acc -= q.pop(0)
        out.append(acc / len(q))
    return out


SETTLE_MINUTES = 5


def settling(rows, minutes=SETTLE_MINUTES):
    """True for report windows in the first `minutes` after a (re)start of selfplay.py. A restart drops the runs in
    flight and starts every slot at once; metrics count runs when they finish, so the early deaths come first, then
    the cohort that went the distance, then the early deaths of the refilled slots: the windows swing (e.g. 0 % ->
    32 % -> 5 %) though the net is the checkpoint's. A new process shows as samples_added (per process) going down."""
    out, start, prev = [], None, None
    for r in rows:
        try:
            t = time.mktime(time.strptime(r["time"], "%Y-%m-%d %H:%M:%S"))
        except (KeyError, ValueError):
            out.append(False)
            continue
        added = r.get("samples_added", 0)
        if start is None or (prev is not None and added < prev):
            start = t - r.get("report_s", 30)   # the process started about one report before its first row
        prev = added
        out.append(t - start < minutes * 60)
    return out


def chart(xs, series, w=520, h=230, ymin=None, ymax=None, xlabel="runs", fmt="{:.0f}", yfmt="{:.1f}"):
    """Line chart in SVG: series = [(label, ys, css var)]."""
    pl, pr, pt, pb = 46, 12, 10, 28
    if not xs:
        return '<p class="empty">No data yet.</p>'
    allv = [v for _, ys, _ in series for v in ys if v is not None]
    if not allv:
        return '<p class="empty">No data yet.</p>'
    lo = min(allv) if ymin is None else ymin
    hi = max(allv) if ymax is None else ymax
    if hi <= lo:
        hi = lo + 1
    x0, x1 = xs[0], xs[-1] if xs[-1] > xs[0] else xs[0] + 1

    def X(x):
        return pl + (x - x0) / (x1 - x0) * (w - pl - pr)

    def Y(y):
        return pt + (1 - (y - lo) / (hi - lo)) * (h - pt - pb)

    g = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = Y(v)
        g.append(f'<line x1="{pl}" x2="{w - pr}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        g.append(f'<text x="{pl - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{yfmt.format(v)}</text>')
    for i in range(5):
        xv = x0 + (x1 - x0) * i / 4
        g.append(f'<text x="{X(xv):.1f}" y="{h - 8}" text-anchor="middle" class="tick">{fmt.format(xv)}</text>')
    for label, ys, color in series:
        pts = [(X(x), Y(y)) for x, y in zip(xs, ys) if y is not None]
        if not pts:
            continue
        d = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
        g.append(f'<polyline points="{d}" fill="none" stroke="var({color})" stroke-width="2" stroke-linejoin="round"/>')
        ex, ey = pts[-1]
        g.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="var({color})"/>')
    g.append("</svg>")
    if len(series) > 1:
        g.append('<div class="legend">' + "".join(
            f'<span><i style="background:var({c})"></i>{html.escape(l)}</span>' for l, _, c in series) + "</div>")
    return "".join(g)


def bars(hist, w=1000, h=230):
    pl, pr, pt, pb = 46, 12, 10, 28
    if not hist:
        return '<p class="empty">No finished runs in the last window.</p>'
    floors = list(range(1, 57))
    vals = [hist.get(str(f), hist.get(f, 0)) for f in floors]
    mx = max(vals) or 1
    bw = (w - pl - pr) / len(floors)
    g = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for i in range(5):
        v = mx * i / 4
        y = pt + (1 - v / mx) * (h - pt - pb)
        g.append(f'<line x1="{pl}" x2="{w - pr}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        g.append(f'<text x="{pl - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{v:.0f}</text>')
    for f, v in zip(floors, vals):
        x = pl + (f - 1) * bw
        bh = v / mx * (h - pt - pb)
        boss = f in (16, 33, 50, 55)
        g.append(f'<rect x="{x + 1:.1f}" y="{h - pb - bh:.1f}" width="{max(1, bw - 2):.1f}" height="{bh:.1f}" '
                 f'fill="var({"--boss" if boss else "--accent"})"/>')
    for f in (1, 6, 16, 33, 50, 55):
        g.append(f'<text x="{pl + (f - 0.5) * bw:.1f}" y="{h - 8}" text-anchor="middle" class="tick">{f}</text>')
    g.append("</svg>")
    return "".join(g)


def asc_summary(rows):
    """Per-ascension totals of the curriculum phase from the report windows. A window reports only the ascension
    current at report time, so the few runs still in flight at a step-up (finishing at the old ascension) are missing
    here; they are only in the driver's totals (runs_done_asc)."""
    out = {}
    for r in rows:
        a = r.get("ascension")
        if a is None or "asc_runs_window" not in r:
            continue
        e = out.setdefault(a, {"runs": 0, "wins": 0, "floors": 0.0, "first": r["time"], "last": r["time"],
                               "first_runs": r["runs_done"], "rolling": 0.0, "rolling_runs": 0})
        n = r["asc_runs_window"]
        e["runs"] += n
        e["wins"] += round(r.get("asc_win_rate_window", 0) * n)
        e["floors"] += r.get("asc_mean_floor_window", 0) * n
        e["last"] = r["time"]
        e["rolling"] = r.get("asc_win_rate_rolling", 0)
        e["rolling_runs"] = r.get("asc_rolling_runs", 0)
    return out


def hours_between(a, b):
    try:
        f = "%Y-%m-%d %H:%M:%S"
        return (time.mktime(time.strptime(b, f)) - time.mktime(time.strptime(a, f))) / 3600
    except ValueError:
        return 0.0


def ascension_panel(rows, last, target=0.10, need=10000):
    summ = asc_summary(rows)
    cur = last.get("ascension", 20)
    e = summ.get(cur, {})
    rate = e.get("rolling", 0.0)
    rr = e.get("rolling_runs", 0)
    pct = min(100.0, 100 * rate / target)
    fill = min(100.0, 100 * rr / need)
    cur_floor = None
    for r in reversed(rows):
        if r.get("ascension") == cur and r.get("asc_runs_window"):
            cur_floor = r["asc_mean_floor_window"]
            break
    steps = []
    for a in range(21):
        cls = "done" if a < cur else "cur" if a == cur else "todo"
        steps.append(f'<span class="step {cls}" title="A{a}">{a}</span>')
    trs = []
    for a in sorted(summ):
        x = summ[a]
        end = summ[a + 1]["first"] if a + 1 in summ else last.get("time", x["last"])
        state = "current" if a == cur else "passed" if a < cur else ""
        trs.append(f'<tr class="{state}"><td>A{a}{" (now)" if a == cur else ""}</td><td>{x["first"][5:16]}</td>'
                   f'<td>{hours_between(x["first"], end):.1f}</td><td>{x["runs"]:,}</td><td>{x["wins"]:,}</td>'
                   f'<td>{100 * x["wins"] / max(1, x["runs"]):.2f}</td><td>{100 * x["rolling"]:.2f}</td>'
                   f'<td>{x["floors"] / max(1, x["runs"]):.1f}</td></tr>')
    floor_txt = f"{cur_floor:.1f}" if cur_floor is not None else "-"
    return f"""<section class="ascbox"><h2>Ascension now: A{cur}</h2>
<div class="ladder">{"".join(steps)}</div>
<div class="tiles">
<div class="tile"><div class="k">Heart kills at A{cur} (last {rr:,} runs)</div><div class="v">{100 * rate:.2f} %</div>
<div class="bar"><i style="width:{pct:.1f}%"></i></div><div class="n">step up at 10 % ({pct:.0f} % of the way)</div></div>
<div class="tile"><div class="k">Runs at A{cur}</div><div class="v">{e.get("runs", 0):,}</div>
<div class="bar"><i style="width:{fill:.1f}%"></i></div><div class="n">window fills at {need:,} runs</div></div>
<div class="tile"><div class="k">Mean floor at A{cur}</div><div class="v">{floor_txt}</div><div class="n">last window, Heart = 55</div></div>
<div class="tile"><div class="k">Time at A{cur}</div><div class="v">{hours_between(e.get("first", last.get("time", "")), last.get("time", "")):.1f} h</div>
<div class="n">since {html.escape(e.get("first", "-"))}</div></div>
</div>
<div class="scroll"><table><tr><th>ascension</th><th>reached</th><th>hours</th><th>runs</th><th>Heart kills</th><th>kill %</th><th>last 10k %</th><th>mean floor</th></tr>{"".join(trs)}</table></div>
</section>"""


HEART_HP_KEYS = tuple(f"heart_hp_{b:02d}" for b in range(16))
PROGRESS_KEYS = ("runs", "ruby", "emerald", "sapphire", "all_keys", "campfires", "recall_offered", "rest", "smith",
                 "recall", "other_campfire", "elites", "burning_elites", "act4", "heart", "keyless_victories",
                 "heart_hp_sum", "heart_entry_hp_sum", "heart_turns_sum") + HEART_HP_KEYS


def heart_panel(rows, cur, recent=20):
    """Heart fights: the Heart's HP left at the fight's end (50-HP bins, 0 = killed), lowest ever, means. Empty before
    the counters existed (selfplay.py with heart_hp_* in progress_window)."""
    if not any("heart_hp_00" in e for r in rows for e in (r.get("progress_window") or {}).values()):
        return ""
    tot = progress_sum(rows).get(cur) or {}
    now = progress_sum(rows[-recent:]).get(cur) or {}
    low = next((r["heart_hp_min"] for r in reversed(rows) if r.get("heart_hp_min") is not None), None)

    def svg(t):
        vals = [t.get(k, 0) for k in HEART_HP_KEYS]
        mx = max(vals) or 1
        w, h, pl, pr, pt, pb = 1000, 200, 46, 12, 10, 28
        bw = (w - pl - pr) / len(vals)
        g = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
        for i in range(5):
            v = mx * i / 4
            y = pt + (1 - v / mx) * (h - pt - pb)
            g.append(f'<line x1="{pl}" x2="{w - pr}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
            g.append(f'<text x="{pl - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{v:.0f}</text>')
        for b, v in enumerate(vals):
            bh = v / mx * (h - pt - pb)
            g.append(f'<rect x="{pl + b * bw + 1:.1f}" y="{h - pb - bh:.1f}" width="{max(1, bw - 2):.1f}" '
                     f'height="{bh:.1f}" fill="var({"--good" if b == 0 else "--boss"})"/>')
            if b % 2 == 0:
                g.append(f'<text x="{pl + (b + 0.5) * bw:.1f}" y="{h - 8}" text-anchor="middle" class="tick">{50 * b}</text>')
        g.append("</svg>")
        return "".join(g)

    def mean(t, k):
        return f'{t[k] / t["heart"]:.0f}' if t.get("heart") else "-"

    tiles = (f'<div class="tiles"><div class="tile"><div class="k">Heart fights (A{cur})</div>'
             f'<div class="v">{tot.get("heart", 0):,}</div><div class="n">last ~{recent} windows: {now.get("heart", 0):,}</div></div>'
             f'<div class="tile"><div class="k">Lowest Heart HP left</div><div class="v">{"-" if low is None else low}</div>'
             f'<div class="n">of 750; 0 = kill</div></div>'
             f'<div class="tile"><div class="k">Mean Heart HP left</div><div class="v">{mean(tot, "heart_hp_sum")}</div>'
             f'<div class="n">recent {mean(now, "heart_hp_sum")}</div></div>'
             f'<div class="tile"><div class="k">Player HP entering</div><div class="v">{mean(tot, "heart_entry_hp_sum")}</div>'
             f'<div class="n">mean turns in the fight {mean(tot, "heart_turns_sum")}</div></div></div>')
    return f"""<section class="ascbox"><h2>Heart fights: Heart HP left at the end</h2>
{tiles}
{svg(tot)}
<p class="rule">Heart HP left when its fight ended, in 50-HP bins (x = bin start; green bin 0-49 includes kills at 0),
all Heart fights at A{cur} since the counters exist. The Heart takes at most 300 damage per turn (Invincible).</p></section>"""


def progress_sum(rows):
    """Run progress counters (selfplay.py progress_window) summed per ascension over the given report windows."""
    out = {}
    for r in rows:
        for a, e in (r.get("progress_window") or {}).items():
            t = out.setdefault(int(a), dict.fromkeys(PROGRESS_KEYS, 0))
            for k in PROGRESS_KEYS:
                t[k] += e.get(k, 0)
    return out


def pct(a, b):
    return f"{100 * a / b:.1f}" if b else "-"


def progress_panel(rows, cur, recent=20):
    """Keys, Recall, elites, Act 4 and Heart per ascension (finished runs). Empty before the counters existed."""
    if not any(r.get("progress_window") for r in rows):
        return ""
    tot = progress_sum(rows)
    now = progress_sum(rows[-recent:]).get(cur)

    def tile(kname, v, note=""):
        return f'<div class="tile"><div class="k">{kname}</div><div class="v">{v}</div><div class="n">{note}</div></div>'

    tiles = ""
    if now and now["runs"]:
        n = now["runs"]
        tiles = '<div class="tiles">' + "".join([
            tile(f"All 3 keys (A{cur})", f'{pct(now["all_keys"], n)} %',
                 f'Ruby {pct(now["ruby"], n)} / Emerald {pct(now["emerald"], n)} / Sapphire {pct(now["sapphire"], n)} %'),
            tile("Recall when offered", f'{pct(now["recall"], now["recall_offered"])} %',
                 f'{now["recall"]:,} of {now["recall_offered"]:,} campfires; rest {pct(now["rest"], now["campfires"])} %, '
                 f'smith {pct(now["smith"], now["campfires"])} %'),
            tile("Elites per run", f'{now["elites"] / n:.2f}',
                 f'burning elite fought in {pct(now["burning_elites"], n)} % of runs'),
            tile("Act 4 reached", f'{pct(now["act4"], n)} %',
                 f'Heart fought {pct(now["heart"], n)} %; keyless Act 3 end {pct(now["keyless_victories"], n)} %'),
        ]) + "</div>"
    trs = []
    for a in sorted(tot):
        x = tot[a]
        n = x["runs"]
        trs.append(f'<tr class="{"current" if a == cur else ""}"><td>A{a}</td><td>{n:,}</td><td>{pct(x["ruby"], n)}</td>'
                   f'<td>{pct(x["emerald"], n)}</td><td>{pct(x["sapphire"], n)}</td><td>{pct(x["all_keys"], n)}</td>'
                   f'<td>{pct(x["recall"], x["recall_offered"])}</td><td>{pct(x["rest"], x["campfires"])}</td>'
                   f'<td>{pct(x["smith"], x["campfires"])}</td><td>{x["elites"] / max(1, n):.2f}</td>'
                   f'<td>{pct(x["burning_elites"], n)}</td><td>{pct(x["act4"], n)}</td><td>{pct(x["heart"], n)}</td>'
                   f'<td>{pct(x["keyless_victories"], n)}</td></tr>')
    xs, keys_s, act4_s = [], [], []
    for r in rows:
        e = (r.get("progress_window") or {}).get(str(r.get("ascension", cur)))
        if not e or not e.get("runs"):
            continue
        xs.append(r["runs_done"])
        keys_s.append(100 * e["all_keys"] / e["runs"])
        act4_s.append(100 * e["act4"] / e["runs"])
    ch = chart(xs, [("all 3 keys % (smoothed)", smooth(keys_s, 10), "--good"),
                    ("Act 4 reached % (smoothed)", smooth(act4_s, 10), "--boss")], ymin=0, yfmt="{:.1f}") if xs else ""
    # Elites per finished run over the whole run (all ascensions of each window summed); windows without the
    # counters or without finished runs are gaps (None).
    ex, el_s, bel_s = [], [], []
    for r in rows:
        es = (r.get("progress_window") or {}).values()
        n = sum(e.get("runs", 0) for e in es)
        ex.append(r["runs_done"])
        el_s.append(sum(e.get("elites", 0) for e in es) / n if n else None)
        bel_s.append(sum(e.get("burning_elites", 0) for e in es) / n if n else None)
    def gap(v):   # smoothed, but missing where the window has no data
        return [m if x is not None else None for m, x in zip(smooth(v, 10), v)]
    if any(v is not None for v in el_s):
        ch += ('<h3>Elites per run (all ascensions)</h3>' +
               chart(ex, [("elite fights per run (smoothed)", gap(el_s), "--accent"),
                          ("burning elite per run (smoothed)", gap(bel_s), "--accent2")], ymin=0, yfmt="{:.2f}"))
    # Relics held and deck size at the run's end (selfplay.py relics_per_run / deck_per_run; rows from before the
    # counters existed carry none and are left out).
    rx = [r["runs_done"] for r in rows if "relics_per_run" in r]
    if rx:
        rr = [r["relics_per_run"] for r in rows if "relics_per_run" in r]
        dd = [r["deck_per_run"] for r in rows if "relics_per_run" in r]
        ch += (f'<h3>Relics and deck size at the run\'s end (per run, from run {rx[0]:,})</h3>' +
               chart(rx, [("relics (smoothed)", gap(rr), "--good"), ("cards in deck (smoothed)", gap(dd), "--boss")],
                     ymin=0, yfmt="{:.0f}"))
    # Relic sources and losses per run (selfplay.py economy_per_run, 2026-11-19; rows without it are left out).
    ox = [r["runs_done"] for r in rows if r.get("economy_per_run")]
    if ox:
        ec = [r["economy_per_run"] for r in rows if r.get("economy_per_run")]
        def col(*ks):
            return [sum(e[k] for k in ks) for e in ec]
        ch += (f'<h3>Relic sources and relics left behind (per run, from run {ox[0]:,})</h3>' +
               chart(ox, [("relics not picked up (left + chests not opened)",
                           gap(col("relics_left_elite", "relics_left_chest", "relics_left_other", "chests_skipped")), "--fg"),
                          ("elite relics taken", gap(col("relics_taken_elite")), "--good"),
                          ("elite relics left", gap(col("relics_left_elite")), "--accent2"),
                          ("chests not opened", gap(col("chests_skipped")), "--boss"),
                          ("chest + other relics left", gap(col("relics_left_chest", "relics_left_other")), "--muted"),
                          ("shop relics bought", gap(col("shop_relics")), "--accent")], ymin=0, yfmt="{:.1f}") +
               '<p class="rule">Not picked up: relics on a reward screen when it was left, plus treasure chests left '
               'unopened (one relic each). The chest relic given up for the Sapphire key is not counted '
               '(sapphire_relic_forfeits in economy_per_run).</p>')
    return f"""<section class="ascbox"><h2>Keys, Recall, elites, Act 4 (finished runs)</h2>
{tiles}
<p class="rule">Tiles: current ascension, last ~{recent} windows. Keys count when held at the run's end. Recall % is over
campfires where Recall was legal; rest / smith % over all campfire choices. Elites: elite-room fights started (the
burning elite gives the Emerald key). A run without all three keys ends after the Act 3 boss (floor 51).</p>
{ch}
<div class="scroll"><table><tr><th>asc</th><th>runs</th><th>Ruby %</th><th>Emerald %</th><th>Sapphire %</th><th>all 3 %</th>
<th>Recall % offered</th><th>rest %</th><th>smith %</th><th>elites/run</th><th>burning elite %</th><th>Act 4 %</th>
<th>Heart %</th><th>keyless end %</th></tr>{"".join(trs)}</table></div>
</section>"""


CSS = """
:root { --bg:#f6f7f9; --panel:#ffffff; --fg:#17202b; --muted:#5d6b7a; --line:#dde3ea; --accent:#2f6fdb;
  --accent2:#d9822b; --good:#1f8a4c; --boss:#9b59b6;
  --display:"Space Grotesk", system-ui, sans-serif; --body:Inter, system-ui, sans-serif;
  --mono:"JetBrains Mono", ui-monospace, monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0f141a; --panel:#161d25; --fg:#e6ebf1;
  --muted:#93a1b0; --line:#28323d; --accent:#6aa0ff; --accent2:#f0a35a; --good:#4cc77f; --boss:#c08ae0; color-scheme:dark } }
:root[data-theme="dark"] { --bg:#0f141a; --panel:#161d25; --fg:#e6ebf1; --muted:#93a1b0; --line:#28323d; --accent:#6aa0ff;
  --accent2:#f0a35a; --good:#4cc77f; --boss:#c08ae0; color-scheme:dark }
body { background:var(--bg); color:var(--fg); font-family:var(--body); line-height:1.45;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }
main { max-width:1060px; margin:0 auto; padding-block:24px 40px; display:grid; gap:20px; }
h1 { font-family:var(--display); font-size:1.7rem; margin:0; text-wrap:balance; }
h2 { font-family:var(--display); font-size:1.05rem; margin:0 0 8px; }
.sub { color:var(--muted); margin:4px 0 0; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; }
.tile { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }
.tile .k { font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
.tile .v { font-family:var(--display); font-size:1.5rem; font-variant-numeric:tabular-nums; }
.tile .n { font-size:.78rem; color:var(--muted); }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 440px), 1fr)); gap:16px; }
section { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; min-width:0; }
.chart { width:100%; height:auto; display:block; }
.chart .grid { stroke:var(--line); stroke-width:1; }
.chart .tick { fill:var(--muted); font-size:12px; font-family:var(--mono); }
.legend { display:flex; gap:14px; flex-wrap:wrap; font-size:.8rem; color:var(--muted); margin-top:6px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:-1px; }
.pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:600;
  border:1px solid var(--line); }
.pill.live { color:var(--good); border-color:var(--good); }
.pill.stale { color:var(--accent2); border-color:var(--accent2); }
.rule { font-size:.86rem; color:var(--muted); }
.empty { color:var(--muted); }
table { border-collapse:collapse; font-size:.85rem; font-variant-numeric:tabular-nums; width:100%; }
td, th { padding:4px 8px; border-bottom:1px solid var(--line); text-align:right; }
th:first-child, td:first-child { text-align:left; }
.scroll { overflow-x:auto; }
.ascbox { display:grid; gap:12px; }
.ladder { display:flex; flex-wrap:wrap; gap:4px; }
.step { min-width:26px; text-align:center; padding:3px 0; border-radius:4px; font-family:var(--mono); font-size:.78rem;
  border:1px solid var(--line); color:var(--muted); }
.step.done { background:var(--good); border-color:var(--good); color:var(--panel); }
.step.cur { background:var(--boss); border-color:var(--boss); color:var(--panel); font-weight:700; }
.bar { position:relative; height:8px; border-radius:4px; background:var(--line); margin:6px 0 4px; overflow:hidden; }
.bar i { position:absolute; inset:0 auto 0 0; background:var(--good); border-radius:4px; }
tr.current td { font-weight:600; }
"""


RULE_MAIN = ("GO if the self-play win rate reaches 10 % by 1M runs, or the first wins appear by 500k runs while the mean "
             "floor still rises. STOP if there is no win by 1M runs and the mean floor gained less than 2 floors over the "
             "last 500k runs. Otherwise inconclusive.")
RULE_VARIANT = ("Continuation (runs 1M-2M, pick-rate exploration on, same net and seeds onward): GO if the self-play win rate "
                "reaches 10 % by 2M runs or the first wins appear while the mean floor still rises; STOP if there is no "
                "win by 2M runs and the mean floor gained less than 2 floors over runs 1M-2M; otherwise inconclusive. "
                "Forced exploration picks lower the self-play win rate a little (Amber Eye: ~3 pp on 0.2 % of moves).")


RULE_CURRICULUM = ("Curriculum (Philipp, 2026-11-17): from the 1M-run net, restart at A0; a win is always a Heart kill. "
                   "Once the Heart-kill rate at the current ascension reaches 10 % over its last 10,000 finished runs, "
                   "the next runs start one ascension higher, up to A20. Pick-rate exploration stays on.")


def page(rows, title, started, subtitle=""):
    last = rows[-1] if rows else {}
    runs = [r["runs_done"] for r in rows]
    # Continuation with pick-rate exploration (rows carry its counters).
    variant = any("forced_picks" in r for r in rows)
    curriculum = any(r.get("ascension", 20) < 20 for r in rows)
    if curriculum:
        # Floors and win rates at A0.. are not comparable with the earlier A20 phases: show the curriculum phase only.
        start = next(i for i, r in enumerate(rows) if r.get("ascension", 20) < 20)
        rows = rows[start:]
        last = rows[-1]
    # Windows right after a restart are biased by which runs finish first (settling): left out of the floor and
    # win-rate curves only (totals, histograms and the panels keep every row).
    mask = settling(rows)
    n_settle = sum(mask)
    asc_line = [r.get("ascension") for r in rows]
    asc_roll = [100 * r["asc_win_rate_rolling"] if "asc_win_rate_rolling" in r else None for r in rows]
    floor = [r["mean_floor_window"] if r.get("runs_window") and not m else None for r, m in zip(rows, mask)]
    win = [100 * r["win_rate_window"] if r.get("runs_window") and not m else None for r, m in zip(rows, mask)]
    k = 10
    floor_s = smooth(floor, k)
    win_s = smooth(win, k)
    pos = [r["positions_per_s"] / 1000 for r in rows]
    lp = [(r["loss"] or {}).get("policy") if r.get("loss") else None for r in rows]
    lo = [(r["loss"] or {}).get("outcome") if r.get("loss") else None for r in rows]
    lh = [(r["loss"] or {}).get("hp") if r.get("loss") else None for r in rows]
    # last ~10 windows' death floors
    hist = {}
    for r in rows[-20:]:
        for f, n in (r.get("death_floors_window") or {}).items():
            hist[str(f)] = hist.get(str(f), 0) + n
    age = None
    try:
        age = time.time() - time.mktime(time.strptime(last["time"], "%Y-%m-%d %H:%M:%S"))
    except (KeyError, ValueError):
        pass
    live = age is not None and age < 900
    status = f'<span class="pill {"live" if live else "stale"}">{"running" if live else "no update for " + str(int((age or 0) // 60)) + " min"}</span>'
    recent_floor = (floor_s[-1] if floor_s else None) or 0
    recent_win = (win_s[-1] if win_s else None) or 0

    def tile(kname, v, note=""):
        return f'<div class="tile"><div class="k">{kname}</div><div class="v">{v}</div><div class="n">{note}</div></div>'

    tiles = "".join([
        tile("Runs played", f'{last.get("runs_done", 0):,}', "in total, all phases" if curriculum else "goal: 2M (continuation)" if variant else "goal: 1M (decision)"),
        tile("Mean floor", f"{recent_floor:.1f}", "last ~5 min, of 55"),
        tile("Heart kills" if curriculum else "Win rate", f"{recent_win:.2f} %", f'{last.get("wins_total", 0):,} wins total'),
        tile("Positions/s", f'{last.get("positions_per_s", 0) / 1000:.0f}k', f'{last.get("moves_per_s", 0):,} moves/s'),
        tile("Train steps", f'{last.get("train_steps", 0):,}', f'{last.get("samples_added", 0):,} samples'),
        tile("Hours", f'{last.get("hours", 0):.1f}', f"started {html.escape(started)}" if started else ""),
    ] + ([
        tile("Memory", f'{last["rss_gb"]:.1f} GB' if last.get("rss_gb") is not None else "-",
             f'{last.get("samples_pending", 0):,} samples pending' if "samples_pending" in last else "process RSS"),
    ] if "rss_gb" in last or "samples_pending" in last else []) + ([
        tile("Forced picks", f'{last.get("forced_picks", 0):,}',
             f'{last.get("explore_roots", 0):,} of {last.get("ooc_roots", 0):,} OOC roots under target'),
    ] if variant else []) + ([
        tile("Forced key moves", f'{sum(last["force_keys"].get(k, 0) for k in ("sapphire", "ruby", "emerald")):,}',
             f'Sapphire {last["force_keys"].get("sapphire", 0):,} / Ruby {last["force_keys"].get("ruby", 0):,} / '
             f'Emerald {last["force_keys"].get("emerald", 0):,}; routes narrowed {last["force_keys"].get("route_masked", 0):,}; '
             + ("on (until the first step-up)" if last["force_keys"].get("active") else "off since the first step-up")),
    ] if last.get("force_keys") else []))
    sub = subtitle or ("0.44M AmberNet warm-started from the 1M-run A20 net, Ironclad ascension curriculum from A0, self-play on the PC "
           "(RTX 3060 Ti). Charts show the curriculum phase only." if curriculum else
           "0.44M AmberNet from scratch, A20 Ironclad, self-play on the PC (RTX 3060 Ti).")
    if subtitle and curriculum:
        sub += " Charts show the curriculum phase only."
    if n_settle:
        sub += (f" Floor and win-rate curves leave out the report windows in the first {SETTLE_MINUTES} min after each "
                f"restart ({n_settle}): "
                "runs finishing then are not a fair sample (short runs finish first).")
    table_rows = "".join(
        f'<tr><td>{html.escape(r["time"])}</td><td>{r["runs_done"]:,}</td><td>{r["mean_floor_window"]:.1f}</td>'
        f'<td>{100 * r["win_rate_window"]:.2f}</td><td>{r["positions_per_s"]:,}</td><td>{r["train_steps"]:,}</td>'
        f'<td>{r.get("stalls", 0)}</td>' + (f'<td>A{r.get("ascension", 20)}</td>' if curriculum else "") + '</tr>'
        for r in rows[-12:][::-1])
    body = f"""
<main>
<header>
<h1>{html.escape(title)} {status}</h1>
<p class="sub">{html.escape(sub)} Updated {html.escape(last.get("time", "-"))} (PC time).</p>
</header>
{ascension_panel(rows, last) if curriculum else ""}
<div class="tiles">{tiles}</div>
{progress_panel(rows, last.get("ascension", 20))}
{heart_panel(rows, last.get("ascension", 20))}
<div class="grid2">
<section><h2>Mean final floor per window</h2>{chart(runs, [("mean floor (smoothed)", floor_s, "--accent")], ymin=0)}</section>
<section><h2>{"Heart-kill rate, all ascensions (%)" if curriculum else "Self-play win rate (%)"}</h2>{chart(runs, [("win rate (smoothed)", win_s, "--good")], ymin=0, yfmt="{:.2f}")}</section>
<section><h2>Training losses</h2>{chart(runs, [("policy", lp, "--accent"), ("outcome", lo, "--accent2"), ("HP", lh, "--boss")], yfmt="{:.2f}")}</section>
{f'<section><h2>Curriculum: ascension and Heart-kill rate (%, last 10k runs at it)</h2>{chart(runs, [("ascension", asc_line, "--boss"), ("Heart kills % (rolling)", asc_roll, "--good")], ymin=0, yfmt="{:.0f}")}</section>' if curriculum else ""}
<section><h2>Positions per second (thousands)</h2>{chart(runs, [("positions/s", pos, "--accent2")], ymin=0, yfmt="{:.0f}")}</section>
{f'<section><h2>Memory: process RSS (GB) and samples pending (millions)</h2>{chart(runs, [("RSS GB", [r.get("rss_gb") for r in rows], "--boss"), ("pending (M)", [r["samples_pending"] / 1e6 if "samples_pending" in r else None for r in rows], "--accent")], ymin=0, yfmt="{:.1f}")}</section>' if any(r.get("rss_gb") is not None for r in rows) else ""}
</div>
<section><h2>Where runs end (death floor, last ~10 min)</h2>{bars(hist)}
<p class="rule">Purple: boss floors (16, 33, 50) and the Heart (55).</p></section>
<section><h2>Decision rule</h2><p class="rule">{RULE_CURRICULUM if curriculum else RULE_VARIANT if variant else RULE_MAIN}</p></section>
<section><h2>Latest windows</h2><div class="scroll"><table><tr><th>time</th><th>runs</th><th>mean floor</th><th>win %</th><th>pos/s</th><th>train steps</th><th>stalls</th>{"<th>asc</th>" if curriculum else ""}</tr>{table_rows}</table></div></section>
</main>"""
    head = (f'<title>{html.escape(title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@500;600&family=JetBrains+Mono&display=swap">\n'
            f"<style>{CSS}</style>\n")
    return head + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("page")
    ap.add_argument("--title", default="Stage 1 self-play")
    ap.add_argument("--started", default="")
    ap.add_argument("--subtitle", default="", help="replaces the description line under the title")
    a = ap.parse_args()
    rows = load(os.path.join(a.out_dir, "metrics.jsonl"))
    tmp = a.page + ".tmp"
    with open(tmp, "w") as f:
        f.write(page(rows, a.title, a.started, a.subtitle))
    os.replace(tmp, a.page)


if __name__ == "__main__":
    main()
