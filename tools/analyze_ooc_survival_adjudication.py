#!/usr/bin/env python3
"""Analyze paired full-run adjudication of targeted OOC tradeoff pairs."""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import median


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets_csv")
    ap.add_argument("adjudication_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--replicates", type=int, required=True)
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(args.targets_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_targets = {"seed", "decIdx", "act", "floor", "screen",
                            "safeBits", "strengthBits"}
        missing = required_targets - set(reader.fieldnames or ())
        if missing:
            raise SystemExit(f"missing target columns: {sorted(missing)}")
        targets = list(reader)
    target_keys = [(int(r["seed"]), int(r["decIdx"])) for r in targets]
    if len(set(target_keys)) != len(target_keys):
        raise SystemExit("duplicate target decision key")
    rows_by_key = defaultdict(lambda: defaultdict(dict))
    with open(args.adjudication_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_adj = {"seed", "decIdx", "act", "floor", "screen", "role",
                        "actionBits", "future", "continuationSeed", "hiddenSeed",
                        "won", "hpEnd", "valid"}
        missing = required_adj - set(reader.fieldnames or ())
        if missing:
            raise SystemExit(f"missing adjudication columns: {sorted(missing)}")
        row_count = 0
        for row in reader:
            row_count += 1
            if int(row["valid"]) != 1:
                raise SystemExit(f"invalid adjudication row: {row}")
            if int(row["won"]) not in (0, 1):
                raise SystemExit(f"non-binary won: {row}")
            role = row["role"]
            if role not in ("S", "V"):
                raise SystemExit(f"unexpected role: {role}")
            key = (int(row["seed"]), int(row["decIdx"]))
            replicate = (int(row["future"]), int(row["continuationSeed"]),
                         int(row["hiddenSeed"]))
            if replicate in rows_by_key[key][role]:
                raise SystemExit(f"duplicate replicate: {key} {role} {replicate}")
            rows_by_key[key][role][replicate] = row
    if row_count != 2 * len(targets) * args.replicates:
        raise SystemExit(f"unexpected adjudication row count: {row_count}")
    if set(rows_by_key) != set(target_keys):
        raise SystemExit("adjudication decision keys do not exactly match targets")

    results = []
    for target in targets:
        key = (int(target["seed"]), int(target["decIdx"]))
        roles = rows_by_key.get(key)
        if (not roles or set(roles["S"]) != set(roles["V"])
                or len(roles["S"]) != args.replicates):
            raise SystemExit(f"missing/unpaired adjudication: {key}")
        expected_meta = tuple(int(target[x]) for x in ("act", "floor", "screen"))
        for role, bits in (("S", target["safeBits"]),
                           ("V", target["strengthBits"])):
            for row in roles[role].values():
                if (tuple(int(row[x]) for x in ("act", "floor", "screen"))
                        != expected_meta or int(row["actionBits"]) != int(bits)):
                    raise SystemExit(f"identity mismatch: {row}")
        safe_win = sum(int(r["won"]) for r in roles["S"].values()) / args.replicates
        strength_win = sum(int(r["won"]) for r in roles["V"].values()) / args.replicates
        safe_hp = sum(float(r["hpEnd"]) for r in roles["S"].values()) / args.replicates
        strength_hp = sum(float(r["hpEnd"]) for r in roles["V"].values()) / args.replicates
        if safe_win > strength_win: winner = "safe"
        elif strength_win > safe_win: winner = "strength"
        else: winner = "tie"
        result = dict(target)
        result.update({"safeAdjudicatedWin": safe_win,
                       "strengthAdjudicatedWin": strength_win,
                       "terminalWinWinner": winner,
                       "safeMeanFinalHp": safe_hp,
                       "strengthMeanFinalHp": strength_hp,
                       "safeRegret": max(safe_win, strength_win) - safe_win,
                       "strengthRegret": max(safe_win, strength_win) - strength_win})
        results.append(result)

    safe_wins = sum(r["terminalWinWinner"] == "safe" for r in results)
    strength_wins = sum(r["terminalWinWinner"] == "strength" for r in results)
    ties = sum(r["terminalWinWinner"] == "tie" for r in results)
    safe_regrets = [r["safeRegret"] for r in results]
    strength_regrets = [r["strengthRegret"] for r in results]
    replicate_outcomes = {"safeOnly": 0, "strengthOnly": 0,
                          "bothWin": 0, "neitherWin": 0}
    for key in target_keys:
        for rep in rows_by_key[key]["S"]:
            sw = int(rows_by_key[key]["S"][rep]["won"])
            vw = int(rows_by_key[key]["V"][rep]["won"])
            label = ("bothWin" if sw and vw else "safeOnly" if sw
                     else "strengthOnly" if vw else "neitherWin")
            replicate_outcomes[label] += 1

    # Hierarchical paired bootstrap: source trajectories are the outer
    # independent clusters; paired futures are resampled within each decision.
    decision_rep_deltas = {}
    seed_decisions = defaultdict(list)
    for key in target_keys:
        decision_rep_deltas[key] = [
            int(rows_by_key[key]["S"][rep]["won"])
            - int(rows_by_key[key]["V"][rep]["won"])
            for rep in rows_by_key[key]["S"]
        ]
        seed_decisions[key[0]].append(key)
    unique_seeds = sorted(seed_decisions)
    rng = random.Random(0)
    bootstrap = []
    for _ in range(10000):
        sampled_decisions = []
        for _ in unique_seeds:
            seed = unique_seeds[rng.randrange(len(unique_seeds))]
            for key in seed_decisions[seed]:
                deltas = decision_rep_deltas[key]
                paired_sample = [deltas[rng.randrange(len(deltas))]
                                 for _ in deltas]
                sampled_decisions.append(sum(paired_sample) / len(paired_sample))
        bootstrap.append(sum(sampled_decisions) / len(sampled_decisions))
    bootstrap.sort()
    lo = bootstrap[int(0.025 * len(bootstrap))]
    hi = bootstrap[int(0.975 * len(bootstrap))]
    mean_delta = sum(r["safeAdjudicatedWin"] - r["strengthAdjudicatedWin"]
                     for r in results) / len(results)
    if safe_wins > strength_wins and sum(safe_regrets) < sum(strength_regrets) and lo > 0:
        verdict = "SUPPORT_SAFETY"
    elif (strength_wins > safe_wins and sum(strength_regrets) < sum(safe_regrets)
          and hi < 0):
        verdict = "REJECT_SAFETY"
    else:
        verdict = "INCONCLUSIVE"

    summary = {"decisions": len(results), "replicatesPerAction": args.replicates,
               "primaryUtility": "terminal win",
               "safeWins": safe_wins, "strengthWins": strength_wins, "ties": ties,
               "safeMeanRegret": sum(safe_regrets) / len(safe_regrets),
               "strengthMeanRegret": sum(strength_regrets) / len(strength_regrets),
               "safeMedianRegret": median(safe_regrets),
               "strengthMedianRegret": median(strength_regrets),
               "safeMinusStrengthMeanWinRate": mean_delta,
               "sourceSeedClusterPairedBootstrap95": [lo, hi],
               "pairedReplicateOutcomesDiagnostic": replicate_outcomes,
               "verdict": verdict,
               "decisionRule": ("SUPPORT safer action only if safe wins > strength wins, "
                                "safe mean regret is lower, and the clustered 95% interval "
                                "for safe-minus-strength win rate excludes zero; otherwise "
                                "INCONCLUSIVE or REJECT if directionally adverse")}
    fields = list(results[0])
    with open(out / "decisions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fields); writer.writeheader(); writer.writerows(results)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
