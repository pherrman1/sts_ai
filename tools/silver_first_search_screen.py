#!/usr/bin/env python3
"""Screen: is the first Silver search's endpoint distribution a good combat-outcome forecast?

Philipp's idea (2026-10-18): a 10k-simulation Silver search at the start of a fight
produces 10k simulated outcomes; their HP distribution may approximate what the CTM
tries to predict. Rows come from `combattransitiongen` with STS_CTM_ROW_FIRST_SEARCH=1
(every row: firstSearch.root / firstSearch.best endpoint histograms, battleEnd = the
realized fight on the same pre-heal scale). CTM forecasts come from `one_combat
ctmscorerows` on the same rows (calibrated A20 stack).

Forecasters, each scored against the realized outcome of the same fight:
  ctm         pre-combat CTM (no opening hand), against RAW post HP (after heals)
  silverRoot  all simulations of the first search, against battle-end HP (before heals)
  silverBest  simulations through the chosen root edge, same scale

Scale note: Silver and the CTM are scored on their own HP scale (before vs after
post-combat heals); death and HP-lost errors are comparable, absolute HP shifts by
the heal. Silver sees the opening hand (its search starts after the draw), the CTM
does not, so Silver has an information advantage the OOC planner cannot use.

    python3 tools/silver_first_search_screen.py --rows 'OUT/*.jsonl' --ctm 'OUT/*.ctm.csv' --out REPORT.json
"""
import argparse
import csv
import glob
import json
import math

import numpy as np


def layer_stats(layer, max_hp, alpha=0.5):
    """(pDeath, mean win HP, log-prob function) from a SilverOutcomeCapture layer."""
    count = layer["count"]
    if count <= 0:
        return None
    deaths = layer["deaths"]
    counts = np.zeros(max_hp + 1)
    for hp, c in enumerate(layer["hpCounts"]):
        if hp >= 1:
            counts[min(hp, max_hp)] += c
    wins = counts.sum()
    p_death = deaths / count
    mean_win = float((counts * np.arange(max_hp + 1)).sum() / wins) if wins > 0 else 0.0
    smoothed = counts[1:] + alpha  # add-alpha over 1..maxHp so every HP has mass
    smoothed /= smoothed.sum()

    def log_p_win_hp(hp):
        return float(math.log(smoothed[min(max(hp, 1), max_hp) - 1]))

    return p_death, mean_win, log_p_win_hp


def boot(per_seed_rows, reps=2000, seed=0):
    keys = list(per_seed_rows)
    rng = np.random.default_rng(seed)
    sums = np.array([per_seed_rows[k][0] for k in keys])
    cnts = np.array([per_seed_rows[k][1] for k in keys])
    stats = []
    for _ in range(reps):
        idx = rng.integers(0, len(keys), len(keys))
        stats.append(sums[idx].sum() / max(1, cnts[idx].sum()))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def summarize(values, seeds):
    values = np.asarray(values, float)
    by_seed = {}
    for v, s in zip(values, seeds):
        a = by_seed.setdefault(s, [0.0, 0])
        a[0] += v
        a[1] += 1
    lo, hi = boot(by_seed) if len(by_seed) > 1 else (float("nan"), float("nan"))
    return {"n": int(len(values)), "mean": float(values.mean()) if len(values) else float("nan"),
            "ci95": [lo, hi]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--ctm", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ctm = {}
    for path in sorted(glob.glob(args.ctm)):
        with open(path) as f:
            for r in csv.DictReader(f):
                if r["scored"] == "1":
                    ctm[(int(r["source_seed"]), int(r["fight_idx"]))] = r
    rows = []
    for path in sorted(glob.glob(args.rows)):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                t, fs, be = r.get("transition"), r.get("firstSearch"), r.get("battleEnd")
                if t is None or not r["runValid"] or fs is None or be is None:
                    continue
                if t["combatOutcome"] not in (1, 2) or t["post"]["smokeBombUsed"]:
                    continue
                c = ctm.get((r["sourceSeed"], r["fightIdx"]))
                if c is None or fs["skipped"] or fs["inheritedVisits"] != 0:
                    continue
                rows.append((r, c))

    names = ["ctm", "silverRoot", "silverBest"]
    brier = {k: [] for k in names}
    logloss = {k: [] for k in names}
    hp_err = {k: [] for k in names}      # predicted mean win HP lost - realized HP lost (wins only)
    hp_logp = {k: [] for k in names}     # log p(realized HP | win), wins only
    seeds_all, seeds_win = [], []
    for r, c in rows:
        t, fs, be = r["transition"], r["firstSearch"], r["battleEnd"]
        died = t["combatOutcome"] == 2
        pre_hp = t["pre"]["curHp"]
        max_hp = max(be["maxHp"], t["post"]["maxHp"], pre_hp, 1)
        fc = {"ctm": (float(c["p_death"]), float(c["expected_win_hp"]),
                      None if died else float(c["log_p_post_hp"]))}
        for k, layer in (("silverRoot", fs["root"]), ("silverBest", fs["best"])):
            st = layer_stats(layer, max_hp)
            if st is None:
                break
            fc[k] = (st[0], st[1], None if died else st[2](be["hp"]))
        if len(fc) != 3:
            continue
        seeds_all.append(r["sourceSeed"])
        for k in names:
            p = min(max(fc[k][0], 1e-3), 1 - 1e-3)
            brier[k].append((fc[k][0] - died) ** 2)
            logloss[k].append(-(math.log(p) if died else math.log(1 - p)))
        if not died:
            seeds_win.append(r["sourceSeed"])
            hp_err["ctm"].append((pre_hp - fc["ctm"][1]) - (pre_hp - t["post"]["curHp"]))
            for k in ("silverRoot", "silverBest"):
                hp_err[k].append((pre_hp - fc[k][1]) - (pre_hp - be["hp"]))
            for k in names:
                hp_logp[k].append(fc[k][2])

    rep = {"states": len(seeds_all), "wins": len(seeds_win),
           "deaths": int(sum(1 for r, _ in rows if r["transition"]["combatOutcome"] == 2)),
           "seeds": len(set(seeds_all))}
    for k in names:
        e = np.asarray(hp_err[k])
        rep[k] = {"deathBrier": summarize(brier[k], seeds_all), "deathLogLoss": summarize(logloss[k], seeds_all),
                  "winHpLostBias": summarize(e, seeds_win),
                  "winHpLostRmse": float(np.sqrt((e ** 2).mean())) if len(e) else float("nan"),
                  "winHpLogScore": summarize(hp_logp[k], seeds_win)}
    for k in ("silverRoot", "silverBest"):
        rep[f"{k}_minus_ctm"] = {
            "deathBrier": summarize(np.subtract(brier[k], brier["ctm"]), seeds_all),
            "winHpSqErr": summarize(np.subtract(np.square(hp_err[k]), np.square(hp_err["ctm"])), seeds_win),
            "winHpLogScore": summarize(np.subtract(hp_logp[k], hp_logp["ctm"]), seeds_win)}
    with open(args.out, "w") as f:
        json.dump(rep, f, indent=2)
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
