#!/usr/bin/env python3
"""v3 live promotion verdict (PLAN.md), at full precision.

  analyze.py RUN_DIR [--out report.json]

Pools RUN_DIR/part*/<arm>K.csv per arm, pairs by seed on the intersection of
all arms, and for each variant against `control` computes the mean paired
floor difference with a Bonferroni (3 variants) 98.33% bootstrap CI, using
paired_analysis.bootstrap_ci (10,000 replicates, one fresh generator with
seed 20260807 per variant).
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 5))
import paired_analysis as pa  # noqa: E402

ARMS = ["control", "learned", "bossfallback", "bossmax30k"]
VARIANTS = ARMS[1:]
CI = 1 - 0.05 / len(VARIANTS)
MARGIN = -0.75


def pooled(run_dir, arm):
    rows = {}
    for path in sorted(glob.glob(os.path.join(run_dir, "part*", f"{arm}[0-9].csv"))):
        for r in pa.load(path)[0]:
            if r["seed"] in rows:
                raise ValueError(f"duplicate seed {r['seed']} in {path}")
            rows[r["seed"]] = r
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir")
    p.add_argument("--out")
    args = p.parse_args()
    data = {a: pooled(args.run_dir, a) for a in ARMS}
    seeds = sorted(set.intersection(*(set(d) for d in data.values())))
    union = set().union(*(set(d) for d in data.values()))
    report = {"pairs": len(seeds), "seedsMissingInSomeArm": len(union) - len(seeds),
              "ci": CI, "margin": MARGIN, "variants": {}}
    ctl = data["control"]
    ctl_sec = float(np.mean([ctl[s]["sec"] for s in seeds]))
    report["controlSecPerRun"] = ctl_sec
    for v in VARIANTS:
        d = data[v]
        fd = np.array([d[s]["floor"] - ctl[s]["floor"] for s in seeds], dtype=float)
        wd = np.array([d[s]["won"] - ctl[s]["won"] for s in seeds], dtype=float)
        mean, lo, hi = pa.bootstrap_ci(fd, ci=CI, rng=np.random.default_rng(pa.BOOTSTRAP_SEED))
        _, wlo, whi = pa.bootstrap_ci(wd, ci=0.95, rng=np.random.default_rng(pa.BOOTSTRAP_SEED))
        sec = float(np.mean([d[s]["sec"] for s in seeds]))
        report["variants"][v] = {
            "floorDiff": mean, "floorDiffCI": [lo, hi], "winDiff": float(wd.mean()),
            "winDiffCI95": [wlo, whi], "secPerRun": sec, "secRatio": sec / ctl_sec,
            "qualifies": bool(lo > MARGIN and sec < ctl_sec)}
    qual = [v for v in VARIANTS if report["variants"][v]["qualifies"]]
    if qual:
        best = max(qual, key=lambda v: (report["variants"][v]["floorDiff"], -report["variants"][v]["secPerRun"]))
        report["verdict"] = f"PROMOTE_{best}"
    else:
        report["verdict"] = "KEEP_OPT_IN"
    if report["seedsMissingInSomeArm"]:
        report["note"] = "partial: computed on the intersection of all four arms"
    text = json.dumps(report, indent=1)
    if args.out:
        open(args.out, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
