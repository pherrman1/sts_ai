#!/usr/bin/env python3
"""§469 paired Collector-fight eval: arm B (Collector prior) - arm A (gen 4).

usage: python3 analyze_469.py OUT.json DIR [DIR ...]
Reads every `*.csv` written by `one_combat silverfocusevalgen` under the dirs (with its manifest).
Fight score per copy: 0 on death, else 53 + curHp + 11 * potionCount + 0.25 * gold + 2 * maxHp (§460).
A copy counts only if both arms' rows are valid; per seed, each arm's score is its mean over the
counted copies; the contrast is paired per seed; 95% CI from a bootstrap over seeds (10,000 resamples,
RNG seed 0). Rule: HELPS if the CI is above 0, HURTS if below 0, else NOT_SHOWN.
"""
import csv, glob, json, os, random, sys
from collections import defaultdict


def score(r):
    if r["won"] != "1":
        return 0.0
    return 53.0 + float(r["curHp"]) + 11.0 * float(r["potionCount"]) + 0.25 * float(r["gold"]) + 2.0 * float(r["maxHp"])


def boot(vals, n=10000, seed=0):
    rng = random.Random(seed)
    m = len(vals)
    bs = sorted(sum(vals[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return [bs[int(0.025 * n)], bs[int(0.975 * n) - 1]]


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    rows, manifests = [], []
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*.csv"), recursive=True):
            rows += list(csv.DictReader(open(p)))
            mp = p[:-4] + ".manifest.json"
            if os.path.exists(mp):
                manifests.append(json.load(open(mp)))
    pairs = defaultdict(dict)
    for r in rows:
        if r["arm"] in pairs[(r["seed"], r["replicate"])]:
            raise SystemExit(f"duplicate row seed {r['seed']} replicate {r['replicate']} arm {r['arm']}")
        pairs[(r["seed"], r["replicate"])][r["arm"]] = r
    per_seed = defaultdict(lambda: {"A": [], "B": [], "dA": [], "dB": [], "cA": [], "cB": []})
    dropped = 0
    for (seed, rep), arms in pairs.items():
        if set(arms) != {"A", "B"} or any(arms[a]["valid"] != "1" for a in arms):
            dropped += 1
            continue
        for a in "AB":
            per_seed[seed][a].append(score(arms[a]))
            per_seed[seed]["d" + a].append(1.0 if arms[a]["won"] != "1" else 0.0)
            per_seed[seed]["c" + a].append(float(arms[a]["cpuSeconds"]))
    mean = lambda x: sum(x) / len(x)
    seeds = sorted(per_seed)
    res = {"seeds": len(seeds), "copies": sum(len(per_seed[s]["A"]) for s in seeds), "droppedCopies": dropped,
           "manifests": len(manifests),
           "requestedSeeds": sum(m["integrity"]["requestedSeeds"] for m in manifests),
           "completedSeeds": sum(m["integrity"]["completedSeeds"] for m in manifests),
           "reachedSeeds": sum(m["integrity"]["reachedSeeds"] for m in manifests)}
    for metric, key in (("score", ""), ("death", "d"), ("cpu", "c")):
        a = [mean(per_seed[s][key + "A"]) for s in seeds]
        b = [mean(per_seed[s][key + "B"]) for s in seeds]
        diff = [y - x for x, y in zip(a, b)]
        res[metric] = {"A": mean(a), "B": mean(b), "B-A": mean(diff), "ci95": boot(diff)}
    lo, hi = res["score"]["ci95"]
    res["verdict"] = "HELPS" if lo > 0 else "HURTS" if hi < 0 else "NOT_SHOWN"
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
