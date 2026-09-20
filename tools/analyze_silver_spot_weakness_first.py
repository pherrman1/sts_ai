#!/usr/bin/env python3
"""Analyze the diagnostic-only SPOT_WEAKNESS_FIRST_V1 paired replay."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


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


def load(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sibling_metrics(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    pair_total = pair_agree = top_total = top_agree = 0
    regrets = []
    centered = []
    for group_rows in groups.values():
        if len(group_rows) < 2:
            continue
        top_total += 1
        candidate_top = max(group_rows, key=lambda row: (row["value"], row["leaf_snapshot_id"]))
        teacher_top = max(group_rows, key=lambda row: (row["teacher_a"], row["leaf_snapshot_id"]))
        top_agree += candidate_top["leaf_snapshot_id"] == teacher_top["leaf_snapshot_id"]
        regrets.append(max(0.0, teacher_top["teacher_a"] - candidate_top["value"]))
        candidate_mean = mean([row["value"] for row in group_rows])
        teacher_mean = mean([row["teacher_a"] for row in group_rows])
        centered.extend((row["value"] - candidate_mean) -
                        (row["teacher_a"] - teacher_mean) for row in group_rows)
        for left in range(len(group_rows)):
            for right in range(left + 1, len(group_rows)):
                delta = group_rows[left]["value"] - group_rows[right]["value"]
                target = group_rows[left]["teacher_a"] - group_rows[right]["teacher_a"]
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


def leaf_means(rows, *, utility_key: str, wall_key: str):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["leaf_snapshot_id"]].append(row)
    output = {}
    for leaf, samples in grouped.items():
        values = [sample[utility_key] for sample in samples]
        output[leaf] = {
            "group_id": samples[0]["group_id"],
            "value": mean(values),
            "rollout_std": statistics.pstdev(values),
            "rollout_se": statistics.pstdev(values) / math.sqrt(len(values)),
            "action_count": mean([sample.get("action_count", sample.get("treatment_action_count"))
                                   for sample in samples]),
            "turn_delta": mean([sample.get("turn_delta", sample.get("treatment_turn_delta"))
                                 for sample in samples]),
            "wall_micros": mean([sample[wall_key] for sample in samples]),
            "replicates": len(samples),
        }
    return output


def attach(arm, teachers):
    rows = []
    for leaf, value in arm.items():
        reference = teachers.get(leaf)
        if reference is None:
            continue
        row = dict(value)
        row["leaf_snapshot_id"] = leaf
        row["teacher_a"] = reference["A"]["value"]
        row["teacher_b"] = reference["B"]["value"]
        rows.append(row)
    return rows


def global_metrics(rows):
    errors = [row["value"] - row["teacher_a"] for row in rows]
    return {
        "leaves": len(rows),
        "value_mae": mean([abs(error) for error in errors]),
        "value_rmse": rmse(errors),
        "sibling": sibling_metrics(rows),
        "rollout_std": {"mean": mean([row["rollout_std"] for row in rows]),
                        "median": median([row["rollout_std"] for row in rows])},
        "rollout_se": {"mean": mean([row["rollout_se"] for row in rows]),
                       "median": median([row["rollout_se"] for row in rows])},
    }


def grouped_bootstrap(base_rows, treatment_rows, replicates, seed):
    base = defaultdict(list)
    treatment = defaultdict(list)
    for row in base_rows:
        base[row["group_id"]].append(row)
    for row in treatment_rows:
        treatment[row["group_id"]].append(row)
    groups = sorted(set(base) & set(treatment))
    rng = random.Random(seed)
    regret_lower = pairwise_not_worse = top_not_worse = 0
    regret_deltas = []
    pair_deltas = []
    top_deltas = []
    for _ in range(replicates):
        chosen = [rng.choice(groups) for _ in groups]
        sampled_base = []
        sampled_treatment = []
        for occurrence, group in enumerate(chosen):
            for row in base[group]:
                copy = dict(row); copy["group_id"] = f"{group}#{occurrence}"; sampled_base.append(copy)
            for row in treatment[group]:
                copy = dict(row); copy["group_id"] = f"{group}#{occurrence}"; sampled_treatment.append(copy)
        bm = sibling_metrics(sampled_base)
        tm = sibling_metrics(sampled_treatment)
        dr = tm["mean_teacher_regret"] - bm["mean_teacher_regret"]
        dp = tm["pairwise_concordance"] - bm["pairwise_concordance"]
        dt = tm["top_leaf_agreement"] - bm["top_leaf_agreement"]
        regret_deltas.append(dr); pair_deltas.append(dp); top_deltas.append(dt)
        regret_lower += dr < 0
        pairwise_not_worse += dp >= 0
        top_not_worse += dt >= -0.05
    return {
        "method": "resample complete sibling groups with replacement",
        "replicates": replicates, "seed": seed, "groups": len(groups),
        "probability_treatment_regret_lower": regret_lower / replicates,
        "probability_pairwise_not_lower": pairwise_not_worse / replicates,
        "probability_top_agreement_not_materially_lower": top_not_worse / replicates,
        "delta_ci": {"regret": ci(regret_deltas), "pairwise": ci(pair_deltas), "top": ci(top_deltas)},
    }


def teacher_noise(teachers):
    rows = []
    for leaf, refs in teachers.items():
        row = {"group_id": refs["A"]["group_id"], "leaf_snapshot_id": leaf,
               "value": refs["B"]["value"], "teacher_a": refs["A"]["value"]}
        rows.append(row)
    errors = [row["value"] - row["teacher_a"] for row in rows]
    return {"leaves": len(rows), "mean_abs": mean([abs(error) for error in errors]),
            "rmse": rmse(errors), "mean": mean(errors), "median": median(errors),
            "sibling": sibling_metrics(rows)}


def identity_check(base_rows, treatment_rows):
    treatment_by_key = {(row["leaf_snapshot_id"], row["replicate"]): row for row in treatment_rows}
    mismatches = []
    for baseline in base_rows:
        key = (baseline["leaf_snapshot_id"], baseline["replicate"])
        treatment = treatment_by_key.get(key)
        if treatment is None:
            mismatches.append({"key": key, "reason": "missing treatment"})
            continue
        if not baseline["candidate_applicable"]:
            checks = {
                "action_fingerprints": (baseline["action_fingerprints"], treatment["treatment_action_fingerprints"]),
                "utility": (baseline["original_root_corrected_utility"], treatment["treatment_utility"]),
                "action_count": (baseline["action_count"], treatment["treatment_action_count"]),
                "turn_delta": (baseline["turn_delta"], treatment["treatment_turn_delta"]),
            }
            for field, (left, right) in checks.items():
                if left != right:
                    mismatches.append({"key": key, "field": field, "baseline": left, "treatment": right})
    return {"inactive_rows": sum(not row["candidate_applicable"] for row in base_rows),
            "mismatch_count": len(mismatches), "mismatches": mismatches[:20]}


def production_stats(base_rows, treatment_rows):
    def stats(values):
        return {"mean": mean(values), "median": median(values),
                "p95": sorted(values)[int(0.95 * (len(values) - 1))] if values else None}
    base_wall = [row["wall_micros"] for row in base_rows]
    treatment_wall = [row["treatment_wall_micros"] for row in treatment_rows]
    paired = {(row["leaf_snapshot_id"], row["replicate"]): row for row in treatment_rows}
    base_action = [row["action_count"] for row in base_rows]
    treatment_action = [paired[(row["leaf_snapshot_id"], row["replicate"])] ["treatment_action_count"] for row in base_rows]
    base_turn = [row["turn_delta"] for row in base_rows]
    treatment_turn = [paired[(row["leaf_snapshot_id"], row["replicate"])] ["treatment_turn_delta"] for row in base_rows]
    return {"baseline_wall_micros": stats(base_wall), "treatment_wall_micros": stats(treatment_wall),
            "baseline_action_count": stats(base_action), "treatment_action_count": stats(treatment_action),
            "baseline_turn_delta": stats(base_turn), "treatment_turn_delta": stats(treatment_turn),
            "mean_wall_overhead": (mean(treatment_wall) - mean(base_wall)) / mean(base_wall),
            "paired_rows": len(base_rows)}


def classify(base, treatment, bootstrap, production, group_count):
    if group_count < 12:
        return "INSUFFICIENT_FRESH_COVERAGE"
    b_regret = base["sibling"]["mean_teacher_regret"]
    t_regret = treatment["sibling"]["mean_teacher_regret"]
    improvement = (b_regret - t_regret) / b_regret if b_regret and b_regret > 0 else None
    pair_delta = treatment["sibling"]["pairwise_concordance"] - base["sibling"]["pairwise_concordance"]
    top_delta = treatment["sibling"]["top_leaf_agreement"] - base["sibling"]["top_leaf_agreement"]
    overhead = production["mean_wall_overhead"]
    gates = {
        "regret_improvement_ge_15pct": improvement is not None and improvement >= 0.15,
        "pairwise_no_regression": pair_delta >= 0,
        "top_no_material_regression": top_delta >= -0.05,
        "bootstrap_probability_ge_90pct": bootstrap["probability_treatment_regret_lower"] >= 0.90,
        "mean_wall_overhead_lt_5pct": overhead < 0.05,
    }
    if all(gates.values()): label = "SPOT_WEAKNESS_FIRST_PROMISING"
    elif (t_regret > b_regret or pair_delta <= -0.05 or
          (overhead > 0.05 and not gates["regret_improvement_ge_15pct"])):
        label = "SPOT_WEAKNESS_FIRST_REJECT"
    else:
        label = "INCONCLUSIVE"
    return {"classification": label, "regret_improvement": improvement,
            "pairwise_delta": pair_delta, "top_agreement_delta": top_delta,
            "gates": gates, "top_material_regression_threshold": -0.05}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("treatment", type=Path)
    parser.add_argument("teachers", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    args = parser.parse_args()
    corpus = load(args.corpus)
    baseline = load(args.baseline)
    treatment = load(args.treatment)
    teacher_rows = load(args.teachers)
    teachers = defaultdict(dict)
    for row in teacher_rows:
        if row.get("state_kind") == "leaf" and row.get("teacher_valid") and row.get("selected_q_valid"):
            teachers[row["leaf_snapshot_id"]][row["replicate"]] = {
                "value": row["original_root_corrected_teacher_value"],
                "selected_action": row["selected_action_fingerprint"],
                "group_id": row["group_id"], "wall_micros": row["wall_micros"]}
    if any(set(refs) != {"A", "B"} for refs in teachers.values()):
        raise RuntimeError("teacher A/B coverage is incomplete")
    if len(baseline) != len(treatment) or len(baseline) != len(corpus) * 32:
        raise RuntimeError("paired baseline/treatment/corpus row count mismatch")
    identity = identity_check(baseline, treatment)
    if identity["mismatch_count"]:
        raise RuntimeError("inactive treatment identity mismatch: " + json.dumps(identity["mismatches"][:3]))
    base_leaf = leaf_means(baseline, utility_key="original_root_corrected_utility", wall_key="wall_micros")
    treatment_leaf = leaf_means(treatment, utility_key="treatment_utility", wall_key="treatment_wall_micros")
    base = global_metrics(attach(base_leaf, teachers))
    treatment_metrics = global_metrics(attach(treatment_leaf, teachers))
    k1_base = global_metrics(attach(leaf_means([r for r in baseline if r["replicate"] == 0],
                                                utility_key="original_root_corrected_utility", wall_key="wall_micros"), teachers))
    k1_treatment = global_metrics(attach(leaf_means([r for r in treatment if r["replicate"] == 0],
                                                     utility_key="treatment_utility", wall_key="treatment_wall_micros"), teachers))
    boot = grouped_bootstrap(attach(base_leaf, teachers), attach(treatment_leaf, teachers), args.bootstrap, 20260920)
    production = production_stats(baseline, treatment)
    active_ids = {row["leaf_snapshot_id"] for row in corpus if row["candidate_applicable"]}
    active_base = {leaf: base_leaf[leaf] for leaf in active_ids}
    active_treatment = {leaf: treatment_leaf[leaf] for leaf in active_ids}
    active_rows = attach(active_base, teachers)
    active_treatment_rows = attach(active_treatment, teachers)
    base_residual = [row["value"] - row["teacher_a"] for row in active_rows]
    treatment_residual = [row["value"] - row["teacher_a"] for row in active_treatment_rows]
    active_diag = {
        "groups": len({row["group_id"] for row in active_rows}), "leaves": len(active_rows),
        "baseline_mean": mean([row["value"] for row in active_rows]),
        "treatment_mean": mean([row["value"] for row in active_treatment_rows]),
        "baseline_mean_abs_residual": mean([abs(x) for x in base_residual]),
        "treatment_mean_abs_residual": mean([abs(x) for x in treatment_residual]),
        "aggregate_fraction_abs_residual_removed": 1 - sum(abs(x) for x in treatment_residual) / sum(abs(x) for x in base_residual),
        "baseline_first_actions": Counter(next((r["action_fingerprints"][0] for r in baseline
                                                 if r["leaf_snapshot_id"] == leaf and r["replicate"] == 0), None)
                                          for leaf in active_ids),
        "candidate_action_fingerprints": Counter(row["candidate_action_fingerprint"] for row in corpus if row["candidate_applicable"]),
        "teacher_a_selected_actions": Counter(teachers[leaf]["A"]["selected_action"] for leaf in active_ids),
        "teacher_b_selected_actions": Counter(teachers[leaf]["B"]["selected_action"] for leaf in active_ids),
        "teacher_action_agreement_leaves": sum(teachers[leaf]["A"]["selected_action"] == teachers[leaf]["B"]["selected_action"] for leaf in active_ids),
    }
    for key in ("baseline_first_actions", "candidate_action_fingerprints", "teacher_a_selected_actions", "teacher_b_selected_actions"):
        active_diag[key] = dict(active_diag[key])
    teacher_noise_result = teacher_noise(teachers)
    report = {
        "schema": "silver_spot_weakness_first_analysis_v1",
        "candidate": "SPOT_WEAKNESS_FIRST_V1",
        "corpus_rows": len(corpus), "baseline_rows": len(baseline), "treatment_rows": len(treatment),
        "group_count": len({row["group_id"] for row in corpus}),
        "teacher_coverage": {"leaves": len(teachers), "rows": len(teacher_rows), "all_valid": True},
        "inactive_identity": identity,
        "baseline_k32": base, "treatment_k32": treatment_metrics,
        "baseline_k1": k1_base, "treatment_k1": k1_treatment,
        "teacher_noise_floor_B_vs_A": teacher_noise_result,
        "group_bootstrap": boot, "production_metrics": production,
        "active_subset": active_diag,
        "classification": classify(base, treatment_metrics, boot, production,
                                     len({row["group_id"] for row in corpus})),
        "definitions": {
            "teacher_regret": "within-group teacher-A top value minus candidate value at the candidate top leaf",
            "bootstrap": "10,000 complete sibling groups resampled with replacement, seed 20260920",
            "top_material_regression": "treatment top-leaf agreement at least 5 percentage points below baseline is material",
            "runtime": "paired raw rollout wall_micros mean over all 8,032 rows; filesystem/teacher cost excluded",
        },
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["classification"]["classification"])


if __name__ == "__main__":
    main()
