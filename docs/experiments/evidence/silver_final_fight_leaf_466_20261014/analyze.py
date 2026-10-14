#!/usr/bin/env python3
"""§466 final-fight leaf analysis. usage: python3 analyze.py OUT_DIR [OUT_DIR ...]

Reads shard*.arms.csv / shard*.samples.csv / shard*.states.csv written by
ctmsilvergen with STS_CTMSILVER_ARMSET=finalleaf (see PREREG-final-fight-leaf.md)."""
import csv
import glob
import random
import sys
from collections import Counter, defaultdict

ARMS = ("base10k", "final10k")


def main(dirs):
    states, arms, samples = {}, defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    control_ok = {}
    for d in dirs:
        for f in glob.glob(f"{d}/shard*.states.csv"):
            for r in csv.DictReader(open(f)):
                states[r["stateId"]] = r
        for f in glob.glob(f"{d}/shard*.arms.csv"):
            for r in csv.DictReader(open(f)):
                if r["arm"] == "control":
                    control_ok[r["stateId"]] = r["valid"] == "1"
                elif r["arm"] in ARMS:
                    arms[r["stateId"]][r["arm"]].append(r)
        for f in glob.glob(f"{d}/shard*.samples.csv"):
            for r in csv.DictReader(open(f)):
                if r["forecaster"] in ARMS:
                    samples[r["stateId"]][r["forecaster"]].append(r)
    reps = max((len(v) for a in arms.values() for v in a.values()), default=0)
    excluded = Counter()
    fights = []
    for sid, s in states.items():
        if not control_ok.get(sid, False):
            excluded["control_invalid_or_missing"] += 1; continue
        a = arms.get(sid, {})
        if any(len(a.get(x, [])) < reps for x in ARMS):
            excluded["incomplete_replicates"] += 1; continue
        if any(r["valid"] != "1" for x in ARMS for r in a[x]):
            excluded["invalid_arm_row"] += 1; continue
        win = {x: sum(int(r["won"]) == 1 for r in a[x]) / reps for x in ARMS}
        cpu = {x: sum(float(r["cpuSeconds"]) for r in a[x]) / reps for x in ARMS}
        smp = samples.get(sid, {})
        deathPot = {x: sum(1 for r in smp.get(x, []) if r["outcome"] == "DEATH" and int(r["potionCount"]) > 0) for x in ARMS}
        deaths = {x: sum(1 for r in smp.get(x, []) if r["outcome"] == "DEATH") for x in ARMS}
        winPot = {x: [int(r["potionCount"]) for r in smp.get(x, []) if r["outcome"] == "VICTORY"] for x in ARMS}
        fights.append(dict(seed=s["sourceSeed"], enc=s["encounter"], win=win, cpu=cpu,
                           deathPot=deathPot, deaths=deaths, winPot=winPot))
    n = len(fights)
    print(f"replicates R={reps}; valid act-3 boss fights {n}; excluded {dict(excluded)}")
    if not n:
        return
    for x in ARMS:
        w = sum(f["win"][x] for f in fights) / n
        d = sum(f["deaths"][x] for f in fights); dp = sum(f["deathPot"][x] for f in fights)
        wp = [p for f in fights for p in f["winPot"][x]]
        c = sum(f["cpu"][x] for f in fights) / n
        print(f"{x}: win {w:.4f}; deaths {d} (holding potions {dp}); potions held per win "
              f"{(sum(wp) / len(wp)) if wp else float('nan'):.3f}; cpu/fight {c:.2f}s")
    by_seed = defaultdict(list)
    for f in fights:
        by_seed[f["seed"]].append(f["win"]["final10k"] - f["win"]["base10k"])
    seeds = sorted(by_seed)
    point = sum(sum(v) for v in by_seed.values()) / n
    rng = random.Random(0)
    boots = []
    for _ in range(10000):
        pick = [by_seed[seeds[rng.randrange(len(seeds))]] for _ in seeds]
        tot = sum(len(v) for v in pick)
        boots.append(sum(sum(v) for v in pick) / tot if tot else 0.0)
    boots.sort()
    lo, hi = boots[249], boots[9749]
    label = "FINAL_LEAF_HELPS" if lo > 0 else "FINAL_LEAF_HURTS" if hi < 0 else "NOT_SHOWN"
    print(f"PRIMARY final10k - base10k win rate: {point * 100:+.2f} pp [{lo * 100:+.2f}, {hi * 100:+.2f}] "
          f"over {len(seeds)} source seeds -> {label}")
    per = defaultdict(lambda: [0, 0.0])
    for f in fights:
        per[f["enc"]][0] += 1; per[f["enc"]][1] += f["win"]["final10k"] - f["win"]["base10k"]
    for e, (k, s) in sorted(per.items()):
        print(f"  {e}: fights {k}, mean diff {s / k * 100:+.2f} pp")


if __name__ == "__main__":
    main(sys.argv[1:])
