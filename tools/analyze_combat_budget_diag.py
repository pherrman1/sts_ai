#!/usr/bin/env python3
"""Analyze paired 500-prefix/10k-reference combat-budget diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict


REQUIRED = {
    "run_seed", "combat_id", "decision_index", "transaction_subdecision_index",
    "checkpoint_simulations", "total_simulations", "checkpoint_action",
    "final_action", "agreement", "room_type", "encounter",
    "checkpoint_top_q_gap", "checkpoint_top_q_gap_valid",
    "checkpoint_top_visit_share", "checkpoint_second_visit_share",
    "checkpoint_top_second_visit_ratio", "checkpoint_visit_entropy",
    "checkpoint_legal_actions",
}


def load(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        rows = list(reader)
    for row in rows:
        if int(row["checkpoint_simulations"]) != 500 or int(row["total_simulations"]) != 10000:
            raise ValueError("all rows must be 500-checkpoint/10000-reference rows")
        if row["agreement"] not in ("0", "1"):
            raise ValueError("agreement must be 0 or 1")
    return rows


def auc(scores, labels):
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    rank_sum = 0.0
    i = 0
    while i < len(pairs):
        j = i + 1
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        rank = (i + 1 + j) / 2.0
        rank_sum += rank * sum(label for _, label in pairs[i:j])
        i = j
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def auprc(scores, labels):
    positives = sum(labels)
    if not positives or positives == len(labels):
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    for index in order:
        if labels[index]:
            tp += 1
        else:
            fp += 1
        recall = tp / positives
        precision = tp / (tp + fp)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def risk_coverage(rows, score_key, direction):
    """Choose a safe-stop threshold on rows, then evaluate unchanged rows."""
    candidates = sorted({float(row[score_key]) for row in rows})
    if direction == "lower-risk":
        candidates = list(reversed(candidates))
    chosen = None
    for threshold in candidates:
        selected = [row for row in rows if ((float(row[score_key]) >= threshold)
                    if direction == "higher-confidence" else (float(row[score_key]) <= threshold))]
        if not selected:
            continue
        false_stops = sum(row["fight_requires_more"] == "1" for row in selected)
        rate = false_stops / len(selected)
        if rate <= 0.05:
            chosen = (threshold, selected, rate)
            break
    if chosen is None:
        return {"threshold": None, "coverage": 0.0, "false_stop_rate": None, "stopped": 0}
    threshold, selected, false_rate = chosen
    return {"threshold": threshold, "coverage": len(selected) / len(rows),
            "false_stop_rate": false_rate, "stopped": len(selected)}


def metric_specs():
    return {
        "q_gap": ("checkpoint_top_q_gap", "higher-confidence"),
        "top_visit_share": ("checkpoint_top_visit_share", "higher-confidence"),
        "second_visit_share": ("checkpoint_second_visit_share", "lower-risk"),
        "top_second_visit_ratio": ("checkpoint_top_second_visit_ratio", "higher-confidence"),
        "visit_entropy": ("checkpoint_visit_entropy", "lower-risk"),
        "legal_actions": ("checkpoint_legal_actions", "lower-risk"),
    }


def score(row, key, direction):
    value = float(row[key])
    return value if direction == "lower-risk" else -value


def analyze_partition(rows):
    if not rows:
        return {"fights": 0, "stable_fights": 0, "unstable_fights": 0, "metrics": {}}
    groups = defaultdict(list)
    for row in rows:
        groups[row["combat_id"]].append(row)
    fights = []
    for combat_id, decisions in groups.items():
        decisions.sort(key=lambda r: (int(r["decision_index"]),
                                      int(r["transaction_subdecision_index"])))
        first = decisions[0]
        sufficient = all(row["agreement"] == "1" for row in decisions)
        first = dict(first)
        first["fight_requires_more"] = "0" if sufficient else "1"
        first["decision_count"] = len(decisions)
        fights.append(first)
    labels = [int(row["fight_requires_more"]) for row in fights]
    result = {
        "fights": len(fights),
        "stable_fights": labels.count(0),
        "unstable_fights": labels.count(1),
        "per_decision_rows": len(rows),
        "per_decision_agreement_rate": sum(row["agreement"] == "1" for row in rows) / len(rows),
        "per_fight_500_sufficient_rate": labels.count(0) / len(labels),
        "metrics": {},
    }
    if len(set(labels)) < 2:
        return result
    for name, (column, direction) in metric_specs().items():
        valid = [row for row in fights if row[column] not in ("", "NA")]
        scores = [score(row, column, direction) for row in valid]
        valid_labels = [int(row["fight_requires_more"]) for row in valid]
        risk = {"auc": auc(scores, valid_labels), "auprc": auprc(scores, valid_labels)}
        # The training caller supplies a threshold; this is a descriptive
        # within-partition curve for compact reports and self-tests.
        risk["threshold_candidates"] = len(set(float(row[column]) for row in valid))
        result["metrics"][name] = risk
    return result


def analyze(rows):
    seeds = sorted({int(row["run_seed"]) for row in rows})
    if len(seeds) < 2:
        raise ValueError("need at least two seeds")
    split = max(1, len(seeds) // 2)
    train_seeds = set(seeds[:split])
    train_rows = [row for row in rows if int(row["run_seed"]) in train_seeds]
    holdout_rows = [row for row in rows if int(row["run_seed"]) not in train_seeds]
    train_groups = defaultdict(list)
    holdout_groups = defaultdict(list)
    for row in train_rows:
        train_groups[row["combat_id"]].append(row)
    for row in holdout_rows:
        holdout_groups[row["combat_id"]].append(row)

    def first_rows(groups):
        output = []
        for decisions in groups.values():
            decisions.sort(key=lambda r: (int(r["decision_index"]),
                                          int(r["transaction_subdecision_index"])))
            sufficient = all(row["agreement"] == "1" for row in decisions)
            row = dict(decisions[0])
            row["fight_requires_more"] = "0" if sufficient else "1"
            output.append(row)
        return output

    train_fights = first_rows(train_groups)
    holdout_fights = first_rows(holdout_groups)
    risk_coverage_result = {}
    for name, (column, direction) in metric_specs().items():
        if direction == "higher-confidence":
            ordered = sorted({float(row[column]) for row in train_fights}, reverse=True)
            selector = lambda row, threshold: float(row[column]) >= threshold
        else:
            ordered = sorted({float(row[column]) for row in train_fights})
            selector = lambda row, threshold: float(row[column]) <= threshold
        selected = None
        for threshold in ordered:
            candidates = [row for row in train_fights if selector(row, threshold)]
            if candidates and sum(row["fight_requires_more"] == "1" for row in candidates) / len(candidates) <= 0.05:
                selected = (threshold, candidates)
                break
        if selected is None:
            risk_coverage_result[name] = {"threshold": None, "train": {}, "holdout": {}}
            continue
        threshold, train_selected = selected
        holdout_selected = [row for row in holdout_fights if selector(row, threshold)]
        def summarize(selected_rows, total):
            return {
                "stopped": len(selected_rows), "coverage": len(selected_rows) / total if total else None,
                "false_stop_rate": (sum(row["fight_requires_more"] == "1" for row in selected_rows)
                                     / len(selected_rows) if selected_rows else None),
            }
        risk_coverage_result[name] = {
            "threshold": threshold,
            "train": summarize(train_selected, len(train_fights)),
            "holdout": summarize(holdout_selected, len(holdout_fights)),
        }

    category = Counter((row["room_type"], row["encounter"])
                       for row in holdout_fights if row["fight_requires_more"] == "1")
    return {
        "schema": "combat_budget_diag_v1",
        "seeds": seeds,
        "train_seeds": sorted(train_seeds),
        "holdout_seeds": sorted(set(seeds) - train_seeds),
        "train": analyze_partition(train_rows),
        "holdout": analyze_partition(holdout_rows),
        "holdout_unstable_categories": [
            {"room_type": room, "encounter": encounter, "unstable_fights": count}
            for (room, encounter), count in sorted(category.items())],
        "train_thresholds_holdout_risk_coverage": risk_coverage_result,
    }


def self_test():
    fields = ["run_seed", "combat_id", "decision_index", "transaction_subdecision_index",
              "checkpoint_simulations", "total_simulations", "checkpoint_action", "final_action",
              "agreement", "room_type", "encounter", "checkpoint_top_q_gap",
              "checkpoint_top_q_gap_valid", "checkpoint_top_visit_share",
              "checkpoint_second_visit_share", "checkpoint_top_second_visit_ratio",
              "checkpoint_visit_entropy", "checkpoint_legal_actions"]
    rows = []
    for seed, stable in ((1, True), (2, True), (3, False), (4, False)):
        for decision in range(2):
            row = {field: "0" for field in fields}
            row.update(run_seed=str(seed), combat_id=f"{seed}:1:{seed}:2",
                       decision_index=str(decision), transaction_subdecision_index="-1",
                       checkpoint_simulations="500", total_simulations="10000",
                       checkpoint_action="a", final_action="a" if stable else ("b" if decision else "a"),
                       agreement="1" if stable or decision == 0 else "0", room_type="hallway",
                       encounter="2", checkpoint_top_q_gap=str(1 + seed),
                       checkpoint_top_visit_share=str(.5 + seed / 20),
                       checkpoint_second_visit_share=".2", checkpoint_top_second_visit_ratio="2",
                       checkpoint_visit_entropy=".7", checkpoint_legal_actions="4")
            rows.append(row)
    result = analyze(rows)
    assert result["train"]["fights"] == 2
    assert result["holdout"]["unstable_fights"] == 2
    assert result["holdout"]["per_decision_agreement_rate"] == 0.5
    print("analyze_combat_budget_diag self-test PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.csv:
        parser.error("csv is required unless --self-test is used")
    result = analyze(load(args.csv))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
