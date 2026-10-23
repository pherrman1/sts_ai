#!/usr/bin/env python3
"""Learned leaf head (silver-leaf-a20 head capped at win-now, 50/50 blend with the playout, 1 point per turn) vs
production Silver at A20 (leaf-value research step 3, fight-level A/B).

usage: python3 analyze.py OUT.json DIR [DIR ...]   (DIR: extracted worker tars; unit prefixes S-<seed>)

Copy of ../silver_maxbackup_ab_20261022/analyze.py with this A/B's arms (STS_CTMSILVER_ARMSET=leafhead), its
pre-registered labels and step-3 gate (PREREG.md) and descriptive additions: act subsets, decisions per fight and
stalls (fights where head10000 takes more than twice base10000's decisions). Original §479 description:

Reads every `*.states.csv`, `*.arms.csv` and `*.samples.csv` written by
`one_combat ctmsilvergen N 20 ...` with STS_CTMSILVER_ARMSET=rollout479 under the given
directories. Fight score, pairing, bootstrap and exclusions as §476 (`analyze_476.py`): per
replicate 0 on death, else 53 + curHp + 11 * potionCount + 0.25 * gold + 2 * maxHp; arm value per fight is the
replicate mean; contrasts are paired per fight; 95% CIs are a bootstrap over source seeds
(10,000 resamples, RNG seed 0). A fight counts only when every arm row is valid and every arm
has R = 2 replicates. The harness marks an escaped replicate (Smoke Bomb, fleeing enemy) invalid, so
a fight with an escape in any arm is excluded; excluded fights are counted by root reason (the
first quarantine reason other than `control_state_invalid`) and ESCAPE replicates are counted per
arm over all replayed fights. Also per arm: CPU per fight, CPU per simulation (sum cpuSeconds / sum
simulations), mean rollout length (sum rolloutActions / sum rolloutPlayouts) and playouts per
simulation, over valid fights only; CPU ratios get the same seed bootstrap.
"""
import csv
import glob
import json
import os
import random
import sys
from collections import defaultdict

R = 2
ARMS = ["base10000", "base12000", "base15000", "head10000"]
CANDIDATE = "head10000"
MATCH_CANDIDATES = ("base12000", "base15000")
# Pre-registered labels: (x, y, positive label, negative label); all fights, score.
LABELED = []   # the headroom label is computed separately (HEADROOM_BAR below)
DESCRIPTIVE = [(CANDIDATE, "base10000")] + [(CANDIDATE, b) for b in MATCH_CANDIDATES] \
    + [(b, "base10000") for b in MATCH_CANDIDATES]
# Pre-registered (PREREG.md): labels on head10000 - base10000 (primary) and head10000 - matched (CPU-matched),
# all fights, score and HP lost.
# CPU-ratio contrasts (x / y): per simulation and per fight.
CPU_RATIOS = [(CANDIDATE, "base10000")] + [(b, "base10000") for b in MATCH_CANDIDATES] \
    + [(CANDIDATE, b) for b in MATCH_CANDIDATES]
METRICS = ("score", "win", "hpLoss", "decisions")   # decisions: descriptive
CPU_MATCH_MAX = 1.10
GATE_SCORE_FLOOR = -1.0   # step-3 gate: head10000 - matched score, all fights, CI lower bound above this
STALL_FACTOR = 2.0        # descriptive: head10000 takes more than this times base10000's decisions in a fight


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
    work = defaultdict(lambda: [0.0, 0, 0, 0, 0])   # (stateId, arm) -> cpuSeconds, simulations, playouts, actions, decisions
    shards, reasons = [], defaultdict(lambda: defaultdict(int))   # stateId -> quarantineReason -> rows
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.states.csv"), recursive=True)):
            prefix = path[: -len(".states.csv")]
            for r in rows(path):
                if r["stateId"] in states:
                    raise SystemExit(f"duplicate state {r['stateId']}")
                states[r["stateId"]] = r
            for r in rows(prefix + ".arms.csv"):
                valid[r["stateId"]] = valid[r["stateId"]] and r["valid"] == "1"
                if r["valid"] != "1":
                    reasons[r["stateId"]][r["quarantineReason"] or "unspecified"] += 1
                cpu[r["arm"]].append(float(r["cpuSeconds"]))
                dec[r["arm"]] += int(r["decisions"])
                w = work[(r["stateId"], r["arm"])]
                w[0] += float(r["cpuSeconds"]); w[1] += int(r["simulations"])
                w[2] += int(r["rolloutPlayouts"]); w[3] += int(r["rolloutActions"]); w[4] += int(r["decisions"])
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
    return states, valid, cpu, dec, samples, shards, work, reasons


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


def boot_ratio(per_seed, n=10000, rng_seed=0):
    """per_seed: seed -> (num_x, den_x, num_y, den_y); statistic (sum num_x/sum den_x)/(sum num_y/sum den_y)."""
    seeds = sorted(per_seed)
    vals = [per_seed[s] for s in seeds]
    def stat(sample):
        a, b, c, d = (sum(v[i] for v in sample) for i in range(4))
        return (a / b) / (c / d) if b and c and d else float("nan")
    rng = random.Random(rng_seed)
    stats = sorted(stat([vals[rng.randrange(len(vals))] for _ in vals]) for _ in range(n))
    return stat(vals), stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def label(c, pos, neg):
    return pos if c["ci95"][0] > 0 else neg if c["ci95"][1] < 0 else "NOT_SHOWN"


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    states, valid, cpu, dec, samples, shards, work, reasons = load(dirs)
    missing = [a for a in ARMS if a not in cpu]
    if missing:
        raise SystemExit(f"missing arms: {missing}")
    over = {len(v) for (sid, a), v in samples.items() if a in ARMS and len(v) > R}
    if over:
        raise SystemExit(f"more than R={R} replicates per fight: {sorted(over)}")
    fights, excluded, escapes = {}, defaultdict(int), defaultdict(int)
    by_reason, rows_by_reason, escapes_all = defaultdict(int), defaultdict(int), defaultdict(int)
    for (sid, a), rs in samples.items():
        if a in ARMS:
            escapes_all[a] += sum(r["outcome"] == "ESCAPE" for r in rs)
    for sid, st in states.items():
        if not valid[sid]:
            excluded["invalid_arm_row"] += 1
            rs = reasons[sid]
            for k, v in rs.items():
                rows_by_reason[k] += v
            root = sorted(k for k in rs if k != "control_state_invalid") or ["control_state_invalid"]
            by_reason[root[0]] += 1
            continue
        pre = float(st["preHp"])
        per = {}
        for a in ARMS:
            rows = samples.get((sid, a), [])
            if len(rows) < R:
                excluded["incomplete_shard_abort"] += 1
                break
            dead = [r["outcome"] == "DEATH" for r in rows]
            escapes[a] += sum(r["outcome"] == "ESCAPE" for r in rows)
            per[a] = {"score": sum(map(score, rows)) / R,
                      "win": 1.0 - sum(dead) / R,
                      "hpLoss": sum(pre - (0.0 if d else float(r["curHp"])) for r, d in zip(rows, dead)) / R,
                      "decisions": work[(sid, a)][4] / R}
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
              "escapes": dict(escapes),
              "excludedFightsByRootReason": dict(by_reason),
              "invalidArmRowsByReason": dict(rows_by_reason),
              "escapeReplicatesAllFights": dict(escapes_all),
              "arms": {}, "contrasts": {}, "cpuRatios": {}, "labels": {}}
    for a in ARMS:
        w = [sum(work[(sid, a)][i] for sid in fights) for i in range(5)]
        result["arms"][a] = {k: sum(p[a][k] for _, p in fights.values()) / len(fights) for k in METRICS}
        result["arms"][a].update(cpuSecondsPerFight=w[0] / len(fights),
                                 cpuMicrosecondsPerSimulation=1e6 * w[0] / max(1, w[1]),
                                 meanRolloutLength=w[3] / max(1, w[2]),
                                 playoutsPerSimulation=w[2] / max(1, w[1]),
                                 decisionsPerFight=w[4] / len(fights))
    subsets = {"all": lambda st: True,
               "boss": lambda st: st["roomClass"] == "BOSS",
               "elite": lambda st: st["roomClass"] == "ELITE",
               "normal": lambda st: st["roomClass"] not in ("BOSS", "ELITE"),
               # Descriptive: Act-4 fights (sources where student C collected all keys by itself).
               "act4": lambda st: st["act"] == "4",
               # Descriptive (this A/B): the head was only tested on Act-1 first fights before.
               "act1": lambda st: st["act"] == "1", "act2": lambda st: st["act"] == "2",
               "act3": lambda st: st["act"] == "3"}
    for x, y in [(x, y) for x, y, _, _ in LABELED] + DESCRIPTIVE:
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
    for x, y in CPU_RATIOS:
        for kind, den in (("perSimulation", 1), ("perFight", None)):
            per_seed = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
            for sid, (st, _) in fights.items():
                v = per_seed[st["sourceSeed"]]
                v[0] += work[(sid, x)][0]; v[2] += work[(sid, y)][0]
                v[1] += work[(sid, x)][1] if den else 1; v[3] += work[(sid, y)][1] if den else 1
            m, lo, hi = boot_ratio(per_seed)
            result["cpuRatios"][f"{x}/{y}/{kind}"] = {"ratio": m, "ci95": [lo, hi]}
    # Pre-registered CPU match: the matched control is the smallest base arm in MATCH_CANDIDATES whose per-fight
    # CPU ratio head10000/base (point estimate) is <= CPU_MATCH_MAX. The "matched" labels compare head10000 with
    # it; with none matched they read NOT_MATCHED.
    matchedArm = next((y for y in MATCH_CANDIDATES
                       if result["cpuRatios"][f"{CANDIDATE}/{y}/perFight"]["ratio"] <= CPU_MATCH_MAX), None)
    result["cpuMatchedArm"] = matchedArm
    for key, y in (("base10000", "base10000"), ("matched", matchedArm)):
        if y is None:
            result["labels"][f"{CANDIDATE}-{key}/score"] = result["labels"][f"{CANDIDATE}-{key}/hpLoss"] = "NOT_MATCHED"
            continue
        c = result["contrasts"][f"{CANDIDATE}-{y}/all/score"]["ci95"]
        result["labels"][f"{CANDIDATE}-{key}/score"] = "BETTER" if c[0] > 0 else "WORSE" if c[1] < 0 else "NOT_SHOWN"
        c = result["contrasts"][f"{CANDIDATE}-{y}/all/hpLoss"]["ci95"]
        result["labels"][f"{CANDIDATE}-{key}/hpLoss"] = "BETTER" if c[1] < 0 else "WORSE" if c[0] > 0 else "NOT_SHOWN"
    # Pre-registered step-3 gate (decides only whether a whole-run A/B is proposed): the matched score contrast over
    # all fights has a CI lower bound above GATE_SCORE_FLOOR, and on boss fights neither the matched score nor the
    # matched HP-lost contrast is WORSE (score CI upper bound < 0, HP-lost CI lower bound > 0). NOT_MATCHED fails.
    if matchedArm is None:
        result["gate"] = {"pass": False, "reason": "NOT_MATCHED"}
    else:
        c_all = result["contrasts"][f"{CANDIDATE}-{matchedArm}/all/score"]["ci95"]
        c_bs = result["contrasts"].get(f"{CANDIDATE}-{matchedArm}/boss/score", {"ci95": [0.0, 0.0]})["ci95"]
        c_bh = result["contrasts"].get(f"{CANDIDATE}-{matchedArm}/boss/hpLoss", {"ci95": [0.0, 0.0]})["ci95"]
        checks = {"allScoreLowerAboveFloor": c_all[0] > GATE_SCORE_FLOOR,
                  "bossScoreNotWorse": not c_bs[1] < 0, "bossHpLossNotWorse": not c_bh[0] > 0}
        result["gate"] = {"pass": all(checks.values()), **checks}
    stalls = defaultdict(int)
    for st, p in fights.values():
        if p[CANDIDATE]["decisions"] > STALL_FACTOR * p["base10000"]["decisions"]:
            stalls["all"] += 1
            stalls[st["roomClass"]] += 1
    result["stallFights"] = dict(stalls)
    result["act4Fights"] = sum(1 for st, _ in fights.values() if st["act"] == "4")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("validFights", "sourceSeeds", "excluded", "truncatedRows", "shards",
                                             "roomClasses", "act4Fights", "labels", "gate", "stallFights",
                                             "cpuMatchedArm", "cpuRatios", "escapes",
                                             "excludedFightsByRootReason", "invalidArmRowsByReason",
                                             "escapeReplicatesAllFights")}))
    for a, v in result["arms"].items():
        print(a, {k: round(x, 3) for k, x in v.items()})
    for k, v in result["contrasts"].items():
        if any(f"/{s}/" in k for s in ("all", "boss", "elite", "normal", "act1", "act2", "act3", "act4")):
            print(f"{k}: {v['mean']:+.3f} [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] n={v['fights']}")


if __name__ == "__main__":
    main()
