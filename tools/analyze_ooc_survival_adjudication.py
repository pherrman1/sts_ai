#!/usr/bin/env python3
"""Analyze paired full-run adjudication of targeted OOC tradeoff pairs."""

import argparse
import csv
import json
import math
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
                            "safeBits", "strengthBits", "safePSurvive",
                            "safeActionIdx", "strengthActionIdx",
                            "strengthPSurvive", "safeVAlive", "strengthVAlive",
                            "safeQProduct", "strengthQProduct",
                            "safeDenseScore", "strengthDenseScore"}
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
        numeric_names = ("safePSurvive", "strengthPSurvive", "safeVAlive",
                         "strengthVAlive", "safeQProduct", "strengthQProduct",
                         "safeDenseScore", "strengthDenseScore")
        numeric = {name: float(target[name]) for name in numeric_names}
        if not all(math.isfinite(value) for value in numeric.values()):
            raise SystemExit(f"non-finite target score: {key}")
        if not (0 <= numeric["strengthPSurvive"] < numeric["safePSurvive"] <= 1):
            raise SystemExit(f"invalid safe/strength survival ordering: {key}")
        if not (0 <= numeric["safeVAlive"] < numeric["strengthVAlive"] <= 1):
            raise SystemExit(f"invalid safe/strength survivor-value ordering: {key}")
        safe_idx = int(target["safeActionIdx"])
        strength_idx = int(target["strengthActionIdx"])
        if safe_idx < 0 or strength_idx < 0 or safe_idx == strength_idx:
            raise SystemExit(f"invalid safe/strength action indices: {key}")
        safe_q = numeric["safePSurvive"] * numeric["safeVAlive"]
        strength_q = numeric["strengthPSurvive"] * numeric["strengthVAlive"]
        if (not math.isclose(numeric["safeQProduct"], safe_q, rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(numeric["strengthQProduct"], strength_q,
                                    rel_tol=1e-12, abs_tol=1e-12)):
            raise SystemExit(f"Q product mismatch: {key}")
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
        def score_choice(safe_score, strength_score):
            if safe_score > strength_score: return "S"
            if strength_score > safe_score: return "V"
            return "S" if safe_idx < strength_idx else "V"

        rule_choices = {
            "survivalOnly": "S",
            "strengthOnly": "V",
            "combinedProduct": score_choice(safe_q, strength_q),
            "denseK3": score_choice(numeric["safeDenseScore"],
                                     numeric["strengthDenseScore"]),
        }
        result = dict(target)
        result.update({"safeAdjudicatedWin": safe_win,
                       "strengthAdjudicatedWin": strength_win,
                       "terminalWinWinner": winner,
                       "safeMeanFinalHp": safe_hp,
                       "strengthMeanFinalHp": strength_hp,
                       "safeRegret": max(safe_win, strength_win) - safe_win,
                       "strengthRegret": max(safe_win, strength_win) - strength_win})
        for name, role in rule_choices.items():
            chosen_win = safe_win if role == "S" else strength_win
            result.update({f"{name}Choice": role,
                           f"{name}AdjudicatedWin": chosen_win,
                           f"{name}Regret": max(safe_win, strength_win) - chosen_win,
                           f"{name}CorrectNonTied": int(
                               winner != "tie"
                               and ((winner == "safe" and role == "S")
                                    or (winner == "strength" and role == "V")))})
        results.append(result)

    safe_wins = sum(r["terminalWinWinner"] == "safe" for r in results)
    strength_wins = sum(r["terminalWinWinner"] == "strength" for r in results)
    ties = sum(r["terminalWinWinner"] == "tie" for r in results)
    replicate_outcomes = {"safeOnly": 0, "strengthOnly": 0,
                          "bothWin": 0, "neitherWin": 0}
    for key in target_keys:
        for rep in rows_by_key[key]["S"]:
            sw = int(rows_by_key[key]["S"][rep]["won"])
            vw = int(rows_by_key[key]["V"][rep]["won"])
            label = ("bothWin" if sw and vw else "safeOnly" if sw
                     else "strengthOnly" if vw else "neitherWin")
            replicate_outcomes[label] += 1

    rule_names = ("survivalOnly", "strengthOnly", "combinedProduct", "denseK3")
    non_tied = safe_wins + strength_wins
    rule_metrics = {}
    for name in rule_names:
        regrets = [r[f"{name}Regret"] for r in results]
        rule_metrics[name] = {
            "safeChoices": sum(r[f"{name}Choice"] == "S" for r in results),
            "strengthChoices": sum(r[f"{name}Choice"] == "V" for r in results),
            "correctNonTied": sum(r[f"{name}CorrectNonTied"] for r in results),
            "accuracyNonTied": (sum(r[f"{name}CorrectNonTied"] for r in results)
                                 / non_tied if non_tied else 0.0),
            "meanAdjudicatedWin": (sum(r[f"{name}AdjudicatedWin"] for r in results)
                                    / len(results)),
            "meanRegret": sum(regrets) / len(regrets),
            "medianRegret": median(regrets),
        }

    # Hierarchical paired bootstrap of combined-minus-baseline chosen wins:
    # source trajectories are outer clusters and paired futures are resampled
    # within decisions.
    rule_rep_wins = {}
    seed_decisions = defaultdict(list)
    result_by_key = {(int(r["seed"]), int(r["decIdx"])): r for r in results}
    for key in target_keys:
        rule_rep_wins[key] = {}
        for name in rule_names:
            role = result_by_key[key][f"{name}Choice"]
            rule_rep_wins[key][name] = [int(rows_by_key[key][role][rep]["won"])
                                        for rep in rows_by_key[key]["S"]]
        seed_decisions[key[0]].append(key)
    unique_seeds = sorted(seed_decisions)
    comparisons = {}
    for baseline_idx, baseline in enumerate(("survivalOnly", "strengthOnly", "denseK3")):
        rng = random.Random(baseline_idx)
        bootstrap = []
        for _ in range(10000):
            sampled_decisions = []
            for _ in unique_seeds:
                seed = unique_seeds[rng.randrange(len(unique_seeds))]
                for key in seed_decisions[seed]:
                    n = len(rule_rep_wins[key][baseline])
                    deltas = [rule_rep_wins[key]["combinedProduct"][i]
                              - rule_rep_wins[key][baseline][i] for i in range(n)]
                    paired_sample = [deltas[rng.randrange(n)] for _ in range(n)]
                    sampled_decisions.append(sum(paired_sample) / n)
            bootstrap.append(sum(sampled_decisions) / len(sampled_decisions))
        bootstrap.sort()
        comparisons[f"combinedMinus{baseline[0].upper() + baseline[1:]}"] = {
            "meanWinRateDifference": (rule_metrics["combinedProduct"]["meanAdjudicatedWin"]
                                      - rule_metrics[baseline]["meanAdjudicatedWin"]),
            "sourceSeedClusterPairedBootstrap95": [
                bootstrap[int(0.025 * len(bootstrap))],
                bootstrap[int(0.975 * len(bootstrap))]],
        }

    primary_baselines = ("survivalOnly", "strengthOnly")
    support = all(
        rule_metrics["combinedProduct"]["accuracyNonTied"] > rule_metrics[b]["accuracyNonTied"]
        and rule_metrics["combinedProduct"]["meanRegret"] < rule_metrics[b]["meanRegret"]
        and comparisons[f"combinedMinus{b[0].upper() + b[1:]}"]["sourceSeedClusterPairedBootstrap95"][0] > 0
        for b in primary_baselines)
    reject = all(
        rule_metrics["combinedProduct"]["accuracyNonTied"] < rule_metrics[b]["accuracyNonTied"]
        and rule_metrics["combinedProduct"]["meanRegret"] > rule_metrics[b]["meanRegret"]
        and comparisons[f"combinedMinus{b[0].upper() + b[1:]}"]["sourceSeedClusterPairedBootstrap95"][1] < 0
        for b in primary_baselines)
    verdict = "SUPPORT_COMBINED" if support else "REJECT_COMBINED" if reject else "INCONCLUSIVE"

    summary = {"decisions": len(results), "replicatesPerAction": args.replicates,
               "primaryUtility": "terminal win",
               "safeWins": safe_wins, "strengthWins": strength_wins, "ties": ties,
               "rules": rule_metrics,
               "comparisons": comparisons,
               "pairedReplicateOutcomesDiagnostic": replicate_outcomes,
               "verdict": verdict,
               "decisionRule": ("SUPPORT_COMBINED only if combined product has higher "
                                "non-tied accuracy, lower mean regret, and clustered paired "
                                "win-difference intervals above zero versus both survival-only "
                                "and strength-only; REJECT_COMBINED symmetrically; otherwise "
                                "INCONCLUSIVE. Dense K=3 is a reported secondary baseline.")}
    fields = list(results[0])
    with open(out / "decisions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fields); writer.writeheader(); writer.writerows(results)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
