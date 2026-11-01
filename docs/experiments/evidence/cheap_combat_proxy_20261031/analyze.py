#!/usr/bin/env python3
"""Cheap-combat proxy check (PREREG.md). usage: analyze.py OUT_ROOT [result.json]

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log} from run_unit.sh. Frozen before any campaign game ran.
"""
import json, random, re, sys
from pathlib import Path

REF = {"diff_pp": 6.0546875, "ci95_pp": [3.41796875, 8.59375]}  # §691, production combat, heartoutcomegen runner
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+)", re.M)


def load(root):
    games = {}  # (arm, seed) -> (kill, act4, floor, wall)
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if d["rc"] != "0":
            continue
        m = WIN.search(done.with_suffix(".log").read_text())
        if not m:
            continue
        floor = float(m.group(2))
        games[(arm, int(seed))] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, int(d["wall"]))
    return games


def paired(games, a, b, idx=0, reps=10000):
    seeds = sorted(s for (arm, s) in games if arm == a and (b, s) in games)
    if not seeds:
        return None
    d = [games[(b, s)][idx] - games[(a, s)][idx] for s in seeds]
    n = len(d)
    rng = random.Random(20261031)
    boots = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return {"n": n, "rate_a_pct": 100 * sum(games[(a, s)][idx] for s in seeds) / n,
            "rate_b_pct": 100 * sum(games[(b, s)][idx] for s in seeds) / n,
            "diff_pp": 100 * sum(d) / n, "ci95_pp": [100 * boots[int(0.025 * reps)], 100 * boots[int(0.975 * reps) - 1]]}


def did(games, c, p, reps=10000):
    seeds = sorted(s for (arm, s) in games if arm == "R" + c
                   and all((x, s) in games for x in ("F" + c, "RP", "FP")))
    if not seeds:
        return None
    d = [(games[("F" + c, s)][0] - games[("R" + c, s)][0]) - (games[("FP", s)][0] - games[("RP", s)][0]) for s in seeds]
    n = len(d)
    rng = random.Random(20261101)
    boots = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return {"n": n, "did_pp": 100 * sum(d) / n, "ci95_pp": [100 * boots[int(0.025 * reps)], 100 * boots[int(0.975 * reps) - 1]]}


def verdict(r):
    if r is None:
        return "MISSING"
    lo, hi = r["ci95_pp"]
    p = REF["diff_pp"]
    if lo > 0 and 0.5 * p <= r["diff_pp"] <= 1.5 * p:
        return "VALID"
    if hi < 0.5 * p:
        return "INVALID"
    return "INCONCLUSIVE"


def main():
    games = load(sys.argv[1])
    out = {"reference_691": REF, "games": len(games)}
    for c in ("1000", "200", "P"):
        k = paired(games, "R" + c, "F" + c)
        out[c] = {"heart": k, "act4": paired(games, "R" + c, "F" + c, idx=1),
                  "mean_wall_s": {arm: (sum(v[3] for (a, _), v in games.items() if a == arm)
                                        / max(1, sum(1 for (a, _) in games if a == arm))) for arm in ("R" + c, "F" + c)}}
        if c != "P":
            out[c]["verdict"] = verdict(k)
            out[c]["did_vs_same_runner_production"] = did(games, c, "P")
    print(json.dumps(out, indent=1))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
