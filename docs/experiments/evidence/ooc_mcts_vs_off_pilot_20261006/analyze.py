#!/usr/bin/env python3
"""OOC MCTS on vs off pilot verdict (PLAN.md).

  analyze.py RUN_DIR [--out report.json]

Pools RUN_DIR/<arm>K.csv (K = 0..3) per arm and pairs by seed on the
intersection of all arms. For each comparison it reports the mean paired win
and floor differences with 95% bootstrap CIs from paired_analysis.bootstrap_ci
(10,000 replicates, a fresh generator with seed 20261006 per statistic).
Only mcts - flat10k decides the verdict; the other two are descriptive.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 4))
import paired_analysis as pa  # noqa: E402

ARMS = ["learned", "flat10k", "mcts"]
COMPARISONS = [("mcts", "flat10k"), ("flat10k", "learned"), ("mcts", "learned")]
SEED = 20261006


def pooled(run_dir, arm):
    rows = {}
    for path in sorted(glob.glob(os.path.join(run_dir, f"{arm}[0-9].csv"))):
        for r in pa.load(path)[0]:
            if r["seed"] in rows:
                raise ValueError(f"duplicate seed {r['seed']} in {path}")
            rows[r["seed"]] = r
    return rows


def ci(x):
    return list(pa.bootstrap_ci(np.asarray(x, dtype=float), ci=0.95, rng=np.random.default_rng(SEED)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir")
    p.add_argument("--out")
    args = p.parse_args()
    data = {a: pooled(args.run_dir, a) for a in ARMS}
    seeds = sorted(set.intersection(*(set(d) for d in data.values())))
    union = set().union(*(set(d) for d in data.values()))
    report = {"pairs": len(seeds), "seedsMissingInSomeArm": len(union) - len(seeds), "arms": {}, "diffs": {}}
    for a in ARMS:
        d = data[a]
        report["arms"][a] = {k: float(np.mean([d[s][k] for s in seeds])) for k in ("won", "floor", "sec")}
    for x, y in COMPARISONS:
        wx = [data[x][s]["won"] for s in seeds]
        wy = [data[y][s]["won"] for s in seeds]
        report["diffs"][f"{x}-{y}"] = {
            "win": ci([a - b for a, b in zip(wx, wy)]),
            "floor": ci([data[x][s]["floor"] - data[y][s]["floor"] for s in seeds]),
            "discordant": [sum(a > b for a, b in zip(wx, wy)), sum(b > a for a, b in zip(wx, wy))],
            "secRatio": report["arms"][x]["sec"] / report["arms"][y]["sec"]}
    _, lo, hi = report["diffs"]["mcts-flat10k"]["win"]
    report["verdict"] = "MCTS_BETTER" if lo > 0 else "MCTS_WORSE" if hi < 0 else "INCONCLUSIVE"
    if report["seedsMissingInSomeArm"]:
        report["note"] = "partial: computed on the intersection of all arms"
    text = json.dumps(report, indent=1)
    if args.out:
        open(args.out, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
