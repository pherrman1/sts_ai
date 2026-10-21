#!/usr/bin/env python3
"""Builds gen2/sweep/results.md from the run folders under ~/h1distill/gen2 (summary.json + train.log)."""
import glob, json, os, re, sys
R = os.path.expanduser("~/h1distill/gen2")

def info(path):
    d = json.load(open(os.path.join(path, "summary.json")))
    h = next(x for x in d["history"] if x["epoch"] == d["selected_epoch"]); s = h.get("select", {})
    sv = s.get("value", {}).get("all", {}); v = d["value"] or {}
    log = open(os.path.join(path, "train.log")).read()
    m = re.search(r"^real ([0-9.]+)", log, re.M)
    return dict(name=os.path.basename(path), ep=d["selected_epoch"], run=d.get("epochs_run", len(d["history"]) - 1),
                obj=s.get("objective"), skl=s.get("kl"), sbce=sv.get("bce"), sconst=sv.get("const_bce"), sauc=sv.get("auc"),
                vkl=d["best_val_kl"], vtop=d["best_val_top1"], v=v, anc=v.get("anchor_kl", s.get("value", {}).get("anchor_kl")),
                sanc=s.get("value", {}).get("anchor_kl"), wall=float(m.group(1)) / 60 if m else None, d=d)

f = lambda x, n=4: "–" if x is None else f"{x:.{n}f}" if isinstance(x, float) else str(x)
def acts(v):
    return " / ".join(f"{v[g]['bce']:.3f}·{v[g]['const_bce']:.3f}·{v[g]['auc']:.3f}" if g in v and v[g].get("auc") is not None else "–"
                      for g in ("act1", "act2", "act3", "act4"))
HEAD = ("| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | "
        "val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |\n" + "|---" * 11 + "|")
def row(i):
    va = i["v"].get("all", {})
    return (f"| {i['name']} | {i['ep']} / {i['run']} | {f(i['obj'])} | {f(i['skl'])} | {f(i['sbce'])} / {f(i['sconst'])} / {f(i['sauc'],3)} | "
            f"{f(i['vkl'])} | {f(i['vtop'])} | {f(va.get('bce'))} / {f(va.get('const_bce'))} / {f(va.get('auc'),3)} | {acts(i['v'])} | "
            f"{f(i['sanc'])} / {f(i['anc'])} | {f(i['wall'],1)} |")
def table(paths, key=lambda i: i["skl"] if i["skl"] is not None else 9):
    xs = sorted([info(p) for p in paths if os.path.exists(os.path.join(p, "summary.json"))], key=key)
    return "\n".join([HEAD] + [row(i) for i in xs])

g = sorted(glob.glob(f"{R}/sweep/S_d64L2_lr*_s0")); grid = [p for p in g if "ep40" not in p]
out = [open(f"{R}/tools/results_head.md").read()]
out += ["## Stage S grid (K=32, pack, val-at-end, patience 3, cap 20; init student_sel; seed 0), sorted by selection policy KL\n", table(grid), ""]
out += ["## Architectures (random init, anchor weight 0, at the best grid point lr 1e-4 / value weight 0.3; anchor KL vs student_sel via --anchor-ref)\n",
        table(sorted(glob.glob(f"{R}/sweep/A_*"))), ""]
out += ["## Seed reruns of the pick and the 40-epoch cap check\n",
        table(sorted(glob.glob(f"{R}/sweep/S_d64L2_lr1e-4_a0.3_v0.3_*")), key=lambda i: i["name"]), ""]
out += ["## Stage T\n", table(sorted(glob.glob(f"{R}/sweep/T*")) + sorted(glob.glob(f"{R}/sweep/E_*")), key=lambda i: i["name"]), ""]
out += ["## Side test: full data (no value subsample), pack + val-at-end — stopped after 7 points by decision\n", table(sorted(glob.glob(f"{R}/sweep_full/*"))), ""]
out += ["## Side test: value subsample (K per run per epoch), recipe lr 3e-4 / a1 / v1\n", table(sorted(glob.glob(f"{R}/ktest/K_*")) + [f"{R}/sweep_nopack/S_d64L2_lr3e-4_a1_v1_s0"], key=lambda i: i["name"]), ""]
def curve(p):
    d = json.load(open(os.path.join(p, "summary.json")))
    return f"- {os.path.basename(p)}: " + ", ".join(f"ep{h['epoch']} {h['select']['kl']:.4f}/{h['select']['value']['all']['bce']:.3f}" for h in d["history"] if "select" in h)
out += ["Per-epoch selection-fold policy KL / value BCE (const 0.642):\n"] + [curve(p) for p in sorted(glob.glob(f"{R}/ktest/K_*_ep20_s0")) + [f"{R}/sweep_nopack/S_d64L2_lr3e-4_a1_v1_s0", f"{R}/sweep_full/S_d64L2_lr3e-4_a1_v1_s0"]] + [""]
out += ["## Speed benchmarks (1 epoch, full cached data, lr 3e-4 / a1 / v1)\n", table(sorted(glob.glob(f"{R}/bench/bench_*")), key=lambda i: i["name"]), ""]
out += [open(f"{R}/tools/results_tail.md").read()]
print("\n".join(out))
