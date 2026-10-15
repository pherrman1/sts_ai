#!/usr/bin/env python3
"""§476: gen-6 Silver MLP prior at A20 with a simulation sweep (paired fight-level).

usage: python3 analyze_476.py OUT.json DIR [DIR ...]

Reads every `*.states.csv`, `*.arms.csv` and `*.samples.csv` written by
`one_combat ctmsilvergen N 20 ...` with STS_CTMSILVER_ARMSET=mlpsweep under the
given directories. Same fight score, pairing and bootstrap as §460
(`../silver_az_mlp_gen3_eval_20261013/analyze_gen3.py`): per replicate 0 on death,
else 53 + curHp + 11 * potionCount + 0.25 * gold + 2 * maxHp; arm value per fight is
the replicate mean; contrasts are paired per fight; 95% CIs are a bootstrap over
source seeds (10,000 resamples, RNG seed 0). A fight counts only when every arm row
is valid and every arm has R = 2 replicates. Also reported: win rate per fight
(1 - death) and HP lost per fight (preHp - post-combat curHp, a death loses all preHp).
A CSV that does not end in a newline (shard killed mid-write) loses its last line, counted
under `truncatedRows`. Per-shard manifests (absent after a kill) are summarized under
`shards`.
"""
import csv
import glob
import json
import os
import random
import sys
from collections import defaultdict

BUDGETS = [10000, 2500, 625]
R = 2
ARMS = [f"{m}{b}" for b in BUDGETS for m in ("plain", "mlp", "mlpprev")]
PRIMARY = [(f"mlp{b}", f"plain{b}") for b in BUDGETS]          # gen 6 vs no prior
ITERATION = [(f"mlp{b}", f"mlpprev{b}") for b in BUDGETS]      # gen 6 vs gen 5
SECONDARY = ([(f"mlpprev{b}", f"plain{b}") for b in BUDGETS]
             + [("mlp2500", "plain10000"), ("mlp625", "plain2500"), ("mlp625", "plain10000"),
                ("plain2500", "plain10000"), ("plain625", "plain10000"),
                ("mlp2500", "mlp10000"), ("mlp625", "mlp10000")])
METRICS = ("score", "win", "hpLoss")


def score(row):
    if row["outcome"] == "DEATH":
        return 0.0
    return (53.0 + float(row["curHp"]) + 11.0 * float(row["potionCount"])
            + 0.25 * float(row["gold"]) + 2.0 * float(row["maxHp"]))


TRUNCATED = defaultdict(int)


def rows(path):
    """csv.DictReader rows of PATH without a final line cut off mid-write."""
    with open(path, newline="") as f:
        text = f.read()
    if text and not text.endswith("\n"):
        text = text[: text.rfind("\n") + 1]
        TRUNCATED[os.path.basename(path).split(".", 1)[1]] += 1
    return list(csv.DictReader(text.splitlines()))


def load(dirs):
    states, valid, cpu, dec, samples = {}, defaultdict(lambda: True), defaultdict(list), defaultdict(int), defaultdict(list)
    shards = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.states.csv"), recursive=True)):
            prefix = path[: -len(".states.csv")]
            for r in rows(path):
                if r["stateId"] in states:
                    raise SystemExit(f"duplicate state {r['stateId']}")
                states[r["stateId"]] = r
            for r in rows(prefix + ".arms.csv"):
                valid[r["stateId"]] = valid[r["stateId"]] and r["valid"] == "1"
                cpu[r["arm"]].append(float(r["cpuSeconds"]))
                dec[r["arm"]] += int(r["decisions"])
            for r in rows(prefix + ".samples.csv"):
                samples[(r["stateId"], r["forecaster"])].append(r)
            shard = {"prefix": os.path.relpath(prefix, d), "manifest": os.path.exists(prefix + ".manifest.json")}
            if shard["manifest"]:
                with open(prefix + ".manifest.json") as f:
                    m = json.load(f)
                shard.update(requestedSeeds=m["seedSpec"]["count"], finishedSeeds=len(m["sources"]),
                             **{k: m["integrity"][k] for k in ("states", "controlReplayMismatches",
                                                               "invalidArmRows", "hallwaySkipped")})
            shards.append(shard)
    return states, valid, cpu, dec, samples, shards


def boot(per_seed, n=10000, rng_seed=0):
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


def label(c, pos, neg):
    return pos if c["ci95"][0] > 0 else neg if c["ci95"][1] < 0 else "NOT_SHOWN"


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    states, valid, cpu, dec, samples, shards = load(dirs)
    missing = [a for a in ARMS if a not in cpu]
    if missing:
        raise SystemExit(f"missing arms: {missing}")
    over = {len(v) for (sid, a), v in samples.items() if a in ARMS and len(v) > R}
    if over:
        raise SystemExit(f"more than R={R} replicates per fight: {sorted(over)}")
    fights, excluded = {}, defaultdict(int)
    for sid, st in states.items():
        if not valid[sid]:
            excluded["invalid_arm_row"] += 1
            continue
        pre = float(st["preHp"])
        per = {}
        for a in ARMS:
            rows = samples.get((sid, a), [])
            if len(rows) < R:
                excluded["incomplete_shard_abort"] += 1
                break
            dead = [r["outcome"] == "DEATH" for r in rows]
            per[a] = {"score": sum(map(score, rows)) / R,
                      "win": 1.0 - sum(dead) / R,
                      "hpLoss": sum(pre - (0.0 if d else float(r["curHp"])) for r, d in zip(rows, dead)) / R}
        else:
            fights[sid] = (st, per)
    if not fights:
        raise SystemExit("no valid fights")
    rooms = defaultdict(int)
    for st, _ in fights.values():
        rooms[st["roomClass"]] += 1
    mean_cpu = {a: sum(v) / len(v) for a, v in cpu.items()}
    result = {"states": len(states), "validFights": len(fights), "excluded": dict(excluded),
              "truncatedRows": dict(TRUNCATED), "shards": shards,
              "seedsWithStates": len({st["sourceSeed"] for st in states.values()}),
              "roomClasses": dict(rooms),
              "sourceSeeds": len({st["sourceSeed"] for st, _ in fights.values()}),
              "meanCpuSecondsPerFight": mean_cpu,
              "cpuMsPerDecision": {a: 1000 * sum(v) / max(1, dec[a]) for a, v in cpu.items()},
              "cpuPerFightVsPlainSameBudget": {f"{m}{b}": mean_cpu[f"{m}{b}"] / mean_cpu[f"plain{b}"]
                                               for b in BUDGETS for m in ("plain", "mlp", "mlpprev")},
              "arms": {}, "contrasts": {}, "labels": {}}
    for a in ARMS:
        result["arms"][a] = {k: sum(p[a][k] for _, p in fights.values()) / len(fights) for k in METRICS}
    subsets = {"all": lambda st: True,
               "boss": lambda st: st["roomClass"] == "BOSS",
               "elite": lambda st: st["roomClass"] == "ELITE",
               "normal": lambda st: st["roomClass"] not in ("BOSS", "ELITE")}
    for x, y in PRIMARY + ITERATION + SECONDARY:
        for name, keep in subsets.items():
            for metric in METRICS:
                per_seed = defaultdict(list)
                for st, p in fights.values():
                    if keep(st):
                        per_seed[st["sourceSeed"]].append(p[x][metric] - p[y][metric])
                if not per_seed:
                    continue
                m, lo, hi = boot(per_seed)
                result["contrasts"][f"{x}-{y}/{name}/{metric}"] = {
                    "mean": m, "ci95": [lo, hi], "fights": sum(len(v) for v in per_seed.values())}
    # Pre-registered labels: all fights, score.
    for x, y in PRIMARY:
        result["labels"][f"{x}-{y}"] = label(result["contrasts"][f"{x}-{y}/all/score"], "G6_HELPS", "G6_HURTS")
    for x, y in ITERATION:
        result["labels"][f"{x}-{y}"] = label(result["contrasts"][f"{x}-{y}/all/score"], "G6_BETTER", "G6_WORSE")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("validFights", "sourceSeeds", "excluded", "truncatedRows", "shards",
                                             "roomClasses", "labels",
                                             "cpuPerFightVsPlainSameBudget")}))
    for k, v in result["contrasts"].items():
        if "/all/" in k or "/boss/" in k:
            print(f"{k}: {v['mean']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] n={v['fights']}")


if __name__ == "__main__":
    main()
