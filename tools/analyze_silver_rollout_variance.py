#!/usr/bin/env python3
"""Analyze fixed SimpleAgent rollout replicates against independent Silver teachers."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

KS = (1, 2, 4, 8, 16, 32)


def mean(values):
    return statistics.fmean(values) if values else None


def median(values):
    return statistics.median(values) if values else None


def rmse(values):
    return math.sqrt(mean([value * value for value in values])) if values else None


def ci(values):
    if not values:
        return {"p025": None, "p975": None}
    ordered = sorted(values)
    return {"p025": ordered[int(0.025 * (len(ordered) - 1))],
            "p975": ordered[int(0.975 * (len(ordered) - 1))]}


def band_turns(turns: int) -> str:
    return "short" if turns <= 2 else "medium" if turns <= 5 else "long"


def band_hp(fraction: float) -> str:
    return "low" if fraction < 0.34 else "mid" if fraction < 0.67 else "high"


def sibling_metrics(rows, value_key="value", reference_key="teacher_a"):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    pair_total = pair_agree = 0
    top_total = top_agree = 0
    regrets = []
    centered = []
    for group_rows in groups.values():
        if len(group_rows) < 2:
            continue
        top_total += 1
        candidate_top = max(group_rows, key=lambda row: row[value_key])
        reference_top = max(group_rows, key=lambda row: row[reference_key])
        top_agree += candidate_top["leaf_snapshot_id"] == reference_top["leaf_snapshot_id"]
        regrets.append(reference_top[reference_key] - candidate_top[reference_key])
        candidate_mean = mean([row[value_key] for row in group_rows])
        reference_mean = mean([row[reference_key] for row in group_rows])
        for row in group_rows:
            centered.append((row[value_key] - candidate_mean)
                            - (row[reference_key] - reference_mean))
        for left in range(len(group_rows)):
            for right in range(left + 1, len(group_rows)):
                delta = group_rows[left][value_key] - group_rows[right][value_key]
                target = group_rows[left][reference_key] - group_rows[right][reference_key]
                if delta == 0 or target == 0:
                    continue
                pair_total += 1
                pair_agree += (delta > 0) == (target > 0)
    return {
        "groups": top_total,
        "pairwise_concordance": pair_agree / pair_total if pair_total else None,
        "pairwise_pairs": pair_total,
        "top_leaf_agreement": top_agree / top_total if top_total else None,
        "mean_teacher_regret": mean(regrets),
        "median_teacher_regret": median(regrets),
        "centered_rmse": rmse(centered),
        "centered_mae": mean([abs(value) for value in centered]),
    }


def rollout_stats(rows):
    def stats(subset):
        actions = [row["action_count"] for row in subset]
        turns = [row["turn_delta"] for row in subset]
        latency = [row["wall_micros"] for row in subset]
        wins = sum(row["terminal_outcome"] == 1 for row in subset)
        losses = sum(row["terminal_outcome"] != 1 for row in subset)
        return {"count": len(subset), "wins": wins, "losses": losses,
                "win_rate": wins / len(subset) if subset else None,
                "mean_action_count": mean(actions), "mean_turn_delta": mean(turns),
                "mean_wall_micros": mean(latency), "median_wall_micros": median(latency),
                "p95_wall_micros": sorted(latency)[int(0.95 * (len(latency) - 1))] if latency else None}
    output = {"all": stats(rows)}
    for field in ("depth", "act", "encounter_category", "source_rollout_length_band", "hp_band"):
        buckets = defaultdict(list)
        for row in rows:
            buckets[str(row.get(field, "unknown"))].append(row)
        output[field] = {key: stats(value) for key, value in sorted(buckets.items())}
    return output


def attach_values(rollouts, teachers, k):
    by_leaf = defaultdict(list)
    for row in rollouts:
        if row.get("accepted") and row["replicate"] < k:
            by_leaf[row["leaf_snapshot_id"]].append(row)
    rows = []
    for leaf, samples in by_leaf.items():
        if len(samples) != k or leaf not in teachers or "A" not in teachers[leaf]:
            continue
        row = dict(samples[0])
        row["value"] = mean([sample["original_root_corrected_utility"] for sample in samples])
        row["teacher_a"] = teachers[leaf]["A"]
        if "B" in teachers[leaf]:
            row["teacher_b"] = teachers[leaf]["B"]
        row["rollout_std"] = statistics.pstdev(
            [sample["original_root_corrected_utility"] for sample in samples]) if k > 1 else 0.0
        row["rollout_se"] = row["rollout_std"] / math.sqrt(k)
        rows.append(row)
    return rows


def teacher_noise(rows):
    paired = [row for row in rows if "teacher_b" in row]
    if not paired:
        return {"leaves": 0}
    diff = [row["teacher_b"] - row["teacher_a"] for row in paired]
    return {"leaves": len(paired), "mean_abs": mean([abs(value) for value in diff]),
            "rmse": rmse(diff), "mean": mean(diff), "median": median(diff),
            "sibling": sibling_metrics([
                {**row, "value": row["teacher_b"]} for row in paired],
                value_key="value", reference_key="teacher_a")}


def margin_noise(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    total = below = 0
    for group_rows in groups.values():
        for left in range(len(group_rows)):
            for right in range(left + 1, len(group_rows)):
                total += 1
                margin = abs(group_rows[left]["teacher_a"] - group_rows[right]["teacher_a"])
                noise = math.sqrt(group_rows[left]["rollout_std"] ** 2
                                  + group_rows[right]["rollout_std"] ** 2)
                below += margin < noise
    return {"pairs": total, "margin_below_one_rollout_noise": below,
            "fraction": below / total if total else None}


def bootstrap(grouped, replicates=1000, seed=20260920):
    ids = sorted(set.intersection(*(set(grouped[k]) for k in KS)))
    if not ids:
        return {}
    rng = random.Random(seed)
    output = {k: {"regret": [], "pairwise": [], "top": []} for k in KS}
    for _ in range(replicates):
        chosen = [rng.choice(ids) for _ in ids]
        for k in KS:
            rows = []
            for occurrence, group_id in enumerate(chosen):
                for row in grouped[k][group_id]:
                    copy = dict(row)
                    copy["group_id"] = f"{group_id}#{occurrence}"
                    rows.append(copy)
            metrics = sibling_metrics(rows)
            for key, name in (("mean_teacher_regret", "regret"),
                              ("pairwise_concordance", "pairwise"),
                              ("top_leaf_agreement", "top")):
                if metrics[key] is not None:
                    output[k][name].append(metrics[key])
    return {k: {name: ci(values) for name, values in metric.items()}
            for k, metric in output.items()}


def classify(metrics, noise):
    m1 = metrics[1]["sibling"]["mean_teacher_regret"]
    m4 = metrics[4]["sibling"]["mean_teacher_regret"]
    m8 = metrics[8]["sibling"]["mean_teacher_regret"]
    m32 = metrics[32]["sibling"]["mean_teacher_regret"]
    c1 = metrics[1]["sibling"]["pairwise_concordance"]
    c4 = metrics[4]["sibling"]["pairwise_concordance"]
    reduction = (m1 - m4) / m1 if m1 is not None and m4 is not None and m1 > 0 else None
    bootstrap4 = metrics[4].get("bootstrap", {}).get("regret", {})
    upper4 = bootstrap4.get("p975") if bootstrap4.get("p975") is not None else m4
    gain_lower = (m1 - upper4) if m1 is not None and upper4 is not None else None
    variance_material = (reduction is not None and reduction >= 0.20 and c4 is not None
                         and c1 is not None and c4 >= c1 and gain_lower is not None and gain_lower > 0)
    teacher_mae = noise.get("mean_abs")
    systematic = (m4 is not None and m8 is not None and m32 is not None and m1 is not None
                  and m1 > 0 and (m1 - m8) / m1 >= 0.20 and (m1 - m4) / m1 < 0.10
                  and teacher_mae is not None and metrics[32]["value_mae"] > teacher_mae)
    not_primary = (teacher_mae is not None and metrics[32]["value_mae"] is not None
                   and metrics[32]["value_mae"] <= teacher_mae * 1.25
                   and reduction is not None and reduction < 0.20)
    if variance_material:
        label = "ROLLOUT_VARIANCE_MATERIAL"
    elif systematic:
        label = "ROLLOUT_SYSTEMATIC_ERROR_MATERIAL"
    elif not_primary:
        label = "ROLLOUT_NOT_PRIMARY"
    else:
        label = "INCONCLUSIVE"
    return {"classification": label, "k1_to_k4_regret_reduction": reduction,
            "predeclared_variance_rule_pass": variance_material,
            "predeclared_systematic_rule_pass": systematic,
            "predeclared_not_primary_rule_pass": not_primary,
            "note": "Bootstrap gain check is source-group clustered; classification is diagnostic, not a treatment recommendation."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("teachers", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    raw_rollouts = [json.loads(line) for line in args.rollouts.read_text().splitlines() if line.strip()]
    raw_teachers = [json.loads(line) for line in args.teachers.read_text().splitlines() if line.strip()]
    teachers = defaultdict(dict)
    for row in raw_teachers:
        if row.get("state_kind") != "leaf" or row.get("budget") != 25000 or not row.get("teacher_valid"):
            continue
        if row.get("selected_q_valid"):
            teachers[row["leaf_snapshot_id"]][row["replicate"]] = row["original_root_corrected_teacher_value"]
    metrics = {}
    grouped = {k: defaultdict(list) for k in KS}
    for k in KS:
        rows = attach_values(raw_rollouts, teachers, k)
        sibling = sibling_metrics(rows)
        value_errors = [row["value"] - row["teacher_a"] for row in rows]
        metrics[k] = {"leaves": len(rows), "value_mae": mean([abs(value) for value in value_errors]),
                      "value_rmse": rmse(value_errors), "sibling": sibling,
                      "rollout_std": {"mean": mean([row["rollout_std"] for row in rows]),
                                      "median": median([row["rollout_std"] for row in rows])},
                      "rollout_se": {"mean": mean([row["rollout_se"] for row in rows]),
                                    "median": median([row["rollout_se"] for row in rows])}}
        for row in rows:
            grouped[k][row["group_id"]].append(row)
    bootstrapped = bootstrap(grouped, args.bootstrap)
    for k in KS:
        metrics[k]["bootstrap"] = bootstrapped.get(k, {})
    rows32 = attach_values(raw_rollouts, teachers, 32)
    noise = teacher_noise(rows32)
    for k in KS:
        metrics[k]["rollout_observables"] = rollout_stats(
            [row for row in raw_rollouts if row.get("accepted") and row["replicate"] < k])
    residuals = sorted(((abs(row["value"] - row["teacher_a"]), row) for row in rows32), reverse=True)
    report = {"schema": "silver_rollout_variance_analysis_v1", "k_values": list(KS),
              "rollout_rows": len(raw_rollouts), "teacher_rows": len(raw_teachers),
              "teacher_noise_floor_B_vs_A": noise, "margin_noise": margin_noise(rows32),
              "metrics": {str(k): value for k, value in metrics.items()},
              "classification": classify(metrics, noise),
              "largest_stable_residuals": [
                  {"group_id": row["group_id"], "leaf_snapshot_id": row["leaf_snapshot_id"],
                   "depth": row["depth"], "encounter_category": row["encounter_category"],
                   "rollout_mean32": row["value"], "teacher_a": row["teacher_a"],
                   "residual": row["value"] - row["teacher_a"]}
                  for _, row in residuals[:20]],
              "bootstrap": {"method": "resample complete sibling groups with replacement",
                            "replicates": args.bootstrap, "seed": 20260920}}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["classification"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
