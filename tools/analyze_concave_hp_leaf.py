#!/usr/bin/env python3
"""Analyze the concave-HP Silver leaf probe (docs/experiments/evidence/silver_concave_hp_leaf_20261018).

Each unit is one potionpriceprobe source run. Every sampled battle-start state is continued for 3 fights
by several copies that share all RNG and policy state: base, leaf:concave=K (Silver uses the concave-HP
leaf in those fights), hp:-12, gold:-50, maxhp:-5, pot:<TYPE>. The leaf effect of a state is
value(leaf copy) - value(base); resource prices are value(base) - value(variant).

Primary: mean leaf effect on altFloor (A20 floor model) for K=2.7, seed-clustered bootstrap 95% CI
(10,000 resamples, RNG 534). BETTER if the lower bound > 0, WORSE if the upper bound < 0, else NOT_SHOWN.
The result is INVALID unless every cohort seed has rc=0, a CSV, the frozen env and the frozen command.

Usage: analyze_concave_hp_leaf.py CAMPAIGN_DIR OUT.json ROOT [ROOT ...]
  ROOT: extracted worker tars or unit dirs (searched recursively for s<seed>.csv/.done/.env/.log).
  analyze_concave_hp_leaf.py --self-test
"""
import csv
import json
import os
import random
import sys
from collections import defaultdict

PRIMARY_K = "2.7"
SECONDARY_K = "1.35"
EXTRA = "extra=leaf:concave=2.7,leaf:concave=1.35,gold:-50,maxhp:-5,ooc=heart1"
BOOT = int(os.environ.get("CONCAVE_BOOT", 10000))
SEED_RNG = 534
COLUMNS = ("altFloor", "altWon", "won", "floorValue", "survived", "hp")


def find_files(roots):
    files = {}
    for root in roots:
        for dirpath, _, names in os.walk(root):
            for name in names:
                if name.startswith("s") and "." in name:
                    seed, ext = name[1:].split(".", 1)
                    if seed.isdigit():
                        files.setdefault(int(seed), {})[ext] = os.path.join(dirpath, name)
    return files


def check_unit(seed, f):
    """Returns a list of validity problems for one cohort seed."""
    problems = []
    for ext in ("csv", "done", "env", "log"):
        if ext not in f:
            problems.append(f"{seed}: missing .{ext}")
    if problems:
        return problems
    done = open(f["done"]).read()
    if " rc=0 " not in done + " ":
        problems.append(f"{seed}: {done.strip()}")
    env = dict(line.strip().split("=", 1) for line in open(f["env"]) if "=" in line)
    if not env.get("STS_OOC_HEART1", "").endswith("/student_sel.bin") or env.get("STS_OOC_MCTS") != "0":
        problems.append(f"{seed}: env is not the frozen student_sel / OOC-MCTS-off env")
    if any(k == "STS_SILVER_CONCAVE_HP_LEAF" for k in env):
        problems.append(f"{seed}: env sets STS_SILVER_CONCAVE_HP_LEAF")
    log = open(f["log"], errors="replace").read()
    if EXTRA not in log or "sample=all" not in log or "[heart1] loaded" not in log:
        problems.append(f"{seed}: log lacks the frozen command or the student load line")
    return problems


def load_states(files, seeds):
    states = defaultdict(dict)  # (seed, battleIdx) -> variant -> row
    invalid = 0
    for seed in seeds:
        with open(files[seed]["csv"], newline="") as fh:
            for row in csv.DictReader(fh):
                if row["valid"] != "1":
                    invalid += 1
                    continue
                states[(seed, int(row["battleIdx"]))][row["variant"]] = row
    # The observer also fires on the source run's final (terminal) state; its base copy runs no fight.
    terminal = [k for k, v in states.items()
                if "base" in v and (v["base"]["silverSimulations"] == "0" or v["base"]["curHp"] == "0")]
    for k in terminal:
        del states[k]
    return states, invalid, len(terminal)


def bootstrap(per_seed, stat):
    """per_seed: seed -> list of items; stat(list of items) -> float. Seed-clustered percentile CI."""
    seeds = sorted(s for s in per_seed if per_seed[s])
    if not seeds:
        return {"estimate": None, "CI": None, "n": 0, "seeds": 0}
    rng = random.Random(SEED_RNG)
    try:
        est = stat([x for s in seeds for x in per_seed[s]])
    except ZeroDivisionError:
        return {"estimate": None, "CI": None, "n": sum(len(per_seed[s]) for s in seeds), "seeds": len(seeds)}
    reps = []
    for _ in range(BOOT):
        sample = [x for _ in seeds for x in per_seed[rng.choice(seeds)]]
        try:
            reps.append(stat(sample))
        except ZeroDivisionError:
            pass
    reps.sort()
    ci = [reps[int(0.025 * len(reps))], reps[int(0.975 * len(reps)) - 1]] if reps else None
    return {"estimate": est, "CI": ci,
            "n": sum(len(v) for v in per_seed.values()), "seeds": len(seeds)}


def mean(xs):
    return sum(xs) / len(xs)


def label(ci):
    return "BETTER" if ci[0] > 0 else "WORSE" if ci[1] < 0 else "NOT_SHOWN"


def leaf_effects(states, k, column, select=lambda base: True):
    per_seed = defaultdict(list)
    name = "leaf:concave=" + k
    for (seed, _), v in states.items():
        if "base" in v and name in v and select(v["base"]):
            per_seed[seed].append(float(v[name][column]) - float(v["base"][column]))
    return per_seed


def hp_fraction(row):
    return int(row["curHp"]) / max(1, int(row["maxHp"]))


def prices(states, column):
    """HP-equivalent prices of gold:-50, maxhp:-5 and non-Fairy potions (ratio of means over states)."""
    per_seed = defaultdict(list)
    for (seed, _), v in states.items():
        base = v.get("base")
        if base is None:
            continue
        b = float(base[column])
        item = {}
        for name, row in v.items():
            if name.startswith(("hp:-", "gold:-", "maxhp:-")) or (name.startswith("pot:") and "FAIRY" not in name):
                item.setdefault(name.split(":")[0], []).append(b - float(row[column]))
        per_seed[seed].append(item)

    def ratio(kind, unit):
        def stat(items):
            hp = [d for it in items for d in it.get("hp", [])]
            other = [d for it in items for d in it.get(kind, [])]
            return (mean(other) / unit) / (mean(hp) / 12)
        return stat
    out = {"hpPerHp": bootstrap(per_seed, lambda items: mean([d for it in items for d in it.get("hp", [])]) / 12)}
    out["goldPerGoldInHp"] = bootstrap(per_seed, ratio("gold", 50))
    out["maxHpPerPointInHp"] = bootstrap(per_seed, ratio("maxhp", 5))
    out["potionNonFairyInHp"] = bootstrap(per_seed, ratio("pot", 1))
    return out


def analyze(campaign, roots):
    cohort = [int(line.split()[0]) for line in open(os.path.join(campaign, "units.txt"))
              if line.strip() and not line.startswith("#")]
    files = find_files(roots)
    problems = [p for s in cohort for p in check_unit(s, files.get(s, {}))]
    extra_seeds = sorted(set(files) - set(cohort))
    if extra_seeds:
        problems.append(f"non-cohort seeds present: {extra_seeds[:10]}")
    result = {"cohortSeeds": len(cohort), "problems": problems, "valid": not problems}
    if problems:
        result["label"] = "INVALID"
        return result
    states, invalid, terminal = load_states(files, cohort)
    result.update({"invalidRows": invalid, "terminalStatesDropped": terminal, "states": len(states)})
    primary = bootstrap(leaf_effects(states, PRIMARY_K, "altFloor"), mean)
    primary["label"] = label(primary["CI"])
    result["primary"] = {"contrast": f"leaf:concave={PRIMARY_K} - base, altFloor", **primary}
    result["label"] = primary["label"]
    secondary = bootstrap(leaf_effects(states, SECONDARY_K, "altFloor"), mean)
    secondary["label"] = label(secondary["CI"])
    result["secondary"] = {"contrast": f"leaf:concave={SECONDARY_K} - base, altFloor", **secondary}
    desc = {}
    for k in (PRIMARY_K, SECONDARY_K):
        d = {}
        for col in ("altWon", "won", "survived", "hp"):
            d[col] = bootstrap(leaf_effects(states, k, col), mean)
        bands = {}
        for lo, hi in ((0, 0.45), (0.45, 0.75), (0.75, 0.9), (0.9, 1.01)):
            bands[f"{lo}-{hi}"] = bootstrap(
                leaf_effects(states, k, "altFloor", lambda b, lo=lo, hi=hi: lo <= hp_fraction(b) < hi), mean)
        d["altFloorByStartHpFraction"] = bands
        for act in ("1", "2", "3"):
            d[f"altFloorAct{act}"] = bootstrap(leaf_effects(states, k, "altFloor", lambda b, a=act: b["act"] == a), mean)
        identical = sum(1 for v in states.values() if "base" in v and f"leaf:concave={k}" in v
                        and v["base"]["altFloor"] == v[f"leaf:concave={k}"]["altFloor"]
                        and v["base"]["hp"] == v[f"leaf:concave={k}"]["hp"])
        d["pairsWithIdenticalOutcome"] = identical
        desc["leaf:concave=" + k] = d
    result["descriptive"] = desc
    result["prices"] = {col: prices(states, col) for col in ("altFloor", "altWon")}
    return result


def self_test():
    import tempfile
    t = tempfile.mkdtemp()
    camp = os.path.join(t, "camp")
    os.makedirs(camp)
    open(os.path.join(camp, "units.txt"), "w").write("101\n102\n")
    head = ("seed,battleIdx,act,floor,curHp,maxHp,potionCount,potionCapacity,potions,variant,contSeed,won,"
            "floorValue,hp,bootstrapped,survived,altWon,altFloor,valid,silverSimulations,cpuMs,gold\n")
    for seed, gain in ((101, 1.0), (102, 0.5)):
        u = os.path.join(t, "out", f"u{seed}")
        os.makedirs(u)
        rows = []
        for b in (1, 2):
            for var, f in (("base", 30), ("leaf:concave=2.7", 30 + gain), ("leaf:concave=1.35", 30),
                           ("hp:-12", 29), ("gold:-50", 29.9), ("maxhp:-5", 29.5), ("pot:FIRE_POTION", 29.2)):
                rows.append(f"{seed},{b},1,{b + 5},60,80,1,3,FIRE_POTION,{var},1,0.1,30,50,1,1,0.1,{f},1,1000,1,99\n")
        open(os.path.join(u, f"s{seed}.csv"), "w").write(head + "".join(rows))
        open(os.path.join(u, f"s{seed}.done"), "w").write(f"tag=s{seed} rc=0 start=x end=y\n")
        open(os.path.join(u, f"s{seed}.env"), "w").write("STS_OOC_HEART1=/r/student_sel.bin\nSTS_OOC_MCTS=0\n")
        open(os.path.join(u, f"s{seed}.log"), "w").write(f"[heart1] loaded x\nsample=all {EXTRA} -> o\n")
    r = analyze(camp, [os.path.join(t, "out")])
    assert r["valid"] and r["label"] == "BETTER", r
    assert abs(r["primary"]["estimate"] - 0.75) < 1e-9, r["primary"]
    assert r["secondary"]["label"] == "NOT_SHOWN"
    p = r["prices"]["altFloor"]
    assert abs(p["hpPerHp"]["estimate"] - 1 / 12) < 1e-9
    assert abs(p["potionNonFairyInHp"]["estimate"] - 0.8 * 12) < 1e-9
    assert abs(p["maxHpPerPointInHp"]["estimate"] - 0.1 * 12) < 1e-9
    assert abs(p["goldPerGoldInHp"]["estimate"] - 0.002 * 12) < 1e-9
    open(os.path.join(t, "out", "u102", "s102.done"), "w").write("tag=s102 rc=124 start=x end=y\n")
    assert analyze(camp, [os.path.join(t, "out")])["label"] == "INVALID"
    open(os.path.join(t, "out", "u102", "s102.done"), "w").write("tag=s102 rc=0 start=x end=y\n")
    open(os.path.join(t, "out", "u102", "s102.env"), "a").write("STS_SILVER_CONCAVE_HP_LEAF=2.7\n")
    assert analyze(camp, [os.path.join(t, "out")])["label"] == "INVALID"
    print("self-test ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    res = analyze(sys.argv[1], sys.argv[3:])
    with open(sys.argv[2], "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps({k: res.get(k) for k in ("label", "states", "problems")}, indent=1))
    for key in ("primary", "secondary"):
        if key in res:
            print(key, res[key]["contrast"], round(res[key]["estimate"], 4),
                  [round(x, 4) for x in res[key]["CI"]], res[key]["label"])
