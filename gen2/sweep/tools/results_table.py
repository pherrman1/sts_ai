#!/usr/bin/env python3
"""AZ gen 2 sweep: one markdown table over SWEEPDIR/*/summary.json (+ train.log wall time).
usage: results_table.py SWEEPDIR > table.md
Columns: selection fold (sel_obj = the run's own objective at the chosen epoch, sel policy KL, sel value BCE/const);
validation fold at the chosen epoch (KL to pi', top-1, value BCE/const/AUC overall and per act, anchor KL to
student_sel); chosen epoch / epochs run; wall minutes. ok = selection value BCE < const BCE (candidate rule)."""
import glob, json, os, re, sys
rows = []
for s in sorted(glob.glob(os.path.join(sys.argv[1], "*", "summary.json"))):
    d = json.load(open(s)); name = os.path.basename(os.path.dirname(s))
    h = next(x for x in d["history"] if x["epoch"] == d["selected_epoch"]); sel = h.get("select", {})
    sv = sel.get("value", {}).get("all", {}); v = d["value"]
    log = open(os.path.join(os.path.dirname(s), "train.log")).read()
    m = re.search(r"^real ([0-9.]+)", log, re.M); wall = float(m.group(1)) / 60 if m else d.get("wall_sec", 0) / 60
    f = lambda x, k="bce": "–" if not x else f"{x[k]:.4f}" if isinstance(x.get(k), float) else str(x.get(k))
    acts = " / ".join(f"{v[g]['bce']:.3f}|{v[g]['const_bce']:.3f}|{v[g]['auc']:.3f}" if g in v and v[g]["auc"] is not None else "–"
                      for g in ("act1", "act2", "act3", "act4"))
    ok = sv and sv["bce"] < sv["const_bce"]
    rows.append((sel.get("kl") if ok else 9e9, f"| {name} | {sel.get('objective', 0):.4f} | {sel.get('kl', 0):.4f} | "
                 f"{f(sv)} / {f(sv, 'const_bce')} | {'yes' if ok else 'no'} | {d['best_val_kl']:.4f} | {d['best_val_top1']:.4f} | "
                 f"{f(v.get('all'))} / {f(v.get('all'), 'const_bce')} / {f(v.get('all'), 'auc')[:6]} | {acts} | "
                 f"{v.get('anchor_kl', '–')} | {d['selected_epoch']} / {d.get('epochs_run', len(d['history']) - 1)} | {wall:.1f} |"))
print("| run | sel objective | sel policy KL | sel value BCE / const | value < const | val KL to π' | val top-1 | "
      "val value BCE / const / AUC | per act BCE\\|const\\|AUC (act1 / act2 / act3 / act4) | val anchor KL | chosen / run epochs | wall min |")
print("|" + "---|" * 12)
for _, r in sorted(rows, key=lambda x: x[0]): print(r)
