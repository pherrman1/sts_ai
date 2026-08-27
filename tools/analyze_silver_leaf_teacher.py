#!/usr/bin/env python3
"""Analyze matched-budget Silver teacher convergence against independent 25k-B."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

BUDGETS = (1000, 3700, 10000, 25000)


def mean(values):
    return statistics.fmean(values) if values else None


def median(values):
    return statistics.median(values) if values else None


def quantile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    pos = 0
    while pos < len(order):
        end = pos + 1
        while end < len(order) and values[order[end]] == values[order[pos]]:
            end += 1
        rank = (pos + end - 1) / 2
        for idx in order[pos:end]:
            result[idx] = rank
        pos = end
    return result


def pearson(xs, ys):
    if len(xs) < 2:
        return None
    mx, my = mean(xs), mean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denom = math.sqrt(sum(x*x for x in dx) * sum(y*y for y in dy))
    return sum(x*y for x, y in zip(dx, dy)) / denom if denom else None


def action_map(row):
    return {a["action_fingerprint"]: a for a in row["root_actions"] if a["leaf_root_q_valid"]}


def compare_rows(candidate, reference):
    ca, ra = action_map(candidate), action_map(reference)
    common = sorted(ca.keys() & ra.keys())
    pair_total = pair_agree = 0
    for i, left in enumerate(common):
        for right in common[i + 1:]:
            cdelta = ca[left]["original_root_corrected_q"] - ca[right]["original_root_corrected_q"]
            rdelta = ra[left]["original_root_corrected_q"] - ra[right]["original_root_corrected_q"]
            pair_total += 1
            pair_agree += (cdelta > 0) == (rdelta > 0) and (cdelta < 0) == (rdelta < 0)
    selected = candidate["selected_action_fingerprint"]
    ref_best = reference["selected_action_fingerprint"]
    ref_best_q = ra.get(ref_best, {}).get("original_root_corrected_q")
    selected_ref_q = ra.get(selected, {}).get("original_root_corrected_q")
    regret = None if ref_best_q is None or selected_ref_q is None else max(0.0, ref_best_q - selected_ref_q)
    q_error = None
    if selected in ca and selected in ra:
        q_error = abs(ca[selected]["original_root_corrected_q"] - ra[selected]["original_root_corrected_q"])
    return {
        "action_eligible": not candidate.get("terminal_snapshot", False)
            and not reference.get("terminal_snapshot", False),
        "top_agree": selected == ref_best,
        "pair_agree": pair_agree,
        "pair_total": pair_total,
        "regret": regret,
        "q_abs_error": q_error,
    }


def aggregate_state(pairs):
    details = [compare_rows(c, r) for c, r in pairs]
    regrets = [d["regret"] for d in details if d["regret"] is not None]
    errors = [d["q_abs_error"] for d in details if d["q_abs_error"] is not None]
    xs = [c["original_root_corrected_teacher_value"] for c, _ in pairs]
    ys = [r["original_root_corrected_teacher_value"] for _, r in pairs]
    differences = [x-y for x, y in zip(xs, ys)]
    top_agreement = mean([d["top_agree"] for d in details if d["action_eligible"]])
    return {
        "leaves": len(pairs),
        "action_eligible_leaves": sum(d["action_eligible"] for d in details),
        "top_action_agreement": top_agreement,
        "top_action_disagreement": None if top_agreement is None else 1.0 - top_agreement,
        "legal_action_pairwise_agreement": (
            sum(d["pair_agree"] for d in details) / sum(d["pair_total"] for d in details)
            if sum(d["pair_total"] for d in details) else None),
        "mean_regret": mean(regrets), "median_regret": median(regrets),
        "mean_q_abs_error": mean(errors), "median_q_abs_error": median(errors),
        "pearson": pearson(xs, ys), "spearman": pearson(ranks(xs), ranks(ys)),
        "value_difference": {
            "mean": mean(differences), "median": median(differences),
            "p05": quantile(differences, 0.05), "p25": quantile(differences, 0.25),
            "p75": quantile(differences, 0.75), "p95": quantile(differences, 0.95),
            "mean_abs": mean([abs(value) for value in differences]),
        },
    }


def sibling_metrics(pairs):
    by_group = defaultdict(list)
    for candidate, reference in pairs:
        by_group[candidate["group_id"]].append((candidate, reference))
    concordant = total = top_agree = groups = 0
    regrets, centered_errors = [], []
    for rows in by_group.values():
        if len(rows) < 2:
            continue
        groups += 1
        candidate_values = [c["original_root_corrected_teacher_value"] for c, _ in rows]
        reference_values = [r["original_root_corrected_teacher_value"] for _, r in rows]
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                cd = candidate_values[i] - candidate_values[j]
                rd = reference_values[i] - reference_values[j]
                if cd == 0 or rd == 0:
                    continue
                total += 1
                concordant += (cd > 0) == (rd > 0)
        ci = max(range(len(rows)), key=candidate_values.__getitem__)
        ri = max(range(len(rows)), key=reference_values.__getitem__)
        top_agree += ci == ri
        regrets.append(reference_values[ri] - reference_values[ci])
        cm, rm = mean(candidate_values), mean(reference_values)
        centered_errors.extend((c-cm) - (r-rm) for c, r in zip(candidate_values, reference_values))
    return {
        "groups_with_two_plus_leaves": groups,
        "strict_pairwise_concordance": concordant / total if total else None,
        "top_leaf_agreement": top_agree / groups if groups else None,
        "mean_regret": mean(regrets), "median_regret": median(regrets),
        "centered_rmse": math.sqrt(mean([e*e for e in centered_errors])) if centered_errors else None,
        "centered_mae": mean([abs(e) for e in centered_errors]),
    }


def subgroup_label(row, dimension):
    if dimension == "act":
        return str(row["act"])
    if dimension == "hp_band":
        value = row["hp_fraction"]
        return "low" if value < 0.34 else "mid" if value < 0.67 else "high"
    if dimension == "rollout_length_band":
        value = row["rollout_turn_delta"]
        return "short" if value <= 2 else "medium" if value <= 5 else "long"
    return row["encounter_category"]


def subgroup_report(pairs):
    report = {}
    for dimension in ("act", "hp_band", "rollout_length_band", "encounter_category"):
        buckets = defaultdict(list)
        for pair in pairs:
            buckets[subgroup_label(pair[0], dimension)].append(pair)
        report[dimension] = {label: aggregate_state(rows) for label, rows in sorted(buckets.items())}
    return report


def interval(values):
    return {"p025": quantile(values, 0.025), "p975": quantile(values, 0.975)}


def bootstrap_uncertainty(pair_sets, replicates, seed):
    """Paired group bootstrap against the independent 25k-B ceiling.

    Whole sibling groups are sampled with replacement. Candidate and 25k-A
    ceiling metrics use the same group draw, preserving their paired
    dependence on the common independent 25k-B reference.
    """
    by_budget = {}
    for budget, pairs in pair_sets.items():
        grouped = defaultdict(list)
        for pair in pairs:
            grouped[pair[0]["group_id"]].append(pair)
        by_budget[budget] = grouped
    common_groups = sorted(set(by_budget[25000]).intersection(
        *(set(by_budget[budget]) for budget in (1000, 3700, 10000))))
    output = {"method": "paired sibling-group bootstrap with replacement",
              "confidence_level": 0.95, "replicates": replicates, "seed": seed,
              "anchor_groups": len(common_groups), "candidates": {}}
    if not common_groups or replicates <= 0:
        return output

    rng = random.Random(seed)
    samples = {budget: {"top": [], "pair": [], "sibling": [], "regret": [],
                        "regret_ratio": [], "joint_pass": []}
               for budget in (1000, 3700, 10000)}
    for _ in range(replicates):
        drawn = [rng.choice(common_groups) for _ in common_groups]
        resampled = {}
        for budget in BUDGETS:
            pairs = []
            for occurrence, group_id in enumerate(drawn):
                for candidate, reference in by_budget[budget][group_id]:
                    candidate_copy = dict(candidate)
                    candidate_copy["group_id"] = f"{group_id}#bootstrap-{occurrence}"
                    pairs.append((candidate_copy, reference))
            resampled[budget] = (aggregate_state(pairs), sibling_metrics(pairs))
        ceiling, sibling_ceiling = resampled[25000]
        for budget in (1000, 3700, 10000):
            metric, sibling = resampled[budget]
            top = metric["top_action_agreement"] - ceiling["top_action_agreement"]
            pair = (metric["legal_action_pairwise_agreement"]
                    - ceiling["legal_action_pairwise_agreement"])
            sibling_margin = (sibling["strict_pairwise_concordance"]
                              - sibling_ceiling["strict_pairwise_concordance"])
            regret_floor = ceiling["mean_regret"] or 0.0
            regret = metric["mean_regret"] - regret_floor
            regret_tolerance = max(0.25, abs(regret_floor))
            values = samples[budget]
            values["top"].append(top)
            values["pair"].append(pair)
            values["sibling"].append(sibling_margin)
            values["regret"].append(regret)
            if abs(regret_floor) >= 1e-9:
                values["regret_ratio"].append(metric["mean_regret"] / regret_floor)
            values["joint_pass"].append(
                top >= -0.02 and pair >= -0.02 and sibling_margin >= -0.02
                and regret <= regret_tolerance)

    for budget, values in samples.items():
        output["candidates"][str(budget)] = {
            "top_action_agreement_margin_vs_25k_ceiling": interval(values["top"]),
            "legal_action_pairwise_margin_vs_25k_ceiling": interval(values["pair"]),
            "sibling_concordance_margin_vs_25k_ceiling": interval(values["sibling"]),
            "mean_regret_excess_vs_25k_noise": interval(values["regret"]),
            "mean_regret_ratio_to_25k_noise": interval(values["regret_ratio"]),
            "global_bar_pass_probability": mean(values["joint_pass"]),
            "note": "Global bootstrap excludes the separately reported manual subgroup-pathology review.",
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("relabels", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260827)
    args = parser.parse_args()
    if args.bootstrap_replicates < 0:
        raise SystemExit("--bootstrap-replicates must be nonnegative")
    rows = {}
    with args.relabels.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1":
                raise SystemExit(f"{args.relabels}:{number}: incompatible relabel schema")
            key = (row["state_kind"], row["leaf_snapshot_id"], row["budget"], row["replicate"])
            if key in rows:
                raise SystemExit(f"{args.relabels}:{number}: duplicate relabel identity {key}")
            rows[key] = row

    comparisons, siblings = {}, {}
    pair_sets = {}
    for budget in BUDGETS:
        pairs = []
        for (kind, leaf, b, replicate), candidate in rows.items():
            if kind != "leaf" or b != budget or replicate != "A":
                continue
            reference = rows.get(("leaf", leaf, 25000, "B"))
            if reference:
                pairs.append((candidate, reference))
        pair_sets[budget] = pairs
        comparisons[str(budget)] = aggregate_state(pairs)
        siblings[str(budget)] = sibling_metrics(pairs)

    ceiling = comparisons["25000"]
    sibling_ceiling = siblings["25000"]
    subgroups = {str(budget): subgroup_report(pair_sets[budget]) for budget in BUDGETS}
    decisions = {}
    chosen = None
    for budget in (1000, 3700, 10000):
        metric, sibling = comparisons[str(budget)], siblings[str(budget)]
        regret_floor = ceiling["mean_regret"] or 0.0
        regret_ratio = None if regret_floor < 1e-9 else metric["mean_regret"] / regret_floor
        pathologies = []
        for dimension, buckets in subgroups[str(budget)].items():
            for label, candidate_subgroup in buckets.items():
                ceiling_subgroup = subgroups["25000"].get(dimension, {}).get(label)
                if not ceiling_subgroup or candidate_subgroup["leaves"] < 5:
                    continue
                top_bad = (candidate_subgroup["top_action_agreement"] is not None
                    and ceiling_subgroup["top_action_agreement"] is not None
                    and candidate_subgroup["top_action_agreement"] + 0.10
                        < ceiling_subgroup["top_action_agreement"])
                pair_bad = (candidate_subgroup["legal_action_pairwise_agreement"] is not None
                    and ceiling_subgroup["legal_action_pairwise_agreement"] is not None
                    and candidate_subgroup["legal_action_pairwise_agreement"] + 0.10
                        < ceiling_subgroup["legal_action_pairwise_agreement"])
                if top_bad or pair_bad:
                    pathologies.append(f"{dimension}={label}")
        passes = bool(metric["leaves"] and
            metric["top_action_agreement"] is not None and
            ceiling["top_action_agreement"] is not None and
            metric["legal_action_pairwise_agreement"] is not None and
            ceiling["legal_action_pairwise_agreement"] is not None and
            metric["top_action_agreement"] + 0.02 >= ceiling["top_action_agreement"] and
            metric["legal_action_pairwise_agreement"] + 0.02 >= ceiling["legal_action_pairwise_agreement"] and
            sibling["strict_pairwise_concordance"] is not None and
            sibling_ceiling["strict_pairwise_concordance"] is not None and
            sibling["strict_pairwise_concordance"] + 0.02 >= sibling_ceiling["strict_pairwise_concordance"] and
            metric["mean_regret"] <= regret_floor + max(0.25, abs(regret_floor)) and
            not pathologies)
        decisions[str(budget)] = {"passes_global_bar": passes,
            "mean_regret_ratio_to_25k_noise": regret_ratio,
            "clear_subgroup_pathologies": pathologies,
            "manual_subgroup_review_required": True}
        if passes and chosen is None:
            chosen = {1000: "TEACHER_1K", 3700: "TEACHER_3P7K", 10000: "TEACHER_10K"}[budget]
    verdict = chosen or "TEACHER_BUDGET_UNRESOLVED_OR_25K_REQUIRED"
    bootstrap = bootstrap_uncertainty(
        pair_sets, args.bootstrap_replicates, args.bootstrap_seed)
    report = {"analyzer_schema": "silver_leaf_teacher_analysis_v1",
              "independent_reference": "25k replicate B", "state_value_and_action": comparisons,
              "sibling_value": siblings, "replicate_ceiling_25kA_vs_25kB": {
                  "state": ceiling, "sibling": sibling_ceiling},
              "subgroups": subgroups,
              "candidate_decisions": decisions,
              "group_bootstrap_uncertainty": bootstrap,
              "verdict": verdict, "point_estimate_verdict": verdict,
              "warning": "Subgroup reversal/pathology must be reviewed before accepting a passing global verdict."}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
