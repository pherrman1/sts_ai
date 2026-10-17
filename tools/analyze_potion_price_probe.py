#!/usr/bin/env python3
"""Analyze potionpriceprobe CSVs: paired resource prices in HP equivalents.

For each sampled state, the price of a variant is value(base) - value(variant)
for one value column. The HP variant (hp:-D) gives the state's value of D HP.
A potion's HP-equivalent price is the ratio of means
mean(potion delta) / mean(HP delta / D), with a bootstrap over source seeds
(states of one seed are resampled together).

Usage: analyze_potion_price_probe.py OUT.json CSV [CSV ...]
"""
import csv
import json
import random
import sys
from collections import defaultdict

VALUE_COLUMNS = ("altFloor", "floorValue", "altWon", "won")
BOOT = 2000


def load(paths):
    states = defaultdict(dict)  # (seed, battleIdx) -> variant -> row
    invalid = 0
    for path in paths:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if row["valid"] != "1":
                    invalid += 1
                    continue
                states[(int(row["seed"]), int(row["battleIdx"]))][row["variant"]] = row
    return states, invalid


def deltas(states, column):
    """seed -> list of (hpSlopePerHp or None, {potion: delta})."""
    per_seed = defaultdict(list)
    for (seed, _), variants in states.items():
        base = variants.get("base")
        if base is None:
            continue
        v0 = float(base[column])
        slope = None
        pots = {}
        for name, row in variants.items():
            if name.startswith("hp:-"):
                slope = (v0 - float(row[column])) / int(name[4:])
            elif name.startswith("pot:"):
                pots[name[4:]] = v0 - float(row[column])
        per_seed[seed].append((slope, pots))
    return per_seed


def summarize(per_seed, seeds):
    hp, pot = [], defaultdict(list)
    for s in seeds:
        for slope, pots in per_seed[s]:
            if slope is not None:
                hp.append(slope)
            for name, d in pots.items():
                pot[name].append(d)
                pot["ALL"].append(d)
    return hp, pot


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def ci(xs):
    xs = sorted(x for x in xs if x == x)
    if not xs:
        return [None, None]
    return [xs[int(0.025 * (len(xs) - 1))], xs[int(0.975 * (len(xs) - 1))]]


def analyze(per_seed):
    seeds = sorted(per_seed)
    hp, pot = summarize(per_seed, seeds)
    hp_mean = mean(hp)
    rng = random.Random(20261017)
    boot_hp, boot_delta, boot_eq = [], defaultdict(list), defaultdict(list)
    for _ in range(BOOT):
        sample = [rng.choice(seeds) for _ in seeds]
        bhp, bpot = summarize(per_seed, sample)
        m = mean(bhp)
        boot_hp.append(m)
        for name, xs in bpot.items():
            d = mean(xs)
            boot_delta[name].append(d)
            boot_eq[name].append(d / m if m and m > 0 else float("nan"))
    potions = {}
    for name, xs in sorted(pot.items(), key=lambda kv: -len(kv[1])):
        d = mean(xs)
        potions[name] = {
            "n": len(xs),
            "delta": d,
            "deltaCI": ci(boot_delta[name]),
            "hpEq": d / hp_mean if hp_mean and hp_mean > 0 else None,
            "hpEqCI": ci(boot_eq[name]),
        }
    return {"seeds": len(seeds), "states": sum(len(v) for v in per_seed.values()),
            "hpSlope": {"n": len(hp), "perHp": hp_mean, "CI": ci(boot_hp)},
            "potions": potions}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    states, invalid = load(sys.argv[2:])
    result = {"invalidRows": invalid}
    for column in VALUE_COLUMNS:
        result[column] = analyze(deltas(states, column))
    with open(sys.argv[1], "w") as f:
        json.dump(result, f, indent=1)
    for column in VALUE_COLUMNS:
        r = result[column]
        print(f"== {column}: seeds {r['seeds']} states {r['states']} value per HP "
              f"{r['hpSlope']['perHp']:.5f} CI {r['hpSlope']['CI']}")
        for name, p in r["potions"].items():
            eq = "nan" if p["hpEq"] is None else f"{p['hpEq']:.1f}"
            print(f"  {name:24s} n={p['n']:4d} delta={p['delta']:+.4f} HP-eq={eq} CI={p['hpEqCI']}")


if __name__ == "__main__":
    main()
