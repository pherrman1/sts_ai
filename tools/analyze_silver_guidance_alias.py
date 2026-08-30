#!/usr/bin/env python3
"""Recompute bounded Silver policy alias and prior-tie diagnostics.

This is deliberately an offline reader: it never trains a model, starts the
simulator, or mutates the input artifacts.  The native prediction CSV is the
frozen held-out prediction output from the 25k-A policy experiment.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def load_features(path: Path):
    groups = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("feature_schema") != "silver_parent_policy_features_v1":
            raise ValueError("unexpected policy feature schema")
        if header["feature_count"] != len(header["feature_names"]):
            raise ValueError("feature header width mismatch")
        for line_number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            row = json.loads(line)
            if len(row["features"]) != header["feature_count"]:
                raise ValueError(f"feature width mismatch at line {line_number}")
            groups[row["group_id"]].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: row["silver_order"])
    return header, groups


def load_parent_labels(path: Path, replicate: str, budget: int):
    labels = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("state_kind") != "parent":
                continue
            if row.get("replicate") != replicate or row.get("budget") != budget:
                continue
            if not row.get("teacher_valid", False):
                continue
            actions = {}
            for action in row["root_actions"]:
                if not action.get("leaf_root_q_valid", False):
                    actions = {}
                    break
                actions[action["action_fingerprint"]] = action
            if actions and len(actions) == row["root_action_count"]:
                labels[row["group_id"]] = (row, actions)
    return labels


def load_predictions(path: Path):
    predictions = defaultdict(dict)
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            predictions[row["group_id"]][row["action_fingerprint"]] = float(
                row["native_prediction"]
            )
    return predictions


def action_kind(fingerprint: str) -> str:
    action_type = fingerprint.split("/", 2)[1].split("=", 1)[1]
    return {"1": "card", "2": "potion", "3": "card_selection", "5": "end_turn"}.get(
        action_type, f"type_{action_type}"
    )


def action_kind_detail(row) -> str:
    kind = action_kind(row["action_fingerprint"])
    if kind == "card":
        # `x=0` is also the default target encoding for a non-target card.
        # Use the canonical action feature, whose position is stable because
        # the 22 action fields are appended after the state block.
        return "targeted_card" if row["features"][-12] > 0.5 else "card"
    return kind


def paired_metrics(groups, scores):
    concordant = pair_count = prediction_ties = 0.0
    top = 0
    regrets = []
    for group_id in sorted(groups):
        rows = groups[group_id]
        truth = [row["reference_q"] for row in rows]
        pred = scores[group_id]
        for left, right in itertools.combinations(range(len(rows)), 2):
            truth_delta = truth[left] - truth[right]
            if truth_delta == 0:
                continue
            pred_delta = pred[left] - pred[right]
            pair_count += 1
            if pred_delta == 0:
                prediction_ties += 1
                concordant += 0.5
            elif (pred_delta > 0) == (truth_delta > 0):
                concordant += 1
        best = max(range(len(rows)), key=lambda i: truth[i])
        chosen = max(range(len(rows)), key=lambda i: pred[i])
        top += int(best == chosen)
        regrets.append(truth[best] - truth[chosen])
    return {
        "parents": len(groups),
        "reference_pairs": int(pair_count),
        "prediction_ties": int(prediction_ties),
        "pairwise_agreement": concordant / pair_count if pair_count else None,
        "top_action_agreement": top / len(groups) if groups else None,
        "mean_regret": statistics.fmean(regrets) if regrets else None,
        "median_regret": statistics.median(regrets) if regrets else None,
    }


def attach(features, b_labels, predictions):
    groups = {}
    for group_id, (parent, actions) in b_labels.items():
        rows = features.get(group_id, [])
        if {row["action_fingerprint"] for row in rows} != set(actions):
            continue
        if predictions and set(predictions.get(group_id, {})) != set(actions):
            continue
        groups[group_id] = [
            {
                **row,
                "reference_q": float(actions[row["action_fingerprint"]]["original_root_corrected_q"]),
                "teacher_a_q": None,
            }
            for row in rows
        ]
    return groups


def alias_diagnostics(groups):
    collision_pairs = non_tied_collision_pairs = 0
    action_collision_rows = 0
    spreads = []
    unique_best_groups = set()
    uniform_collision_top_errors = []
    uniform_collision_regrets = []
    collision_kind = Counter()
    by_kind = defaultdict(lambda: {"rows": 0, "collision_rows": 0, "pairs": 0, "non_tied_pairs": 0, "spreads": []})

    for group_id, rows in groups.items():
        best_q = max(row["reference_q"] for row in rows)
        buckets = defaultdict(list)
        for row in rows:
            buckets[tuple(row["features"])].append(row)
            by_kind[action_kind_detail(row)]["rows"] += 1
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            action_collision_rows += len(bucket)
            if any(row["reference_q"] == best_q for row in bucket):
                unique_best_groups.add(group_id)
                uniform_collision_top_errors.append(
                    1.0 - sum(row["reference_q"] == best_q for row in bucket) / len(bucket)
                )
                uniform_collision_regrets.append(
                    statistics.fmean(best_q - row["reference_q"] for row in bucket)
                )
            for left, right in itertools.combinations(bucket, 2):
                collision_pairs += 1
                kind = "+".join(sorted({action_kind_detail(left), action_kind_detail(right)}))
                collision_kind[kind] += 1
                detail = by_kind[action_kind_detail(left)]
                detail["pairs"] += 1
                spread = abs(left["reference_q"] - right["reference_q"])
                detail["spreads"].append(spread)
                spreads.append(spread)
                if left["reference_q"] != right["reference_q"]:
                    non_tied_collision_pairs += 1
                    detail["non_tied_pairs"] += 1
    all_pairs = sum(len(rows) * (len(rows) - 1) // 2 for rows in groups.values())
    non_tied_pairs = sum(
        int(left["reference_q"] != right["reference_q"])
        for rows in groups.values()
        for left, right in itertools.combinations(rows, 2)
    )
    result_by_kind = {}
    for kind, detail in sorted(by_kind.items()):
        result_by_kind[kind] = {
            "rows": detail["rows"],
            "collision_rows": sum(
                1
                for group in groups.values()
                for bucket in _feature_buckets(group).values()
                if len(bucket) > 1
                for row in bucket
                if action_kind_detail(row) == kind
            ),
            "pairs": detail["pairs"],
            "non_tied_pairs": detail["non_tied_pairs"],
            "mean_q_spread": statistics.fmean(detail["spreads"]) if detail["spreads"] else None,
            "max_q_spread": max(detail["spreads"]) if detail["spreads"] else None,
        }
    return {
        "parents": len(groups),
        "actions": sum(len(rows) for rows in groups.values()),
        "all_action_pairs": all_pairs,
        "non_tied_reference_pairs": non_tied_pairs,
        "collision_pairs": collision_pairs,
        "collision_pair_fraction_all_pairs": collision_pairs / all_pairs if all_pairs else None,
        "non_tied_collision_pairs": non_tied_collision_pairs,
        "unavoidable_pairwise_error_floor": 0.5 * non_tied_collision_pairs / non_tied_pairs if non_tied_pairs else None,
        "feature_alias_pairwise_ceiling": 1.0 - 0.5 * non_tied_collision_pairs / non_tied_pairs if non_tied_pairs else None,
        "actions_in_collision": action_collision_rows,
        "action_collision_fraction": action_collision_rows / sum(len(rows) for rows in groups.values()),
        "collision_q_spread_mean": statistics.fmean(spreads) if spreads else None,
        "collision_q_spread_median": statistics.median(spreads) if spreads else None,
        "collision_q_spread_max": max(spreads) if spreads else None,
        "groups_with_best_action_in_collision": len(unique_best_groups),
        "groups_with_best_action_in_collision_fraction": len(unique_best_groups) / len(groups) if groups else None,
        "uniform_tie_top_error_conditional_on_affected_group": statistics.fmean(uniform_collision_top_errors) if uniform_collision_top_errors else None,
        "uniform_tie_mean_regret_conditional_on_affected_group": statistics.fmean(uniform_collision_regrets) if uniform_collision_regrets else None,
        "uniform_tie_top_error_over_all_parents": sum(uniform_collision_top_errors) / len(groups) if groups else None,
        "uniform_tie_mean_regret_over_all_parents": sum(uniform_collision_regrets) / len(groups) if groups else None,
        "collision_kind_pairs": dict(sorted(collision_kind.items())),
        "by_action_kind": result_by_kind,
    }


def _feature_buckets(rows):
    buckets = defaultdict(list)
    for row in rows:
        buckets[tuple(row["features"])].append(row)
    return buckets


def prior_tie_diagnostics(groups, predictions):
    tied_groups = tied_pairs = non_tied_reference_tied_pairs = unequal_prior_pairs = 0
    prior_gaps = []
    for group_id, rows in groups.items():
        scores = [predictions[group_id][row["action_fingerprint"]] for row in rows]
        if not any(left == right for left, right in itertools.combinations(scores, 2)):
            continue
        tied_groups += 1
        order = sorted(range(len(rows)), key=lambda i: (-scores[i], i))
        n = len(rows)
        denom = n * (n + 1) / 2.0
        priors = [0.0] * n
        for position, index in enumerate(order):
            priors[index] = (n - position) / denom
        for left, right in itertools.combinations(range(n), 2):
            if scores[left] != scores[right]:
                continue
            tied_pairs += 1
            if rows[left]["reference_q"] != rows[right]["reference_q"]:
                non_tied_reference_tied_pairs += 1
            gap = abs(priors[left] - priors[right])
            prior_gaps.append(gap)
            unequal_prior_pairs += int(gap != 0)
    return {
        "groups_with_exact_score_ties": tied_groups,
        "exact_tied_action_pairs": tied_pairs,
        "exact_tied_pairs_with_non_tied_25k_b_q": non_tied_reference_tied_pairs,
        "tied_pairs_with_unequal_rank_priors": unequal_prior_pairs,
        "mean_absolute_prior_gap_within_ties": statistics.fmean(prior_gaps) if prior_gaps else 0.0,
        "max_absolute_prior_gap_within_ties": max(prior_gaps) if prior_gaps else 0.0,
        "rank_prior_formula": "weight=(n-position)/(n*(n+1)/2), stable score-descending sort",
    }


def q_visit_agreement(labels, groups):
    result = {}
    for replicate in ("A", "B"):
        agree = eligible = 0
        for group_id in groups:
            if group_id not in labels[replicate]:
                continue
            _, actions = labels[replicate][group_id]
            if set(actions) != {row["action_fingerprint"] for row in groups[group_id]}:
                continue
            eligible += 1
            q_choice = max(actions, key=lambda fp: actions[fp]["original_root_corrected_q"])
            visit_choice = max(actions, key=lambda fp: actions[fp]["visits"])
            agree += int(q_choice == visit_choice)
        result[replicate] = {"eligible_multi_action_parents": eligible, "max_q_max_visit_agreement": agree / eligible if eligible else None}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    header, feature_groups = load_features(args.features)
    b_labels = load_parent_labels(args.relabels, "B", 25000)
    a_labels = load_parent_labels(args.relabels, "A", 25000)
    predictions = load_predictions(args.predictions)
    all_groups = attach(feature_groups, b_labels, predictions)
    groups = {group_id: rows for group_id, rows in all_groups.items() if len(rows) > 1}
    model_scores = {
        group_id: [predictions[group_id][row["action_fingerprint"]] for row in rows]
        for group_id, rows in groups.items()
    }
    ordering_scores = {group_id: [-float(row["silver_order"]) for row in rows] for group_id, rows in groups.items()}
    teacher_scores = {
        group_id: [float(a_labels[group_id][1][row["action_fingerprint"]]["original_root_corrected_q"]) for row in rows]
        for group_id, rows in groups.items()
        if group_id in a_labels and set(a_labels[group_id][1]) == {row["action_fingerprint"] for row in rows}
    }
    report = {
        "schema": "silver_guidance_alias_diagnostic_v1",
        "feature_schema": header["feature_schema"],
        "feature_count": header["feature_count"],
        "held_out_replicate": "25k-B",
        "budget": 25000,
        "multi_action_metrics": {
            "current_ordering": paired_metrics(groups, ordering_scores),
            "learned_model": paired_metrics(groups, model_scores),
            "teacher_25k_A": paired_metrics({k: groups[k] for k in teacher_scores}, teacher_scores),
        },
        "feature_alias": alias_diagnostics(all_groups),
        "learned_rank_prior_ties": prior_tie_diagnostics(groups, predictions),
        "max_q_vs_max_visit": q_visit_agreement({"A": a_labels, "B": b_labels}, groups),
        "input_counts": {
            "feature_groups": len(feature_groups),
            "25k_B_valid_parent_groups": len(b_labels),
            "prediction_groups": len(predictions),
            "matched_parent_groups": len(all_groups),
            "matched_multi_action_groups": len(groups),
        },
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
