#!/usr/bin/env python3
"""Analyze and fit Silver terminal-value components on fixed rollout leaves.

This is an offline diagnostic. It never changes BattleSearcher defaults and
never uses Teacher B for fitting. Rows must come from the diagnostic rollout
seam, with original-root raw terminal features and exact reconstruction
parity recorded by the native executable.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear


PARAMETERS = (
    "win_bonus", "potion_weight", "victory_turn_penalty",
    "monster_damage_weight", "alive_weight", "energy_waste_weight",
    "draw_weight", "turn_survival_weight", "gold_weight", "max_hp_weight",
    "parasite_penalty",
)
UNTIED_PARAMETERS = (
    "win_bonus", "victory_hp", "victory_potion", "victory_turn_penalty",
    "death_save", "gold", "max_hp", "parasite_penalty", "monster_damage",
    "alive_penalty", "energy_waste", "draw", "loss_potion", "survival",
)
CURRENT = {
    "win_bonus": 53.0, "potion_weight": 11.0,
    "victory_turn_penalty": 0.4, "monster_damage_weight": 37.0,
    "alive_weight": 3.4, "energy_waste_weight": 1.75, "draw_weight": 0.03,
    "turn_survival_weight": 1.5, "gold_weight": 0.25, "max_hp_weight": 2.0,
    "parasite_penalty": 12.0,
}

FEATURES = (
    "victory_post_battle_healed_hp", "victory_potion_count", "victory_turn",
    "death_save_hp_equivalent", "effective_gold_delta", "max_hp_delta",
    "parasite_implant", "loss_monster_damage_fraction", "loss_monsters_alive",
    "loss_energy_wasted", "loss_cards_drawn", "loss_potion_count",
    "loss_survival_turns",
)
FIXED_FEATURES = ("victory_post_battle_healed_hp", "death_save_hp_equivalent")
LAMBDAS = (0.01, 0.1, 1.0, 10.0, 100.0)


def mean(values):
    return statistics.fmean(values) if values else None


def percentile(values, q):
    if not values:
        return None
    return sorted(values)[min(len(values) - 1, int(q * (len(values) - 1)))]


def corr(left, right):
    if len(left) != len(right) or len(left) < 2:
        return None
    lx, rx = mean(left), mean(right)
    lvar = sum((x - lx) ** 2 for x in left)
    rvar = sum((x - rx) ** 2 for x in right)
    if lvar == 0 or rvar == 0:
        return None
    return sum((x - lx) * (y - rx) for x, y in zip(left, right)) / math.sqrt(lvar * rvar)


def feature_vector(features):
    return np.asarray([float(features.get(name, 0.0)) for name in FEATURES], dtype=float)


def parameter_vector(weights):
    return np.asarray([float(weights[name]) for name in PARAMETERS], dtype=float)


def parameter_features(features):
    """Return the compatible EvalWeights design vector for one terminal."""
    victory = float(features.get("victory", False))
    return np.asarray([
        victory,
        float(features["victory_potion_count"])
        + 0.5 * float(features["loss_potion_count"]),
        -float(features["victory_turn"]),
        float(features["loss_monster_damage_fraction"]), -float(features["loss_monsters_alive"]),
        -float(features["loss_energy_wasted"]), float(features["loss_cards_drawn"]),
        float(features["loss_survival_turns"]),
        float(features["effective_gold_delta"]), float(features["max_hp_delta"]),
        -float(features["parasite_implant"]),
    ])


def fixed_value(features, include_death_save=True):
    value = float(features.get("victory_post_battle_healed_hp", 0.0))
    if include_death_save:
        value += float(features.get("death_save_hp_equivalent", 0.0))
    return value


def score(features, weights, include_death_save=True):
    return fixed_value(features, include_death_save) + float(
        parameter_features(features) @ parameter_vector(weights))


def corrected_parameter_features(leaf_features, original_root_features):
    """Exact current teacher-comparison contract: leaf score + root correction."""
    vector = parameter_features(leaf_features).copy()
    vector[PARAMETERS.index("gold_weight")] += float(
        original_root_features.get("effective_gold_delta", 0.0))
    vector[PARAMETERS.index("max_hp_weight")] += float(
        original_root_features.get("max_hp_delta", 0.0))
    return vector


def corrected_score(leaf_features, original_root_features, weights, include_death_save=True):
    return fixed_value(leaf_features, include_death_save) + float(
        corrected_parameter_features(leaf_features, original_root_features)
        @ parameter_vector(weights))


def untied_features(leaf_features, original_root_features):
    """Independent constrained coefficients, retained as an upper-bound diagnostic."""
    return np.asarray([
        float(leaf_features.get("victory", 0.0)),
        float(leaf_features["victory_post_battle_healed_hp"]),
        float(leaf_features["victory_potion_count"])
        + 0.5 * float(leaf_features["loss_potion_count"]),
        -float(leaf_features["victory_turn"]),
        float(leaf_features["death_save_hp_equivalent"]),
        float(leaf_features["effective_gold_delta"])
        + float(original_root_features.get("effective_gold_delta", 0.0)),
        float(leaf_features["max_hp_delta"])
        + float(original_root_features.get("max_hp_delta", 0.0)),
        -float(leaf_features["parasite_implant"]),
        float(leaf_features["loss_monster_damage_fraction"]),
        -float(leaf_features["loss_monsters_alive"]),
        -float(leaf_features["loss_energy_wasted"]),
        float(leaf_features["loss_cards_drawn"]),
        float(leaf_features["loss_potion_count"]),
        float(leaf_features["loss_survival_turns"]),
    ])


def untied_score(leaf_features, original_root_features, weights):
    return float(untied_features(leaf_features, original_root_features)
                 @ np.asarray([weights[name] for name in UNTIED_PARAMETERS]))


def load_jsonl(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_leaves(rollout_path, teacher_path, tolerance=1e-8):
    rollouts = load_jsonl(rollout_path)
    teachers = {}
    for row in load_jsonl(teacher_path):
        if not row.get("teacher_valid", False):
            continue
        teachers.setdefault(row["leaf_snapshot_id"], {})[row["replicate"]] = row
    by_leaf = defaultdict(list)
    parity_errors = []
    for row in rollouts:
        if not row.get("accepted", False):
            raise ValueError(f"unaccepted rollout row: {row.get('leaf_snapshot_id')}/{row.get('replicate')}")
        if not row.get("terminal_features_valid", False):
            raise ValueError("rollout row lacks terminal feature decomposition")
        if abs(float(row["reconstructed_terminal_value"]) - float(row["leaf_root_utility"])) > tolerance:
            parity_errors.append(row["leaf_snapshot_id"])
        features = row.get("original_root_terminal_features")
        if not features:
            raise ValueError("rollout row lacks original-root terminal features")
        by_leaf[row["leaf_snapshot_id"]].append(row)
    if parity_errors:
        raise ValueError(f"current terminal reconstruction mismatch in {len(parity_errors)} rows")

    leaves = []
    for leaf_id, rows in sorted(by_leaf.items()):
        if leaf_id not in teachers or "A" not in teachers[leaf_id]:
            continue
        if len(rows) != 32:
            raise ValueError(f"leaf {leaf_id} has {len(rows)} rows, expected 32")
        leaf_features = {}
        original_root_features = {}
        for name in FEATURES:
            leaf_features[name] = mean([float(r["terminal_features"].get(name, 0.0)) for r in rows])
            original_root_features[name] = mean([
                float(r["original_root_terminal_features"].get(name, 0.0)) for r in rows])
        leaf_features["victory"] = mean([
            1.0 if r["terminal_features"].get("victory", False) else 0.0 for r in rows])
        original_root_features["victory"] = mean([
            1.0 if r["original_root_terminal_features"].get("victory", False) else 0.0
            for r in rows])
        leaves.append({
            "leaf_snapshot_id": leaf_id, "group_id": rows[0]["group_id"],
            "source_seed": str(rows[0]["source_seed"]), "act": rows[0].get("act"),
            "encounter_category": rows[0].get("encounter_category"),
            "hp_band": rows[0].get("hp_band"),
            "source_rollout_length_band": rows[0].get("source_rollout_length_band"),
            "features": leaf_features, "original_root_features": original_root_features,
            "current_value": mean([float(r["original_root_corrected_utility"]) for r in rows]),
            "reconstructed_original_root_value": mean([
                float(r["reconstructed_original_root_value"]) for r in rows]),
            "teacher_a": float(teachers[leaf_id]["A"]["original_root_corrected_teacher_value"]),
            "teacher_b": (float(teachers[leaf_id]["B"]["original_root_corrected_teacher_value"])
                          if "B" in teachers[leaf_id] else None),
        })
    if not leaves:
        raise ValueError("no leaves with 32 feature rows and Teacher A")
    return leaves


def groups(leaves):
    result = defaultdict(list)
    for leaf in leaves:
        result[leaf["group_id"]].append(leaf)
    return {key: value for key, value in result.items() if len(value) >= 2}


def source_ids(leaves):
    return sorted({leaf["source_seed"] for leaf in leaves})


def metrics(leaves, values, teacher_key="teacher_a"):
    by_id = {leaf["leaf_snapshot_id"]: value for leaf, value in zip(leaves, values)}
    regrets, pairs, pair_ok, tops, top_ok = [], 0, 0, 0, 0
    for sibling in groups(leaves).values():
        candidate = max(sibling, key=lambda leaf: by_id[leaf["leaf_snapshot_id"]])
        teacher = max(sibling, key=lambda leaf: leaf[teacher_key])
        regrets.append(teacher[teacher_key] - candidate[teacher_key])
        tops += 1
        top_ok += candidate["leaf_snapshot_id"] == teacher["leaf_snapshot_id"]
        for i, left in enumerate(sibling):
            for right in sibling[i + 1:]:
                delta = by_id[left["leaf_snapshot_id"]] - by_id[right["leaf_snapshot_id"]]
                target = left[teacher_key] - right[teacher_key]
                if delta == 0 or target == 0:
                    continue
                pairs += 1
                pair_ok += (delta > 0) == (target > 0)
    return {
        "groups": tops, "mean_teacher_regret": mean(regrets),
        "pairwise_concordance": pair_ok / pairs if pairs else None,
        "pairwise_pairs": pairs, "top_leaf_agreement": top_ok / tops if tops else None,
    }


def weighted_pairs(leaves, teacher_key="teacher_a", vector_fn=corrected_parameter_features,
                   subtract_fixed=True):
    by_source = defaultdict(list)
    for leaf in leaves:
        by_source[leaf["source_seed"]].append(leaf)
    rows = []
    for source, source_leaves in by_source.items():
        source_groups = list(groups(source_leaves).values())
        for sibling in source_groups:
            pair_count = len(sibling) * (len(sibling) - 1) // 2
            if not pair_count:
                continue
            row_weight = 1.0 / len(source_groups) / pair_count
            for i, left in enumerate(sibling):
                for right in sibling[i + 1:]:
                    left_x = vector_fn(left["features"], left["original_root_features"])
                    right_x = vector_fn(right["features"], right["original_root_features"])
                    target = left[teacher_key] - right[teacher_key]
                    fixed = (fixed_value(left["features"]) - fixed_value(right["features"])
                             if subtract_fixed else 0.0)
                    rows.append((math.sqrt(row_weight), left_x - right_x, target - fixed))
    return rows


def fit_compatible(leaves, lam, teacher_key="teacher_a"):
    rows = weighted_pairs(leaves, teacher_key)
    if not rows:
        raise ValueError("no sibling pairs")
    x = np.asarray([weight * delta for weight, delta, _ in rows])
    y = np.asarray([weight * target for weight, _, target in rows])
    current = parameter_vector(CURRENT)
    # Minimize weighted residuals plus lambda * ||w-current||^2.
    x = np.vstack([x, math.sqrt(lam) * np.eye(len(PARAMETERS))])
    y = np.concatenate([y, math.sqrt(lam) * current])
    result = lsq_linear(x, y, bounds=(np.zeros(len(PARAMETERS)), np.full(len(PARAMETERS), np.inf)),
                        lsmr_tol="auto", tol=1e-12, max_iter=1000)
    return {name: float(value) for name, value in zip(PARAMETERS, result.x)}, result


def fit_untied(leaves, lam, teacher_key="teacher_a"):
    rows = weighted_pairs(leaves, teacher_key, untied_features, subtract_fixed=False)
    if not rows:
        raise ValueError("no sibling pairs")
    x = np.asarray([weight * delta for weight, delta, _ in rows])
    y = np.asarray([weight * target for weight, _, target in rows])
    x = np.vstack([x, math.sqrt(lam) * np.eye(len(UNTIED_PARAMETERS))])
    y = np.concatenate([y, math.sqrt(lam) * np.zeros(len(UNTIED_PARAMETERS))])
    result = lsq_linear(x, y, bounds=(np.zeros(len(UNTIED_PARAMETERS)),
                                      np.full(len(UNTIED_PARAMETERS), np.inf)),
                        lsmr_tol="auto", tol=1e-12, max_iter=1000)
    return {name: float(value) for name, value in zip(UNTIED_PARAMETERS, result.x)}, result


def select_lambda(train):
    ids = source_ids(train)
    if len(ids) < 3:
        return 1.0
    folds = [set(ids[i::3]) for i in range(3)]
    choices = []
    for lam in LAMBDAS:
        fold_regrets = []
        for held in folds:
            fit_rows = [leaf for leaf in train if leaf["source_seed"] not in held]
            eval_rows = [leaf for leaf in train if leaf["source_seed"] in held]
            weights, _ = fit_compatible(fit_rows, lam)
            fold_regrets.append(metrics(eval_rows, [corrected_score(
                x["features"], x["original_root_features"], weights) for x in eval_rows])["mean_teacher_regret"])
        choices.append((mean(fold_regrets), lam))
    return min(choices, key=lambda item: (item[0], item[1]))[1]


def crossfit(leaves):
    ids = source_ids(leaves)
    predictions = {}
    fold_receipts = []
    for fold, held in enumerate([set(ids[i::5]) for i in range(5)]):
        train = [leaf for leaf in leaves if leaf["source_seed"] not in held]
        test = [leaf for leaf in leaves if leaf["source_seed"] in held]
        lam = select_lambda(train)
        weights, solver = fit_compatible(train, lam)
        for leaf in test:
            predictions[leaf["leaf_snapshot_id"]] = corrected_score(
                leaf["features"], leaf["original_root_features"], weights)
        fold_receipts.append({"fold": fold, "held_out_sources": sorted(held), "lambda": lam,
                              "weights": weights, "solver_success": bool(solver.success)})
    values = [predictions[leaf["leaf_snapshot_id"]] for leaf in leaves]
    return metrics(leaves, values), fold_receipts, predictions


def crossfit_untied(leaves):
    ids = source_ids(leaves)
    predictions = {}
    for held in [set(ids[i::5]) for i in range(5)]:
        train = [leaf for leaf in leaves if leaf["source_seed"] not in held]
        test = [leaf for leaf in leaves if leaf["source_seed"] in held]
        weights, _ = fit_untied(train, 1.0)
        for leaf in test:
            predictions[leaf["leaf_snapshot_id"]] = untied_score(
                leaf["features"], leaf["original_root_features"], weights)
    return metrics(leaves, [predictions[leaf["leaf_snapshot_id"]] for leaf in leaves]), predictions


def bootstrap_delta(leaves, baseline_values, candidate_values, teacher_key="teacher_a", replicates=2000):
    by_source = defaultdict(list)
    for leaf, base, candidate in zip(leaves, baseline_values, candidate_values):
        by_source[leaf["source_seed"]].append((leaf, base, candidate))
    source_list = sorted(by_source)
    rng = random.Random(20260921)
    deltas = []
    for _ in range(replicates):
        sample = []
        for _ in source_list:
            sample.extend(by_source[rng.choice(source_list)])
        sampled_leaves = [row[0] for row in sample]
        base = [row[1] for row in sample]
        candidate = [row[2] for row in sample]
        base_metric = metrics(sampled_leaves, base, teacher_key)["mean_teacher_regret"]
        candidate_metric = metrics(sampled_leaves, candidate, teacher_key)["mean_teacher_regret"]
        if base_metric is not None and candidate_metric is not None:
            deltas.append(base_metric - candidate_metric)
    return {"replicates": len(deltas), "p025": percentile(deltas, 0.025),
            "p500": percentile(deltas, 0.5), "p975": percentile(deltas, 0.975)}


def component_audit(leaves):
    rows = []
    leaf_contributions = {
        "victory_post_battle_healed_hp": [],
        "death_save_hp_equivalent": [],
        **{name: [] for name in PARAMETERS},
    }
    for leaf in leaves:
        features = leaf["features"]
        x = corrected_parameter_features(features, leaf["original_root_features"])
        contributions = x * parameter_vector(CURRENT)
        leaf_contributions["victory_post_battle_healed_hp"].append(
            float(features["victory_post_battle_healed_hp"]))
        leaf_contributions["death_save_hp_equivalent"].append(
            float(features["death_save_hp_equivalent"]))
        for name, value in zip(PARAMETERS, contributions):
            leaf_contributions[name].append(float(value))
    total = [leaf["current_value"] for leaf in leaves]
    teacher_a_residuals = [leaf["current_value"] - leaf["teacher_a"] for leaf in leaves]
    teacher_b_indices = [index for index, leaf in enumerate(leaves)
                         if leaf["teacher_b"] is not None]
    teacher_b_residuals = [leaves[index]["current_value"] - leaves[index]["teacher_b"]
                           for index in teacher_b_indices]
    for name, values in leaf_contributions.items():
        teacher_b_values = [values[index] for index in teacher_b_indices]
        values = leaf_contributions[name]
        rows.append({
            "component": name, "nonzero_rate": sum(v != 0 for v in values) / len(values),
            "mean_contribution": mean(values), "std": statistics.pstdev(values),
            "p95_magnitude": percentile(sorted(abs(v) for v in values), 0.95),
            "share_of_q32_variance": (np.var(values) / np.var(total) if np.var(total) else None),
            "correlation_with_teacher_a_residual": corr(values, teacher_a_residuals),
            "correlation_with_teacher_b_residual": corr(teacher_b_values, teacher_b_residuals),
        })
    return rows


def ablations(leaves, bootstrap_replicates):
    names = ["DEFAULT", "NO_WIN_TURN_PENALTY", "NO_POTION_VALUE", "NO_DEATH_SAVE",
             "NO_GOLD", "NO_MAX_HP", "NO_PARASITE", "NO_MONSTER_DAMAGE",
             "NO_ALIVE_PENALTY", "NO_ENERGY_WASTE", "NO_DRAW", "NO_SURVIVAL"]
    output = {}
    for name in names:
        weights = dict(CURRENT)
        include_death = True
        if name == "NO_WIN_TURN_PENALTY": weights["victory_turn_penalty"] = 0
        elif name == "NO_POTION_VALUE": weights["potion_weight"] = 0
        elif name == "NO_DEATH_SAVE": include_death = False
        elif name == "NO_GOLD": weights["gold_weight"] = 0
        elif name == "NO_MAX_HP": weights["max_hp_weight"] = 0
        elif name == "NO_PARASITE": weights["parasite_penalty"] = 0
        elif name == "NO_MONSTER_DAMAGE": weights["monster_damage_weight"] = 0
        elif name == "NO_ALIVE_PENALTY": weights["alive_weight"] = 0
        elif name == "NO_ENERGY_WASTE": weights["energy_waste_weight"] = 0
        elif name == "NO_DRAW": weights["draw_weight"] = 0
        elif name == "NO_SURVIVAL": weights["turn_survival_weight"] = 0
        values = [corrected_score(leaf["features"], leaf["original_root_features"],
                                  weights, include_death) for leaf in leaves]
        teacher_b_leaves = [x for x in leaves if x["teacher_b"] is not None]
        teacher_b_values = [v for x, v in zip(leaves, values) if x["teacher_b"] is not None]
        baseline = [corrected_score(leaf["features"], leaf["original_root_features"], CURRENT)
                    for leaf in leaves]
        output[name] = {
            "teacher_a": metrics(leaves, values, "teacher_a"),
            "teacher_b": metrics(teacher_b_leaves, teacher_b_values, "teacher_b"),
            "source_bootstrap_baseline_minus_ablation_teacher_a": bootstrap_delta(
                leaves, baseline, values, "teacher_a", bootstrap_replicates),
            "source_bootstrap_baseline_minus_ablation_teacher_b": bootstrap_delta(
                teacher_b_leaves,
                [corrected_score(x["features"], x["original_root_features"], CURRENT)
                 for x in teacher_b_leaves],
                teacher_b_values, "teacher_b", bootstrap_replicates),
        }
    return output


def distribution(values):
    return {"p05": percentile(values, 0.05), "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95), "count": len(values)}


def cross_outcome_ordering(leaves, weights):
    values = [(leaf, corrected_score(leaf["features"], leaf["original_root_features"], weights))
              for leaf in leaves]
    victories = [value for leaf, value in values if leaf["features"].get("victory", 0.0) > 0.5]
    losses = [value for leaf, value in values if leaf["features"].get("victory", 0.0) <= 0.5]
    return {
        "victory": distribution(victories), "ordinary_loss": distribution(losses),
        "minimum_victory_value": min(victories) if victories else None,
        "maximum_loss_value": max(losses) if losses else None,
        "losses_at_or_above_minimum_victory": sum(value >= min(victories)
                                                   for value in losses) if victories else None,
    }


def subgroup_diagnostics(leaves, baseline, candidate):
    output = {}
    for field in ("act", "hp_band", "source_rollout_length_band"):
        values = defaultdict(list)
        for leaf, base, fitted in zip(leaves, baseline, candidate):
            value = leaf.get(field)
            if value is not None:
                values[str(value)].append((leaf, base, fitted))
        if not values:
            output[field] = {"available": False, "reason": "source corpus omits this metadata"}
            continue
        output[field] = {
            "available": True,
            "groups": {
                key: {
                    "count": len(rows),
                    "baseline_teacher_a": metrics([row[0] for row in rows],
                                                    [row[1] for row in rows], "teacher_a"),
                    "candidate_teacher_a": metrics([row[0] for row in rows],
                                                     [row[2] for row in rows], "teacher_a"),
                }
                for key, rows in sorted(values.items())
            },
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollouts", type=Path, required=True)
    parser.add_argument("--teachers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args()
    leaves = load_leaves(args.rollouts, args.teachers)
    baseline = [corrected_score(leaf["features"], leaf["original_root_features"], CURRENT)
                for leaf in leaves]
    recorded = [leaf["current_value"] for leaf in leaves]
    reconstruction_error = max(abs(a - b) for a, b in zip(baseline, recorded))
    if reconstruction_error > 1e-7:
        raise SystemExit(f"original-root reconstruction mismatch max={reconstruction_error}")
    crossfit_metrics, folds, predictions = crossfit(leaves)
    crossfit_untied_metrics, untied_predictions = crossfit_untied(leaves)
    candidate = [predictions[leaf["leaf_snapshot_id"]] for leaf in leaves]
    teacher_b_rows = [leaf for leaf in leaves if leaf["teacher_b"] is not None]
    teacher_b_candidate = [predictions[leaf["leaf_snapshot_id"]] for leaf in teacher_b_rows]
    teacher_b_baseline = [corrected_score(leaf["features"], leaf["original_root_features"], CURRENT)
                          for leaf in teacher_b_rows]
    baseline_a = metrics(leaves, baseline, "teacher_a")
    baseline_b = metrics(teacher_b_rows, teacher_b_baseline, "teacher_b")
    candidate_b = metrics(teacher_b_rows, teacher_b_candidate, "teacher_b")
    full_weights, _ = fit_compatible(leaves, select_lambda(leaves))
    full_untied_weights, _ = fit_untied(leaves, 1.0)
    dev_gain = ((baseline_a["mean_teacher_regret"] - crossfit_metrics["mean_teacher_regret"])
                / baseline_a["mean_teacher_regret"] if baseline_a["mean_teacher_regret"] else None)
    result = {
        "schema": "silver_terminal_value_audit_v1",
        "status": "development_only",
        "source_count": len(source_ids(leaves)), "leaf_count": len(leaves),
        "group_count": len(groups(leaves)), "rollout_count": len(leaves) * 32,
        "current_weights": CURRENT,
        "current_reconstruction_max_abs_error": reconstruction_error,
        "component_audit": component_audit(leaves),
        "ablations": ablations(leaves, args.bootstrap),
        "baseline": {"teacher_a": baseline_a, "teacher_b": baseline_b},
        "cross_fitted_compatible": {"teacher_a": crossfit_metrics, "teacher_b": candidate_b,
                                    "dev_regret_reduction": dev_gain, "folds": folds},
        "fitted_compatible_development_only": full_weights,
        "untied_diagnostic": {"cross_fitted_teacher_a": crossfit_untied_metrics,
                              "fitted_development_only": full_untied_weights},
        "bootstrap_baseline_minus_candidate_teacher_a": bootstrap_delta(
            leaves, baseline, candidate, "teacher_a", args.bootstrap),
        "bootstrap_baseline_minus_candidate_teacher_b": bootstrap_delta(
            teacher_b_rows, teacher_b_baseline, teacher_b_candidate, "teacher_b", args.bootstrap),
        "gap_recovery_against_zero_regret_ceiling": {
            "baseline_regret": baseline_a["mean_teacher_regret"],
            "candidate_regret": crossfit_metrics["mean_teacher_regret"],
            "fraction_of_zero_regret_gap_recovered": dev_gain,
            "note": "Zero regret is an optimistic metric ceiling, not a true game-objective oracle.",
        },
        "cross_outcome_ordering": {
            "current": cross_outcome_ordering(leaves, CURRENT),
            "fitted_development_only": cross_outcome_ordering(leaves, full_weights),
        },
        "subgroup_diagnostics": subgroup_diagnostics(leaves, baseline, candidate),
        "classification": ("TERMINAL_REWEIGHT_DEV_PROMISING" if dev_gain is not None and dev_gain >= 0.15
                            else ("TERMINAL_FORM_TOO_RESTRICTIVE"
                                  if baseline_a["mean_teacher_regret"]
                                  and (baseline_a["mean_teacher_regret"]
                                       - crossfit_untied_metrics["mean_teacher_regret"])
                                  / baseline_a["mean_teacher_regret"] >= 0.15
                                  else "TERMINAL_REWEIGHT_HEADROOM_INSUFFICIENT")),
        "interpretation": "Teacher A/B remain Silver-objective labels; this measures fixed SimpleAgent trajectory scoring only.",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"], "sources": len(source_ids(leaves)),
                      "leaves": len(leaves), "teacher_a_regret": crossfit_metrics["mean_teacher_regret"]}, indent=2))


if __name__ == "__main__":
    main()
