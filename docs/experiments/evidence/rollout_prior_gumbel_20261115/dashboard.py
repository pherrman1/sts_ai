#!/usr/bin/env python3
"""Live training dashboard for stage 1 (plain HTML page, stdlib only; republished as an artifact during the grid).
usage: dashboard.py RUNS_DIR OUT.html
Reads RUNS_DIR/NAME/train.json (finished runs) and RUNS_DIR/NAME.log (epoch lines of a running one)."""
import datetime
import glob
import html
import json
import os
import sys

BASE = {"playout": 2.449, "all": 1.952, "top1": 0.390, "mean": 1.992}   # g7f_E on the same validation rows (R0.json)
ORDER = ["V", "CQP", "CQ30", "CQ10", "CQ30m", "X-Q", "X-SH", "X-QSH", "S1", "X-B"]
LABEL = {"V": "Visit-Shares", "CQP": "cq:paper (≈ Argmax)", "CQ30": "cq:30 backed", "CQ10": "cq:10 backed",
         "CQ30m": "cq:30 mean", "X-Q": "+ Q-Kopf", "X-SH": "+ Kurzhorizont-Kopf", "X-QSH": "+ beide Köpfe",
         "S1": "Seed 1", "X-B": "Boss-Finetune"}
EPOCHS = {"X-B": 3}
PALETTE = ["#3b6fd8", "#d2782a", "#2c9a6a", "#a14fc4", "#c43d5c", "#5f8f1f", "#1f8aa0", "#8a6d3b", "#6b7280", "#b8860b"]


def load(runs):
    out = {}
    for name in ORDER:
        tj, lg = os.path.join(runs, name, "train.json"), os.path.join(runs, name + ".log")
        eps, final, state = [], None, "wartet"
        if os.path.exists(tj):
            r = json.load(open(tj))
            eps = r["epochs"]; final = r["val_final"]; state = "fertig"
        elif os.path.exists(lg):
            for line in open(lg, errors="replace"):
                if line.startswith('{"epoch"'):
                    try:
                        eps.append(json.loads(line))
                    except ValueError:
                        pass
            state = "läuft"
            if "Traceback" in open(lg, errors="replace").read():
                state = "Fehler"
        out[name] = {"eps": eps, "final": final, "state": state}
    return out


def chart(data):
    W, H, L, R, T, B = 720, 300, 52, 16, 14, 34
    series = [(n, [e["val_playout"]["q_regret_backed"] for e in d["eps"]]) for n, d in data.items() if d["eps"]]
    ys = [y for _, s in series for y in s] + [BASE["playout"]]
    lo, hi = min(ys + [1.6]), max(ys)
    lo, hi = (int(lo * 10) / 10), (int(hi * 10) + 1) / 10
    xmax = 24
    X = lambda i: L + (W - L - R) * i / xmax
    Y = lambda v: T + (H - T - B) * (hi - v) / (hi - lo)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Q-Regret pro Epoche">']
    v = lo
    while v <= hi + 1e-9:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" class="tick" text-anchor="end">{v:.1f}</text>')
        v += 0.1
    for i in range(0, 25, 4):
        parts.append(f'<text x="{X(i):.1f}" y="{H - 12}" class="tick" text-anchor="middle">{i + 1}</text>')
    parts.append(f'<text x="{(L + W - R) / 2}" y="{H - 0}" class="tick" text-anchor="middle">Epoche</text>')
    yb = Y(BASE["playout"])
    parts.append(f'<line x1="{L}" x2="{W - R}" y1="{yb:.1f}" y2="{yb:.1f}" class="base"/>'
                 f'<text x="{W - R - 4}" y="{yb - 6:.1f}" class="tick" text-anchor="end">g7f_E 2.45</text>')
    for k, (n, s) in enumerate(series):
        col = PALETTE[ORDER.index(n) % len(PALETTE)]
        off = 22 if n == "X-B" else 0
        pts = " ".join(f"{X(i + off):.1f},{Y(y):.1f}" for i, y in enumerate(s))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>')
        parts.append(f'<circle cx="{X(len(s) - 1 + off):.1f}" cy="{Y(s[-1]):.1f}" r="3.5" fill="{col}"/>')
    parts.append("</svg>")
    return "".join(parts)


def row(name, d):
    col = PALETTE[ORDER.index(name) % len(PALETTE)]
    ep = len(d["eps"]); tot = EPOCHS.get(name, 25)
    m = d["final"] if d["final"] else ({"playout": d["eps"][-1]["val_playout"], "all": d["eps"][-1]["val_all"]}
                                       if d["eps"] else None)
    cells = ["–"] * 5
    if m:
        p, a = m["playout"], m["all"]
        delta = p["q_regret_backed"] - BASE["playout"]
        cells = [f'{p["q_regret_backed"]:.3f}', f'{delta:+.3f}', f'{p["q_regret_mean"]:.3f}',
                 f'{100 * p["top1_gpick"]:.1f} %', f'{a["q_regret_backed"]:.3f}']
    pill = {"fertig": "ok", "läuft": "run", "wartet": "wait", "Fehler": "err"}[d["state"]]
    prog = f"{ep}/{tot}" if d["state"] != "wartet" else ""
    return (f'<tr><td><span class="sw" style="background:{col}"></span>{html.escape(name)}'
            f'<div class="sub">{html.escape(LABEL[name])}</div></td>'
            f'<td><span class="pill {pill}">{d["state"]}</span> <span class="sub">{prog}</span></td>'
            + "".join(f"<td class=num>{c}</td>" for c in cells) + "</tr>")


def main():
    runs, out = sys.argv[1], sys.argv[2]
    data = load(runs)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1))).strftime("%d.%m. %H:%M")
    done = [n for n, d in data.items() if d["final"]]
    best = min(done, key=lambda n: data[n]["final"]["playout"]["q_regret_backed"]) if done else None
    running = [n for n, d in data.items() if d["state"] == "läuft"]
    secs = [e["seconds"] for d in data.values() for e in d["eps"][-3:]] if running else []
    remaining = sum(EPOCHS.get(n, 25) - len(d["eps"]) for n, d in data.items() if d["state"] in ("läuft", "wartet"))
    eta = f"~{round(remaining * (sum(secs) / len(secs)) / 60)} min" if secs else "–"
    bestline = (f'{best}: {data[best]["final"]["playout"]["q_regret_backed"]:.3f} '
                f'({data[best]["final"]["playout"]["q_regret_backed"] - BASE["playout"]:+.3f} gegen g7f_E)') if best else "–"
    page = f"""<title>Rollout-Prior Training</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* layout: one column, summary strip, curve, run table */
:root {{ --bg:#f6f7f9; --panel:#ffffff; --fg:#1d2330; --muted:#5d6676; --line:#dfe3ea; --accent:#3b6fd8;
  --ok:#1f7a4d; --okbg:#dcf2e6; --run:#7a5a00; --runbg:#fbefc8; --err:#a3243b; --errbg:#f8dbe1;
  --f-head:"Space Grotesk",system-ui,sans-serif; --f-body:"Inter",system-ui,sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#12151b; --panel:#1a1f28; --fg:#e6e9ef;
  --muted:#9aa3b2; --line:#2c3340; --accent:#7ea2f0; --ok:#7fd3a4; --okbg:#173a2a; --run:#f0cd6b; --runbg:#3a3115;
  --err:#f19aac; --errbg:#40202a; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#12151b; --panel:#1a1f28; --fg:#e6e9ef; --muted:#9aa3b2; --line:#2c3340;
  --accent:#7ea2f0; --ok:#7fd3a4; --okbg:#173a2a; --run:#f0cd6b; --runbg:#3a3115; --err:#f19aac; --errbg:#40202a;
  color-scheme:dark }}
body {{ background:var(--bg); color:var(--fg); font-family:var(--f-body); }}
.wrap {{ max-width:900px; margin:0 auto; padding-block:20px 40px; padding-left:max(16px, env(safe-area-inset-left, 0px));
  padding-right:max(16px, env(safe-area-inset-right, 0px)); display:grid; gap:18px; }}
h1 {{ font-family:var(--f-head); font-size:1.5rem; margin:0; text-wrap:balance; }}
.lead {{ color:var(--muted); margin:4px 0 0; max-width:65ch; line-height:1.45; }}
.strip {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; }}
.kv {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; }}
.kv b {{ display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; }}
.kv span {{ font-family:var(--f-head); font-size:1.15rem; font-variant-numeric:tabular-nums; }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; }}
.panel h2 {{ font-family:var(--f-head); font-size:1rem; margin:0 0 8px; }}
svg {{ width:100%; height:auto; display:block; }}
.grid {{ stroke:var(--line); stroke-width:1; }} .base {{ stroke:var(--muted); stroke-dasharray:5 4; stroke-width:1.5; }}
.tick {{ fill:var(--muted); font-size:11px; font-family:var(--f-body); }}
.tbl {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:.86rem; }}
th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:600; }}
td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.sub {{ color:var(--muted); font-size:.76rem; }} .sw {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }}
.pill {{ font-size:.74rem; padding:2px 8px; border-radius:999px; }}
.ok {{ color:var(--ok); background:var(--okbg); }} .run {{ color:var(--run); background:var(--runbg); }}
.wait {{ color:var(--muted); border:1px solid var(--line); }} .err {{ color:var(--err); background:var(--errbg); }}
.note {{ color:var(--muted); font-size:.8rem; line-height:1.45; max-width:75ch; }}
</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@500;600&display=swap">
<div class="wrap">
<header><h1>Rollout-Prior auf G16-Zielen</h1>
<p class="lead">Stufe 1 von Issue #1053: g7f_E-großes MLP, trainiert auf 3,12 Mio. G16 + mb4 Roots (D2/D2b), PC-GPU.
Maß: Q-Regret (max-backed) des Argmax auf Validierungs-Roots in Boss-Räumen und Act 4, kleiner ist besser.</p></header>
<div class="strip">
<div class="kv"><b>Stand</b><span>{now} Uhr</span></div>
<div class="kv"><b>Fertig</b><span>{len(done)} / {len(ORDER)}</span></div>
<div class="kv"><b>Läuft</b><span>{html.escape(", ".join(running) or "–")}</span></div>
<div class="kv"><b>Rest (geschätzt)</b><span>{eta}</span></div>
<div class="kv"><b>Bester Lauf</b><span>{html.escape(bestline)}</span></div>
</div>
<section class="panel"><h2>Q-Regret Boss + Act 4 pro Epoche</h2>{chart(data)}</section>
<section class="panel tbl"><h2>Läufe</h2><table>
<tr><th>Lauf</th><th>Status</th><th class="num">Regret backed</th><th class="num">Δ g7f_E</th><th class="num">Regret mean</th>
<th class="num">Top-1 Pick</th><th class="num">Alle Räume</th></tr>
<tr><td>g7f_E<div class="sub">heutiger Playout-Prior</div></td><td></td><td class="num">{BASE['playout']:.3f}</td>
<td class="num">0</td><td class="num">{BASE['mean']:.3f}</td><td class="num">{100 * BASE['top1']:.1f} %</td><td class="num">{BASE['all']:.3f}</td></tr>
{''.join(row(n, d) for n, d in data.items())}
</table></section>
<p class="note">Validierung: 310.371 Roots (90.486 in Boss/Act 4), Split nach Run-Seed wie T1; die Gate-Holdout bleibt ungelesen.
V und CQP liefen in der Cloud (CPU), der Rest auf dem PC. Laufende Läufe zeigen die letzte Epoche, fertige den Endstand.
Root-Regret ist nur ein Vorfilter: ob ein Netz die Playouts verbessert, misst erst Stufe 2.</p>
</div>"""
    open(out, "w").write(page)


if __name__ == "__main__":
    main()
