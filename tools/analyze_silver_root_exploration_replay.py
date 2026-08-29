#!/usr/bin/env python3
"""Analyze the preregistered Silver root-only exploration replay.

The 25k-A labels select one lower-c candidate.  The independent 25k-B labels
are then used only for the offline gate.  Bootstrap resampling is by anchor,
not by action or replay row.
"""
import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


BUDGETS = (64, 128, 256, 1000)
CONTROL = "c25_control"
CANDIDATES = ("c18_5", "c12_5", "c9_9")


def read_replay(path):
    with open(path, encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows or rows[0].get("replay_schema") != "silver_root_exploration_replay_v1":
        raise RuntimeError(f"incompatible replay schema: {path}")
    data = [row for row in rows[1:] if "candidate" in row]
    if any(row.get("failure_row") for row in data):
        raise RuntimeError(f"replay contains failure rows: {path}")
    return rows[0], data


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def grouped(rows):
    result = {}
    for row in rows:
        key = (row["group_id"], row["budget"], row["candidate"])
        if key in result:
            raise RuntimeError(f"duplicate replay row: {key}")
        result[key] = row
    return result


def quantile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))]


def metric(rows, field):
    values = [row[field] for row in rows]
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": quantile(values, 0.95),
        "max": max(values),
    }


def summary(rows, label_prefix="b"):
    top_field = f"{label_prefix}_top_action"
    regret_field = f"{label_prefix}_regret"
    return {
        "n": len(rows),
        "top_action_agreement": statistics.fmean(row[top_field] for row in rows),
        "selected_regret": metric(rows, regret_field),
        "regret_ge_1": sum(row[regret_field] >= 1.0 for row in rows),
        "regret_ge_3": sum(row[regret_field] >= 3.0 for row in rows),
        "root_action_set_failures": sum(not row["root_action_set_equal"] for row in rows),
        "accounting_failures": sum(not row["exact_budget_accounting"] for row in rows),
        "mean_wall_micros": statistics.fmean(row["wall_micros"] for row in rows),
    }


def paired(control, candidate, field):
    keys = sorted(control)
    if set(keys) != set(candidate):
        raise RuntimeError("control/candidate anchor sets differ")
    return [candidate[key][field] - control[key][field] for key in keys]


def bootstrap_probability(values, predicate, seed, draws=10000):
    rng = random.Random(seed)
    successes = 0
    n = len(values)
    for _ in range(draws):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        if predicate(sample):
            successes += 1
    return successes / draws


def row_map(rows, candidate, budget, label_prefix):
    return {
        row["group_id"]: row
        for row in rows
        if row["candidate"] == candidate and row["budget"] == budget
    }


def evaluate_population(rows, label_prefix):
    result = {}
    for candidate in (CONTROL,) + CANDIDATES:
        for budget in BUDGETS:
            selected = [row for row in rows
                        if row["candidate"] == candidate and row["budget"] == budget]
            result[f"{candidate}/{budget}"] = summary(selected, label_prefix)
    return result


def selection_analysis(rows):
    by = grouped(rows)
    scores = {}
    details = {}
    for candidate in CANDIDATES:
        budget_details = []
        rejected = []
        for budget in BUDGETS[:3]:
            control = row_map(rows, CONTROL, budget, "a")
            treatment = row_map(rows, candidate, budget, "a")
            top_diffs = paired(control, treatment, "a_top_action")
            regret_reductions = [-value for value in paired(control, treatment, "a_regret")]
            top_improvement = statistics.fmean(top_diffs)
            regret_reduction = statistics.fmean(regret_reductions)
            top_scale = statistics.pstdev(top_diffs) or 1.0
            regret_scale = statistics.pstdev(regret_reductions) or 1.0
            budget_details.append({
                "budget": budget,
                "top_agreement_improvement": top_improvement,
                "mean_regret_reduction": regret_reduction,
                "standardized_improvement": (top_improvement / top_scale
                                               + regret_reduction / regret_scale) / 2.0,
                "new_ge_3_regrets": sum(
                    treatment[group]["a_regret"] >= 3.0
                    and control[group]["a_regret"] < 3.0 for group in treatment),
            })
            if budget in (128, 256) and budget_details[-1]["new_ge_3_regrets"]:
                rejected.append(f"new_ge_3_regret_at_{budget}")
        all_control = row_map(rows, CONTROL, 1000, "a")
        all_treatment = row_map(rows, candidate, 1000, "a")
        cpu_control = statistics.fmean(row["wall_micros"] for row in all_control.values())
        cpu_treatment = statistics.fmean(row["wall_micros"] for row in all_treatment.values())
        cpu_ratio = cpu_treatment / cpu_control
        if cpu_ratio > 1.05:
            rejected.append("cpu_above_1.05")
        score = statistics.fmean(item["standardized_improvement"] for item in budget_details)
        scores[candidate] = score
        details[candidate] = {
            "budgets": budget_details,
            "score": score,
            "cpu_ratio_at_1000": cpu_ratio,
            "rejection_reasons": rejected,
        }
    eligible = [candidate for candidate in CANDIDATES if not details[candidate]["rejection_reasons"]]
    selected = None if not eligible else sorted(
        eligible,
        key=lambda candidate: (-scores[candidate],
                               abs(float(candidate[1:].replace("_", ".")) - 25.0)))[0]
    return selected, details


def offline_gate(rows, selected):
    by = grouped(rows)
    budget_results = []
    for budget in BUDGETS[:3]:
        control = row_map(rows, CONTROL, budget, "b")
        treatment = row_map(rows, selected, budget, "b")
        top_diff = statistics.fmean(paired(control, treatment, "b_top_action"))
        regret_reduction = -statistics.fmean(paired(control, treatment, "b_regret"))
        control_regret = statistics.fmean(row["b_regret"] for row in control.values())
        budget_results.append({
            "budget": budget,
            "top_agreement_improvement": top_diff,
            "mean_regret_reduction": regret_reduction,
            "non_worse_both": top_diff >= 0.0 and regret_reduction >= 0.0,
            "threshold_improvement": top_diff >= 0.05 or (
                control_regret > 0.0 and regret_reduction >= 0.15 * control_regret),
            "control_mean_regret": control_regret,
            "treatment_mean_regret": statistics.fmean(row["b_regret"] for row in treatment.values()),
            "control_top_agreement": statistics.fmean(row["b_top_action"] for row in control.values()),
            "treatment_top_agreement": statistics.fmean(row["b_top_action"] for row in treatment.values()),
        })

    control1000 = row_map(rows, CONTROL, 1000, "b")
    treatment1000 = row_map(rows, selected, 1000, "b")
    control_missed = sum(not row["b_top_action"] for row in control1000.values())
    treatment_missed = sum(not row["b_top_action"] for row in treatment1000.values())
    control_mean = statistics.fmean(row["b_regret"] for row in control1000.values())
    treatment_mean = statistics.fmean(row["b_regret"] for row in treatment1000.values())
    control_catastrophes = sum(row["b_regret"] >= 3.0 for row in control1000.values())
    treatment_catastrophes = sum(row["b_regret"] >= 3.0 for row in treatment1000.values())

    winning = max((item for item in budget_results if item["threshold_improvement"]),
                  key=lambda item: max(item["top_agreement_improvement"],
                                       item["mean_regret_reduction"]), default=None)
    bootstrap = None
    if winning:
        budget = winning["budget"]
        control = row_map(rows, CONTROL, budget, "b")
        treatment = row_map(rows, selected, budget, "b")
        top_diffs = paired(control, treatment, "b_top_action")
        regret_reductions = [-value for value in paired(control, treatment, "b_regret")]
        regret_threshold = 0.15 * winning["control_mean_regret"]
        bootstrap = {
            "budget": budget,
            "top_improvement_probability_at_5pp": bootstrap_probability(
                top_diffs, lambda sample: statistics.fmean(sample) >= 0.05,
                20260829 + budget),
            "mean_regret_reduction_probability_at_15pct": bootstrap_probability(
                regret_reductions,
                lambda sample: statistics.fmean(sample) >= regret_threshold,
                20261829 + budget),
        }
        bootstrap["winning_probability"] = max(
            bootstrap["top_improvement_probability_at_5pp"],
            bootstrap["mean_regret_reduction_probability_at_15pct"])

    selected_rows = [row for row in rows if row["candidate"] == selected]
    control_rows = [row for row in rows if row["candidate"] == CONTROL]
    cpu_ratio = statistics.fmean(row["wall_micros"] for row in selected_rows) / statistics.fmean(
        row["wall_micros"] for row in control_rows)
    result = {
        "budgets": budget_results,
        "winning_budget": winning["budget"] if winning else None,
        "bootstrap": bootstrap,
        "at_1000": {
            "control_missed_best": control_missed,
            "treatment_missed_best": treatment_missed,
            "additional_missed_best": treatment_missed - control_missed,
            "control_mean_regret": control_mean,
            "treatment_mean_regret": treatment_mean,
            "mean_regret_increase": treatment_mean - control_mean,
            "control_ge_3": control_catastrophes,
            "treatment_ge_3": treatment_catastrophes,
            "new_ge_3": treatment_catastrophes > control_catastrophes,
        },
        "cpu_ratio_all_budgets": cpu_ratio,
    }
    result["passes"] = (
        sum(item["non_worse_both"] for item in budget_results) >= 2
        and any(item["threshold_improvement"] for item in budget_results)
        and bootstrap is not None and bootstrap["winning_probability"] >= 0.90
        and result["at_1000"]["additional_missed_best"] <= 1
        and result["at_1000"]["mean_regret_increase"] <= 0.10
        and not result["at_1000"]["new_ge_3"]
        and cpu_ratio <= 1.05
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--multi", required=True)
    parser.add_argument("--all", dest="all_rows", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--corpus")
    parser.add_argument("--labels")
    parser.add_argument("--executable")
    args = parser.parse_args()
    multi_header, multi_rows = read_replay(args.multi)
    all_header, all_rows = read_replay(args.all_rows)
    if len(multi_rows) != 63 * 4 * 4 or len(all_rows) != 93 * 4 * 4:
        raise RuntimeError(f"unexpected replay row counts: multi={len(multi_rows)} all={len(all_rows)}")
    selected, selection = selection_analysis(multi_rows)
    population_summary = evaluate_population(multi_rows, "a")
    secondary_summary = (evaluate_population(all_rows, "b")
                         if selected is not None else {
                             "not_run": "selection_rule_rejected_all_lower_root_candidates",
                         })
    gate = offline_gate(all_rows, selected) if selected is not None else {
        "passes": False,
        "not_run": "selection_rule_rejected_all_lower_root_candidates",
    }
    report = {
        "evidence_schema": "silver_root_exploration_evidence_v1",
        "status": "OFFLINE_GATE_PASS" if gate["passes"] else "ROOT_EXPLORATION_REDUCTION_REJECTED",
        "baseline_source_sha": "034830df6510f1ab37ad4f053c07333fca0970c7",
        "candidate_grid": [25.0, 18.5, 12.5, 9.9],
        "selection_rule": {
            "labels": "25k-A only",
            "budgets": [64, 128, 256],
            "reject_new_ge_3_at": [128, 256],
            "cpu_limit": 1.05,
            "selected_candidate": selected,
            "candidates": selection,
        },
        "configuration": {
            "root_control": "unset (ordinary deterministic c=25)",
            "internal_deterministic_c": 25.0,
            "chance_c": 25.0,
            "chance_widening": "unchanged",
            "adaptive_enabled": False,
            "reuse_cap_mode": "none",
            "action_masking_or_pruning": False,
        },
        "primary_multi_action_63": {
            "row_count": len(multi_rows),
            "population_summary": population_summary,
        },
        "secondary_all_93": {
            "row_count": len(all_rows),
            "population_summary": secondary_summary,
        },
        "independent_25k_B_gate": gate,
        "artifacts": {
            "multi_replay": str(Path(args.multi).resolve()),
            "multi_replay_sha256": sha256(args.multi),
            "all_replay": str(Path(args.all_rows).resolve()),
            "all_replay_sha256": sha256(args.all_rows),
        },
        "raw_headers": {"multi": multi_header, "all": all_header},
    }
    if args.corpus:
        report["artifacts"]["corpus"] = str(Path(args.corpus).resolve())
        report["artifacts"]["corpus_sha256"] = sha256(args.corpus)
    if args.labels:
        report["artifacts"]["relabel"] = str(Path(args.labels).resolve())
        report["artifacts"]["relabel_sha256"] = sha256(args.labels)
    if args.executable:
        report["artifacts"]["replay_executable"] = str(Path(args.executable).resolve())
        report["artifacts"]["replay_executable_sha256"] = sha256(args.executable)
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "selected": selected,
                      "offline_gate": gate["passes"],
                      "report": str(Path(args.report).resolve())}, sort_keys=True))


if __name__ == "__main__":
    main()
