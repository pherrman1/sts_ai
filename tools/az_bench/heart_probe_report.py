#!/usr/bin/env python3
"""Paired report of a Heart search probe (selfplay.py --heart-arms, 2026-11-18).

Each Heart start (run seed) is played once per arm and rep from the same state. Per start and arm the plays are
averaged; arm k is compared with arm 0 by the paired per-start difference in damage dealt to the Heart
(heart_max_hp - heart_hp), with a bootstrap 95 % interval over starts, plus kill and stall counts.

usage: heart_probe_report.py heart_probe.jsonl [--arms "64/16 p.25,256 full,..."] [--json out.json]
"""

import argparse
import collections
import json
import sys

import numpy as np


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--arms", default="", help="comma-separated arm names (default: arm0, arm1, ...)")
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in open(args.path) if l.strip()]
    n_arms = 1 + max(r["arm"] for r in rows)
    names = [a.strip() for a in args.arms.split(",")] if args.arms else [f"arm{k}" for k in range(n_arms)]
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by[r["seed"]][r["arm"]].append(r)
    reps = max(len(v) for s in by.values() for v in s.values())
    # Complete starts only: every arm has all its reps (a probe stopped early leaves partial starts).
    starts = sorted(s for s, v in by.items() if all(len(v[k]) == reps for k in range(n_arms)))
    dmg = np.array([[np.mean([p["heart_max_hp"] - p["heart_hp"] for p in by[s][k]]) for k in range(n_arms)]
                    for s in starts])
    rng = np.random.default_rng(0)
    out = {"plays": len(rows), "starts_complete": len(starts), "reps": reps, "arms": []}
    for k in range(n_arms):
        plays = [p for s in starts for p in by[s][k]]
        a = {"arm": k, "name": names[k] if k < len(names) else f"arm{k}", "plays": len(plays),
             "kills": sum(p["win"] for p in plays), "stalls": sum(p["stall"] for p in plays),
             "damage_mean": float(dmg[:, k].mean()) if len(starts) else None,
             "damage_median": float(np.median(dmg[:, k])) if len(starts) else None,
             "turns_mean": float(np.mean([p["turns"] for p in plays])) if plays else None,
             "searched_moves_mean": float(np.mean([p["searched"] for p in plays])) if plays else None}
        if k > 0 and len(starts) > 1:
            d = dmg[:, k] - dmg[:, 0]
            idx = rng.integers(0, len(d), size=(args.boot, len(d)))
            bm = d[idx].mean(1)
            a["diff_vs_arm0"] = {"mean": float(d.mean()), "se": float(d.std(ddof=1) / np.sqrt(len(d))),
                                 "ci95": [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))],
                                 "share_starts_better": float(np.mean(d > 0)),
                                 "share_starts_worse": float(np.mean(d < 0))}
        out["arms"].append(a)
    print(json.dumps(out, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
