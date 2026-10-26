#!/usr/bin/env python3
"""Gen-3 results table from runs/*/summary.json (chosen epoch's selection metrics, report-only validation).
usage: summarize_g3.py GEN3_DIR"""
import glob, json, os, sys
R = sys.argv[1]; rows = []
for s in sorted(glob.glob(os.path.join(R, "runs", "*", "summary.json"))):
    n = os.path.basename(os.path.dirname(s)); d = json.load(open(s))
    h = next(x for x in d["history"] if x["epoch"] == d["selected_epoch"]); sv = h["select"]["value"]["all"]
    vv = d["value"].get("all", {})
    rows.append((n, h["select"]["kl"], sv["bce"], sv["const_bce"], sv.get("auc"), d["best_val_kl"], d["best_val_top1"],
                 vv.get("bce"), vv.get("auc"), d["selected_epoch"], d["epochs_run"], d["wall_sec"]))
print("| run | sel KL | sel BCE | sel const | sel AUC | val KL | val top-1 | val BCE | val AUC | epoch | run | wall s |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
f = lambda x, p=4: "-" if x is None else f"{x:.{p}f}"
for r in rows:
    print(f"| {r[0]} | {f(r[1])} | {f(r[2])} | {f(r[3])} | {f(r[4],3)} | {f(r[5])} | {f(r[6],3)} | {f(r[7])} | {f(r[8],3)} "
          f"| {r[9]} | {r[10]} | {r[11]:.0f} |")
pick = open(os.path.join(R, "logs", "pick.txt")).read().strip() if os.path.exists(os.path.join(R, "logs", "pick.txt")) else None
kl = {r[0]: r[1] for r in rows}
if pick:
    refs = [kl.get("REF_gen2_pick"), kl.get("REF_gen2_VT_nstep")]
    ok = all(x is not None and kl[pick] < x for x in refs)
    print(f"\npick {pick} (sel KL {kl[pick]:.4f}); beats both gen-2 references on selection: {ok}"
          + ("" if ok else " -> NO_CANDIDATE"))
