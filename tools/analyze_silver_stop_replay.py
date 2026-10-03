#!/usr/bin/env python3
"""Pre-registered analysis of the learned-stop replay A/B (silverstopreplaygen).

Input: shard prefixes (PREFIX.arms.csv). A fight counts when the control
replay matched the source fight. An invalid adaptive199 or learned result in
such a fight (escape, turn cap, non-death loss) scores signedOutcome -1 and
won 0 for that arm; per-arm invalid counts are reported.

Primary (learned vs adaptive199, the production #199 policy):
  S = 1 - sum(simulations learned) / sum(simulations adaptive199)
  D = mean over fights of signedOutcome(learned) - signedOutcome(adaptive199),
      95% source-seed-clustered bootstrap (2,000 replicates, seed 0)
Verdict:
  LEARNED_STOP_PASS           S >= 0.10, CI lower bound of D > -0.005, and no
                              more learned-only than adaptive199-only invalid
                              fights
  LEARNED_STOP_COMPUTE_FAIL   S < 0.10
  LEARNED_STOP_QUALITY_FAIL   otherwise (non-inferiority not shown)
Secondary, descriptive: every arm against control (flat 10k), win rates,
potions, CPU, and the same deltas by room class.
"""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict

ARMS = ["control", "adaptive199", "learned"]
MIN_SAVING = 0.10
MARGIN = -0.005
REPS = 2000


def load(prefixes):
    fights = defaultdict(dict)
    rooms = {}
    for prefix in prefixes:
        with open(prefix + ".arms.csv", newline="") as f:
            for row in csv.DictReader(f):
                fights[row["stateId"]][row["arm"]] = row
        with open(prefix + ".states.csv", newline="") as f:
            for row in csv.DictReader(f):
                rooms[row["stateId"]] = row["roomClass"]
    valid, excluded = [], defaultdict(int)
    arm_invalid = {a: 0 for a in ARMS[1:]}
    only_invalid = {a: 0 for a in ARMS[1:]}
    for sid, arms in fights.items():
        if set(arms) != set(ARMS):
            excluded["missing_arm"] += 1
            continue
        # The fight counts when the control replay matched; an invalid
        # adaptive199/learned result (escape, turn cap, non-death loss) is that
        # arm's own outcome and scores as a loss with signedOutcome -1.
        if arms["control"]["valid"] != "1":
            excluded[arms["control"]["quarantineReason"] or "control_invalid"] += 1
            continue
        bad = {a: arms[a]["valid"] != "1" for a in ARMS[1:]}
        for a in ARMS[1:]:
            arm_invalid[a] += bad[a]
            only_invalid[a] += bad[a] and not any(bad[b] for b in ARMS[1:] if b != a)
        row = {"seed": int(arms["control"]["sourceSeed"]), "room": rooms.get(sid, "?")}
        for a in ARMS:
            invalid = a != "control" and bad[a]
            row[f"q_{a}"] = -1.0 if invalid else float(arms[a]["signedOutcome"])
            row[f"won_{a}"] = 0 if invalid else int(arms[a]["won"])
            row[f"sims_{a}"] = int(arms[a]["simulations"])
            row[f"cpu_{a}"] = float(arms[a]["cpuSeconds"])
            row[f"pot_{a}"] = int(arms[a]["potionsAfter"])
        valid.append(row)
    excluded["armInvalid"] = arm_invalid
    excluded["armOnlyInvalid"] = only_invalid
    return valid, dict(excluded), len(fights)


def bootstrap(rows, stat):
    by_seed = defaultdict(list)
    for r in rows:
        by_seed[r["seed"]].append(r)
    seeds = sorted(by_seed)
    rng = random.Random(0)
    values = []
    for _ in range(REPS):
        sample = [r for s in (rng.choice(seeds) for _ in seeds) for r in by_seed[s]]
        values.append(stat(sample))
    values.sort()
    return [values[int(0.025 * REPS)], values[int(0.975 * REPS) - 1]]


def delta(rows, a, b, key="q"):
    return sum(r[f"{key}_{a}"] - r[f"{key}_{b}"] for r in rows) / len(rows) if rows else 0.0


def saving(rows, a, b):
    sb = sum(r[f"sims_{b}"] for r in rows)
    return 1 - sum(r[f"sims_{a}"] for r in rows) / sb if sb else 0.0


def compare(rows, a, b):
    return {
        "n": len(rows),
        "signedOutcome": delta(rows, a, b), "signedOutcomeCI": bootstrap(rows, lambda x: delta(x, a, b)),
        "winRate": delta(rows, a, b, "won"), "potionsAfter": delta(rows, a, b, "pot"),
        "simulationSaving": saving(rows, a, b),
        "cpuRatio": (sum(r[f"cpu_{a}"] for r in rows) / sum(r[f"cpu_{b}"] for r in rows)) if rows else 0.0,
    }


def analyze(prefixes):
    rows, excluded, total = load(prefixes)
    primary = compare(rows, "learned", "adaptive199")
    primary["simulationSavingCI"] = bootstrap(rows, lambda x: saving(x, "learned", "adaptive199"))
    s, lo = primary["simulationSaving"], primary["signedOutcomeCI"][0]
    only = excluded["armOnlyInvalid"]
    verdict = ("LEARNED_STOP_COMPUTE_FAIL" if s < MIN_SAVING
               else "LEARNED_STOP_PASS" if lo > MARGIN and only["learned"] <= only["adaptive199"]
               else "LEARNED_STOP_QUALITY_FAIL")
    secondary = {f"{a}_vs_control": compare(rows, a, "control") for a in ("adaptive199", "learned")}
    by_room = {}
    for room in sorted({r["room"] for r in rows}):
        sub = [r for r in rows if r["room"] == room]
        by_room[room] = {"learned_vs_adaptive199": compare(sub, "learned", "adaptive199"),
                         "learned_vs_control": compare(sub, "learned", "control")}
    return {"verdict": verdict, "rule": {"minSaving": MIN_SAVING, "margin": MARGIN, "reps": REPS},
            "fights": total, "validFights": len(rows), "sourceSeeds": len({r["seed"] for r in rows}),
            "excluded": excluded, "primary": primary, "secondary": secondary, "byRoom": by_room,
            "inputs": prefixes}


def selftest():
    import os
    import tempfile
    d = tempfile.mkdtemp()
    prefix = os.path.join(d, "t")
    with open(prefix + ".states.csv", "w") as f:
        f.write("stateId,roomClass\n")
        for i in range(40):
            f.write(f"s{i},NORMAL\n")
    with open(prefix + ".arms.csv", "w") as f:
        f.write("stateId,sourceSeed,arm,won,signedOutcome,potionsAfter,cpuSeconds,simulations,valid,quarantineReason\n")
        for i in range(40):
            for arm, sims, q in (("control", 100, 0.5), ("adaptive199", 60, 0.5), ("learned", 40, 0.5 - 0.001 * (i % 2))):
                f.write(f"s{i},{i % 10},{arm},1,{q},1,1.0,{sims},1,\n")
    out = analyze([prefix])
    assert out["validFights"] == 40 and abs(out["primary"]["simulationSaving"] - 1 / 3) < 1e-12
    assert abs(out["primary"]["signedOutcome"] + 0.0005) < 1e-12 and out["verdict"] == "LEARNED_STOP_PASS"
    # One learned-only escape: scored -1 and PASS becomes impossible.
    prefix2 = os.path.join(d, "u")
    with open(prefix2 + ".states.csv", "w") as f:
        f.write("stateId,roomClass\n")
        for i in range(40):
            f.write(f"s{i},NORMAL\n")
    with open(prefix2 + ".arms.csv", "w") as f:
        f.write("stateId,sourceSeed,arm,won,signedOutcome,potionsAfter,cpuSeconds,simulations,valid,quarantineReason\n")
        for i in range(40):
            for arm, sims in (("control", 100), ("adaptive199", 60), ("learned", 40)):
                bad = arm == "learned" and i == 0
                f.write(f"s{i},{i % 10},{arm},{-1 if bad else 1},0.5,1,1.0,{sims},{0 if bad else 1},{'escape' if bad else ''}\n")
    out = analyze([prefix2])
    assert out["validFights"] == 40 and out["excluded"]["armOnlyInvalid"] == {"adaptive199": 0, "learned": 1}
    assert abs(out["primary"]["signedOutcome"] + 1.5 / 40) < 1e-12 and out["verdict"] == "LEARNED_STOP_QUALITY_FAIL"
    print("selftest ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prefixes", nargs="*")
    p.add_argument("--out")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return selftest()
    report = analyze(args.prefixes)
    text = json.dumps(report, indent=1)
    if args.out:
        open(args.out, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
