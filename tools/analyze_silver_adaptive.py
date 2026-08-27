#!/usr/bin/env python3
"""Screen cheap Silver-1k root signals for a two-tier 1k->3.7k rule.

This is deliberately descriptive: each signal is ranked and thresholded on
its own.  It does not fit a classifier or select a policy from a learned
model.  The diagnostic CSV is one row per root action; root-level metrics are
computed only on the clean deterministic joint subset used by PR #66.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def _float(row, key):
    value = row.get(key, "")
    return None if value in ("", "NA", "nan", "NaN") else float(value)


def _summaries(encoded):
    if not encoded:
        return []
    output = []
    for entry in encoded.split(";"):
        fields = entry.rsplit("@", 4)
        if len(fields) != 5:
            raise ValueError("invalid root-action summary: " + entry)
        fingerprint, visits, child_sims, eval_sum, q = fields
        output.append({
            "fingerprint": fingerprint,
            "visits": int(visits),
            "child_sims": int(child_sims),
            "eval_sum": float(eval_sum),
            "q": None if q == "NA" else float(q),
        })
    return output


def _groups(rows):
    result = defaultdict(list)
    for row in rows:
        result[(row["run_seed"], row["floor"], row["encounter"],
               row["combat_decision_ordinal"])].append(row)
    return result


def _root_features(root):
    first = root[0]
    summaries = _summaries(first.get("low_root_action_summaries", ""))
    if not summaries:
        # This fallback keeps the analyzer useful on an older CSV, but only
        # exposes what that schema actually recorded.
        chosen_visits = _float(first, "chosen_1k_visits")
        return {
            "top_visit_share": chosen_visits / 1000.0 if chosen_visits is not None else None,
            "top_two_visit_gap_share": None,
            "top_q_gap": None,
            "visit_entropy": None,
            "legal_actions": None,
        }
    ranked = sorted(summaries, key=lambda item: item["visits"], reverse=True)
    total = sum(item["visits"] for item in ranked)
    if total <= 0:
        return {"top_visit_share": None, "top_two_visit_gap_share": None,
                "top_q_gap": None, "visit_entropy": None,
                "legal_actions": len(ranked)}
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else {"visits": 0, "q": None}
    q_gap = (top["q"] - second["q"]
             if top["q"] is not None and second["q"] is not None else None)
    shares = [item["visits"] / total for item in ranked if item["visits"] > 0]
    return {
        "top_visit_share": top["visits"] / total,
        "top_two_visit_gap_share": (top["visits"] - second["visits"]) / total,
        "top_q_gap": q_gap,
        "visit_entropy": -sum(share * math.log(share) for share in shares),
        "legal_actions": len(ranked),
    }


def _rank(values):
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(ordered):
        end = pos + 1
        while end < len(ordered) and ordered[end][1] == ordered[pos][1]:
            end += 1
        average = (pos + end - 1) / 2.0 + 1.0
        for index, _ in ordered[pos:end]:
            ranks[index] = average
        pos = end
    return ranks


def _spearman(values, targets):
    if len(values) < 2:
        return None
    lhs, rhs = _rank(values), _rank(targets)
    lhs_mean, rhs_mean = statistics.mean(lhs), statistics.mean(rhs)
    numerator = sum((a - lhs_mean) * (b - rhs_mean) for a, b in zip(lhs, rhs))
    denom_l = math.sqrt(sum((a - lhs_mean) ** 2 for a in lhs))
    denom_r = math.sqrt(sum((b - rhs_mean) ** 2 for b in rhs))
    return numerator / (denom_l * denom_r) if denom_l and denom_r else 0.0


def _auc(scores, labels):
    positives = [score for score, label in zip(scores, labels) if label]
    negatives = [score for score, label in zip(scores, labels) if not label]
    if not positives or not negatives:
        return None
    wins = sum(1.0 if pos > neg else 0.5 if pos == neg else 0.0
               for pos in positives for neg in negatives)
    return wins / (len(positives) * len(negatives))


def _binary_summary(scores, labels):
    return {
        "spearman": _spearman(scores, [int(label) for label in labels]),
        "auroc": _auc(scores, labels),
    }


def _thresholds(values):
    ordered = sorted(values)
    if not ordered:
        return []
    # Four coarse quantile cut points are enough for a screen and avoid
    # silently tuning a threshold against every observed root.
    return sorted(set(ordered[min(len(ordered) - 1, int(len(ordered) * q))]
                      for q in (0.2, 0.4, 0.6, 0.8)))


def _quality_summary(roots, action_key, reference_key="chosen_37k"):
    usable = [item for item in roots if item.get(action_key)]
    if not usable:
        return None
    regrets = [item["regrets"][item[action_key]] for item in usable]
    return {
        "roots": len(usable),
        "top_action_agreement": sum(
            item[action_key] == item[reference_key] for item in usable) / len(usable),
        "action_disagreement": sum(
            item[action_key] != item[reference_key] for item in usable) / len(usable),
        "mean_regret": statistics.mean(regrets),
        "median_regret": statistics.median(regrets),
    }


def analyze(rows, high_regret_threshold=0.1):
    roots = []
    for key, root in _groups(rows).items():
        by_action = {row["action_fingerprint"]: row for row in root}
        chosen_1k, chosen_37k = root[0]["chosen_1k"], root[0]["chosen_37k"]
        if chosen_1k not in by_action or chosen_37k not in by_action:
            continue
        if by_action[chosen_1k].get("stochastic") != "0" \
                or by_action[chosen_37k].get("stochastic") != "0":
            continue
        best = max(float(row["reference_value"]) for row in root
                   if row.get("stochastic") == "0")
        regret_1k = best - float(by_action[chosen_1k]["reference_value"])
        regret_37k = best - float(by_action[chosen_37k]["reference_value"])
        adaptive_action = root[0].get("adaptive_action", "")
        if adaptive_action not in by_action:
            adaptive_action = None
        item = {
            "key": key,
            "chosen_1k": chosen_1k,
            "chosen_37k": chosen_37k,
            "adaptive_action": adaptive_action,
            "regrets": {
                action: best - float(row["reference_value"])
                for action, row in by_action.items()
            },
            "changed": chosen_1k != chosen_37k,
            "regret_1k": regret_1k,
            "regret_37k": regret_37k,
            "beneficial": regret_37k + 1e-9 < regret_1k,
            "high_regret": regret_1k >= high_regret_threshold,
        }
        item.update(_root_features(root))
        roots.append(item)

    definitions = {
        "top_visit_share": "low is uncertain",
        "top_two_visit_gap_share": "low is uncertain",
        "top_q_gap": "low is uncertain",
        "visit_entropy": "high is uncertain",
        "legal_actions": "high is uncertain",
    }
    candidates = {}
    for signal, direction in definitions.items():
        usable = [item for item in roots if item[signal] is not None]
        if not usable:
            candidates[signal] = {"direction": direction, "roots": 0}
            continue
        values = [item[signal] for item in usable]
        labels = [item["beneficial"] for item in usable]
        scores = [-value if "low" in direction else value for value in values]
        tables = []
        for threshold in _thresholds(values):
            escalated = [((value < threshold) if "low" in direction else (value > threshold))
                         for value in values]
            count = sum(escalated)
            beneficial = sum(label for label in labels)
            high = sum(item["high_regret"] for item in usable)
            tables.append({
                "threshold": threshold,
                "escalated_roots": count,
                "escalation_rate": count / len(usable),
                "mean_simulations": 1000.0 + 2700.0 * count / len(usable),
                "beneficial_roots": beneficial,
                "captured_beneficial_fraction": (
                    sum(flag and label for flag, label in zip(escalated, labels)) / beneficial
                    if beneficial else None),
                "high_regret_roots": high,
                "missed_high_regret_roots": sum(
                    item["high_regret"] and not flag for item, flag in zip(usable, escalated)),
            })
        candidates[signal] = {
            "direction": direction,
            "roots": len(usable),
            "beneficial_roots": sum(labels),
            "changed_roots": sum(item["changed"] for item in usable),
            "high_regret_roots": sum(item["high_regret"] for item in usable),
            "benefit": _binary_summary(scores, labels),
            "changed_action": _binary_summary(scores, [item["changed"] for item in usable]),
            "nonzero_regret": _binary_summary(
                scores, [item["regret_1k"] > 1e-9 for item in usable]),
            "thresholds": tables,
        }
    result = {
        "scope": {
            "roots": len(roots),
            "changed_roots": sum(item["changed"] for item in roots),
            "beneficial_roots": sum(item["beneficial"] for item in roots),
            "high_regret_threshold": high_regret_threshold,
            "high_regret_roots": sum(item["high_regret"] for item in roots),
        },
        "candidates": candidates,
    }
    quality = {
        "fixed_1k": _quality_summary(roots, "chosen_1k"),
        "fixed_37k": _quality_summary(roots, "chosen_37k"),
        "adaptive": _quality_summary(roots, "adaptive_action"),
    }
    adaptive_rows = [
        root[0] for root in _groups(rows).values()
        if root and root[0].get("adaptive_simulations") not in (None, "", "NA")
    ]
    if adaptive_rows:
        simulations = [float(row["adaptive_simulations"]) for row in adaptive_rows]
        escalated = [row.get("adaptive_escalated") == "1" for row in adaptive_rows]
        quality["adaptive_compute"] = {
            "roots": len(adaptive_rows),
            "average_simulations": statistics.mean(simulations),
            "escalated_roots": sum(escalated),
            "escalation_rate": sum(escalated) / len(escalated),
        }
    result["quality"] = quality
    return result


def load(path):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("diagnostic CSV has no rows")
    required = {"run_seed", "floor", "encounter", "combat_decision_ordinal",
                "action_fingerprint", "chosen_1k", "chosen_37k",
                "reference_value", "stochastic"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))
    return rows


def self_test():
    base = {"run_seed": "1", "floor": "2", "encounter": "3",
            "combat_decision_ordinal": "4", "chosen_1k": "a",
            "chosen_37k": "b", "stochastic": "0"}
    rows = []
    for fp, value in (("a", "0"), ("b", "1"), ("c", "0")):
        row = dict(base, action_fingerprint=fp, reference_value=value,
                   low_root_action_summaries="a@8@8@0@0;b@4@4@0@0;c@0@0@0@NA")
        rows.append(row)
    result = analyze(rows, high_regret_threshold=0.5)
    assert result["scope"]["roots"] == 1
    assert result["scope"]["beneficial_roots"] == 1
    assert result["candidates"]["top_visit_share"]["roots"] == 1
    assert result["candidates"]["top_visit_share"]["thresholds"]
    print("analyze_silver_adaptive self-test PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--high-regret-threshold", type=float, default=0.1)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.csv:
        parser.error("csv is required unless --self-test is used")
    rendered = json.dumps(analyze(load(args.csv), args.high_regret_threshold),
                          indent=2, sort_keys=True)
    if args.json_path:
        Path(args.json_path).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
