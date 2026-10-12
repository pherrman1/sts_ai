#!/usr/bin/env python3
"""§452 tree-prior fight-level pilot: paired arm comparison.

usage: python3 tools/analyze_silver_tree_prior_452.py OUT.json DIR [DIR ...]

Reads every `*.states.csv`, `*.arms.csv` and `*.samples.csv` written by
`one_combat ctmsilvergen` with STS_CTMSILVER_ARMSET=treeprior452[k8] under the
given directories. A fight counts when every arm row of that state is valid
(the control replay matched the source fight). Fight score, per replicate:
0 on death, else 53 + curHp + 11 * potionCount + 0.25 * gold + 2 * maxHp
(Silver's victory weights; turn and escape terms omitted). Each arm's score
for a fight is its replicate mean; contrasts are paired per fight, and CIs are
a bootstrap over source seeds (10,000 resamples, RNG seed 0).
"""
import csv
import glob
import json
import os
import random
import sys
from collections import defaultdict

ARMS = ["plain2k", "root2k", "tree8_2k", "tree1_2k"]
CONTRASTS = [("tree8_2k", "plain2k"), ("root2k", "plain2k"), ("tree8_2k", "root2k"),
             ("tree1_2k", "plain2k"), ("tree1_2k", "tree8_2k")]


def score(row):
    if row["outcome"] == "DEATH":
        return 0.0
    return (53.0 + float(row["curHp"]) + 11.0 * float(row["potionCount"])
            + 0.25 * float(row["gold"]) + 2.0 * float(row["maxHp"]))


def load(dirs):
    states, valid, cpu, samples = {}, defaultdict(lambda: True), defaultdict(list), defaultdict(list)
    for d in dirs:
        for path in glob.glob(os.path.join(d, "**", "*.states.csv"), recursive=True):
            prefix = path[: -len(".states.csv")]
            with open(path) as f:
                for r in csv.DictReader(f):
                    states[r["stateId"]] = r
            with open(prefix + ".arms.csv") as f:
                for r in csv.DictReader(f):
                    valid[r["stateId"]] = valid[r["stateId"]] and r["valid"] == "1"
                    cpu[r["arm"]].append(float(r["cpuSeconds"]))
            with open(prefix + ".samples.csv") as f:
                for r in csv.DictReader(f):
                    samples[(r["stateId"], r["forecaster"])].append(r)
    return states, valid, cpu, samples


def boot(per_seed, n=10000, rng_seed=0):
    """per_seed: {seed: [diffs]} -> (mean, lo, hi) of the fight-weighted mean."""
    seeds = sorted(per_seed)
    rng = random.Random(rng_seed)
    total = sum(len(v) for v in per_seed.values())
    mean = sum(sum(v) for v in per_seed.values()) / total
    sums = [(sum(per_seed[s]), len(per_seed[s])) for s in seeds]
    stats = []
    for _ in range(n):
        a = b = 0.0
        for _ in seeds:
            s, c = sums[rng.randrange(len(seeds))]
            a += s
            b += c
        stats.append(a / b)
    stats.sort()
    return mean, stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    states, valid, cpu, samples = load(dirs)
    arms = [a for a in ARMS if any(k[1] == a for k in samples)]
    fights = {}
    for sid, st in states.items():
        if not valid[sid]:
            continue
        per = {}
        for a in arms:
            rows = samples.get((sid, a), [])
            if not rows:
                break
            per[a] = {"score": sum(map(score, rows)) / len(rows),
                      "death": sum(r["outcome"] == "DEATH" for r in rows) / len(rows),
                      "hp": sum(float(r["curHp"]) for r in rows) / len(rows)}
        else:
            fights[sid] = (st, per)
    result = {"states": len(states), "validFights": len(fights),
              "sourceSeeds": len({st["sourceSeed"] for st, _ in fights.values()}),
              "meanCpuSecondsPerFight": {a: sum(v) / len(v) for a, v in cpu.items()},
              "arms": {}, "contrasts": {}}
    for a in arms:
        result["arms"][a] = {k: sum(p[a][k] for _, p in fights.values()) / len(fights)
                             for k in ("score", "death", "hp")}
    subsets = {"all": lambda st: True,
               "boss": lambda st: st["roomClass"].upper().startswith("BOSS"),
               "elite": lambda st: st["roomClass"].upper().startswith("ELITE")}
    for x, y in CONTRASTS:
        if x not in arms or y not in arms:
            continue
        for name, keep in subsets.items():
            for metric in ("score", "death"):
                per_seed = defaultdict(list)
                for st, p in fights.values():
                    if keep(st):
                        per_seed[st["sourceSeed"]].append(p[x][metric] - p[y][metric])
                if not per_seed:
                    continue
                m, lo, hi = boot(per_seed)
                result["contrasts"][f"{x}-{y}/{name}/{metric}"] = {
                    "mean": m, "ci95": [lo, hi], "fights": sum(len(v) for v in per_seed.values())}
    primary = result["contrasts"].get("tree8_2k-plain2k/all/score")
    result["primaryLabel"] = ("TREE_PRIOR_HELPS" if primary and primary["ci95"][0] > 0
                              else "TREE_PRIOR_HURTS" if primary and primary["ci95"][1] < 0
                              else "NOT_SHOWN")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("validFights", "sourceSeeds", "primaryLabel")}))
    for k, v in result["contrasts"].items():
        print(f"{k}: {v['mean']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] n={v['fights']}")


if __name__ == "__main__":
    main()
