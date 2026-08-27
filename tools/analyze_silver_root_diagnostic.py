#!/usr/bin/env python3
"""Analyze the bounded Silver root-action reference diagnostic.

The CSV is one row per (captured root, legal root action).  Reference values
are fresh forced-action continuation estimates; current Silver quantities are
the production 1k/3.7k root visits and child-Q values.  This tool deliberately
does not call the game or tune an intervention.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def f(row, key):
    return float(row[key])


def i(row, key):
    return int(row[key])


def cmp(a, b, eps=1e-9):
    if a > b + eps:
        return 1
    if b > a + eps:
        return -1
    return 0


def load(path):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("diagnostic CSV has no action rows")
    required = {
        "run_seed", "floor", "encounter", "combat_decision_ordinal",
        "action_fingerprint", "chosen_1k", "chosen_37k",
        "chosen_1k_visits", "chosen_37k_visits", "reference_value",
        "reference_value_stddev", "action_type", "stochastic", "cur_hp",
        "max_hp", "potion_count", "reference_rollout_calls",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))
    return rows


def groups(rows):
    out = defaultdict(list)
    for row in rows:
        key = (row["run_seed"], row["floor"], row["encounter"],
               row["combat_decision_ordinal"])
        out[key].append(row)
    return out


def ordering(rows, score_key):
    good = agree = 0
    for pos, lhs in enumerate(rows):
        for rhs in rows[pos + 1:]:
            ref_sign = cmp(f(lhs, "reference_value"), f(rhs, "reference_value"))
            cur_sign = cmp(f(lhs, score_key), f(rhs, score_key))
            if ref_sign == 0:
                continue
            good += 1
            if cur_sign == ref_sign:
                agree += 1
    return {"agreement": agree / good if good else None,
            "agree_pairs": agree, "comparable_pairs": good}


def q_ordering(rows, key):
    filtered = [r for r in rows if r[key] != "NA"]
    return ordering(filtered, key)


def root_summary(root):
    by_action = {r["action_fingerprint"]: r for r in root}
    ref_best_value = max(f(r, "reference_value") for r in root)
    ref_best = {r["action_fingerprint"] for r in root
                if abs(f(r, "reference_value") - ref_best_value) <= 1e-9}
    chosen_1k = root[0]["chosen_1k"]
    chosen_37k = root[0]["chosen_37k"]
    def regret(chosen):
        return (ref_best_value - f(by_action[chosen], "reference_value")
                if chosen in by_action else None)
    ref_values = sorted((f(r, "reference_value") for r in root), reverse=True)
    margin = ref_values[0] - ref_values[1] if len(ref_values) > 1 else None
    return {
        "rows": len(root),
        "ref_best": next(iter(ref_best)),
        "ref_best_ties": len(ref_best),
        "chosen_1k": chosen_1k,
        "chosen_37k": chosen_37k,
        "top_agree_1k": chosen_1k in ref_best,
        "top_agree_37k": chosen_37k in ref_best,
        "regret_1k": regret(chosen_1k),
        "regret_37k": regret(chosen_37k),
        "reference_margin": margin,
        "reference_stddev_max": max(f(r, "reference_value_stddev") for r in root),
        "encounter": root[0]["encounter"],
        "action_type_1k": by_action.get(chosen_1k, root[0])["action_type"],
        "action_type_37k": by_action.get(chosen_37k, root[0])["action_type"],
        "stochastic_1k": by_action.get(chosen_1k, root[0])["stochastic"],
        "stochastic_37k": by_action.get(chosen_37k, root[0])["stochastic"],
        "hp_fraction": f(root[0], "cur_hp") / max(1.0, f(root[0], "max_hp")),
        "potion": f(root[0], "potion_count") > 0,
        "reroot": root[0].get("active_reroot_exact", "NA"),
        "fallback": root[0].get("active_fallback_reason", "NA"),
    }


def breakdown(summaries, field):
    buckets = defaultdict(list)
    for item in summaries:
        value = item[field]
        if field == "hp_fraction":
            value = "low" if value < .34 else "mid" if value < .67 else "high"
        buckets[str(value)].append(item)
    out = {}
    for key, items in sorted(buckets.items()):
        regrets = [x["regret_1k"] for x in items if x["regret_1k"] is not None]
        out[key] = {
            "roots": len(items),
            "disagreements_1k": sum(not x["top_agree_1k"] for x in items),
            "disagreement_rate_1k": sum(not x["top_agree_1k"] for x in items) / len(items),
            "mean_regret_1k": statistics.mean(regrets) if regrets else None,
        }
    return out


def margin_breakdown(summaries):
    buckets = {
        "<0.1": [x for x in summaries if x["reference_margin"] is not None
                 and x["reference_margin"] < 0.1],
        "0.1-0.5": [x for x in summaries if x["reference_margin"] is not None
                     and 0.1 <= x["reference_margin"] < 0.5],
        "0.5-1.0": [x for x in summaries if x["reference_margin"] is not None
                    and 0.5 <= x["reference_margin"] < 1.0],
        ">=1.0": [x for x in summaries if x["reference_margin"] is not None
                  and x["reference_margin"] >= 1.0],
    }
    out = {}
    for key, items in buckets.items():
        def avg(field):
            values = [x[field] for x in items if x[field] is not None]
            return statistics.mean(values) if values else None
        out[key] = {
            "roots": len(items),
            "mean_regret_1k": avg("regret_1k"),
            "mean_regret_3.7k": avg("regret_37k"),
            "disagreement_rate_1k": (
                sum(not x["top_agree_1k"] for x in items) / len(items)
                if items else None),
            "disagreement_rate_3.7k": (
                sum(not x["top_agree_37k"] for x in items) / len(items)
                if items else None),
        }
    return out


def _analyze_rows(rows):
    root_groups = groups(rows)
    summaries = []
    pair_visits_1k = {"agree_pairs": 0, "comparable_pairs": 0}
    pair_visits_37k = {"agree_pairs": 0, "comparable_pairs": 0}
    pair_q_1k = {"agree_pairs": 0, "comparable_pairs": 0}
    pair_q_37k = {"agree_pairs": 0, "comparable_pairs": 0}
    for root in root_groups.values():
        summaries.append(root_summary(root))
        for total, current in ((pair_visits_1k, "chosen_1k_visits"),
                               (pair_visits_37k, "chosen_37k_visits")):
            result = ordering(root, current)
            for key in total:
                total[key] += result[key] or 0
        for total, current in ((pair_q_1k, "chosen_1k_q"),
                               (pair_q_37k, "chosen_37k_q")):
            result = q_ordering(root, current)
            for key in total:
                total[key] += result[key] or 0

    def mean(key):
        values = [x[key] for x in summaries if x[key] is not None]
        return statistics.mean(values) if values else None
    def median(key):
        values = [x[key] for x in summaries if x[key] is not None]
        return statistics.median(values) if values else None
    def rate(key):
        return sum(bool(x[key]) for x in summaries) / len(summaries) if summaries else None
    def pair_rate(total):
        return (total["agree_pairs"] / total["comparable_pairs"]
                if total["comparable_pairs"] else None)

    examples = []
    for key, root in root_groups.items():
        by_action = {r["action_fingerprint"]: r for r in root}
        chosen = root[0]["chosen_1k"]
        best = max(root, key=lambda r: f(r, "reference_value"))
        chosen_row = by_action.get(chosen)
        if chosen_row is not None and best["action_fingerprint"] != chosen:
            examples.append({
                "root": {"seed": key[0], "floor": key[1], "encounter": key[2], "decision": key[3]},
                "chosen_1k": {k: chosen_row.get(k) for k in
                              ("action_fingerprint", "reference_value", "reference_value_stddev",
                               "reference_win_bonus", "reference_hp", "reference_potion",
                               "reference_turn_penalty", "reference_monster_damage", "reference_alive",
                               "reference_energy_waste", "reference_draw", "reference_survival")},
                "reference_best": {k: best.get(k) for k in
                                   ("action_fingerprint", "reference_value", "reference_value_stddev",
                                    "reference_win_bonus", "reference_hp", "reference_potion",
                                    "reference_turn_penalty", "reference_monster_damage", "reference_alive",
                                    "reference_energy_waste", "reference_draw", "reference_survival")},
            })
    examples.sort(key=lambda x: float(x["reference_best"]["reference_value"])
                  - float(x["chosen_1k"]["reference_value"]), reverse=True)

    def rollout_totals(prefix, calls_key=None, wins_key=None, losses_key=None,
                       actions_key=None, turns_key=None, utility_key=None,
                       stored_means=False, source_rows=None):
        fields = ("rollout_calls", "terminal_wins", "terminal_losses",
                  "rollout_actions", "rollout_turns", "utility_sum")
        keys = {
            "rollout_calls": calls_key or f"{prefix}_rollout_calls",
            "terminal_wins": wins_key or f"{prefix}_terminal_wins",
            "terminal_losses": losses_key or f"{prefix}_terminal_losses",
            "rollout_actions": actions_key or f"{prefix}_rollout_actions",
            "rollout_turns": turns_key or f"{prefix}_rollout_turns",
            "utility_sum": utility_key or f"{prefix}_utility_sum",
        }
        totals = {field: 0 for field in fields}
        rows_to_sum = (source_rows if source_rows is not None
                       else [root[0] for root in root_groups.values()])
        for row in rows_to_sum:
            calls = float(row[keys["rollout_calls"]])
            for field in fields:
                value = float(row[keys[field]])
                totals[field] += value * calls if stored_means and field in (
                    "rollout_actions", "rollout_turns", "utility_sum") else value
        calls = totals["rollout_calls"]
        return {
            "calls": int(totals["rollout_calls"]),
            "terminal_wins": int(totals["terminal_wins"]),
            "terminal_losses": int(totals["terminal_losses"]),
            "mean_actions": totals["rollout_actions"] / calls if calls else None,
            "mean_turns": totals["rollout_turns"] / calls if calls else None,
            "mean_utility": totals["utility_sum"] / calls if calls else None,
        }

    return {
        "roots": len(summaries),
        "action_rows": len(rows),
        "seeds": len({r["run_seed"] for r in rows}),
        "top_action_agreement": {
            "silver_1k": rate("top_agree_1k"),
            "silver_3.7k": rate("top_agree_37k"),
        },
        "mean_regret": {"silver_1k": mean("regret_1k"), "silver_3.7k": mean("regret_37k")},
        "median_regret": {"silver_1k": median("regret_1k"), "silver_3.7k": median("regret_37k")},
        "reference_margin": {"mean": mean("reference_margin"), "median": median("reference_margin")},
        "pairwise_ordering_agreement": {
            "visits_1k": {**pair_visits_1k, "rate": pair_rate(pair_visits_1k)},
            "visits_3.7k": {**pair_visits_37k, "rate": pair_rate(pair_visits_37k)},
            "q_1k": {**pair_q_1k, "rate": pair_rate(pair_q_1k)},
            "q_3.7k": {**pair_q_37k, "rate": pair_rate(pair_q_37k)},
        },
        "budget_change": {
            "chosen_disagreement_rate_1k_vs_3.7k": sum(
                x["chosen_1k"] != x["chosen_37k"] for x in summaries) / len(summaries),
            "mean_regret_delta_3.7k_minus_1k": mean("regret_37k") - mean("regret_1k"),
        },
        "breakdowns": {
            "encounter": breakdown(summaries, "encounter"),
            "action_type_1k": breakdown(summaries, "action_type_1k"),
            "hp_regime": breakdown(summaries, "hp_fraction"),
            "potion_available": breakdown(summaries, "potion"),
            "stochastic_1k": breakdown(summaries, "stochastic_1k"),
            "reroot": breakdown(summaries, "reroot"),
            "fallback": breakdown(summaries, "fallback"),
        },
        "regret_by_reference_margin": margin_breakdown(summaries),
        "rollout_aggregates": {
            "reference": {
                **rollout_totals(
                    "reference", calls_key="reference_rollout_calls",
                    wins_key="reference_terminal_wins",
                    losses_key="reference_terminal_losses",
                    actions_key="reference_rollout_actions",
                    turns_key="reference_rollout_turns",
                    utility_key="reference_utility_sum", stored_means=True,
                    source_rows=rows),
            },
            "current_1k": rollout_totals("current_1k"),
            "current_3.7k": rollout_totals("current_37k"),
        },
        "reference_stability": {
            "max_replicate_value_stddev_mean": mean("reference_stddev_max"),
            "max_replicate_value_stddev_max": max((x["reference_stddev_max"] for x in summaries), default=None),
        },
        "largest_disagreement_examples": examples[:10],
    }


def analyze(rows):
    """Return deterministic-reference headlines plus mixed-action descriptives.

    A stochastic forced root action is sampled once before its continuation
    search, so its reference value is not a 5k-simulation estimate of the
    root action's chance expectation.  The full mixed-action analysis remains
    available under ``all_roots_descriptive``.  Headline action-quality
    metrics use only rows marked deterministic; a selected stochastic action
    also excludes that root from the corresponding budget's top-action and
    regret denominator.
    """
    all_results = _analyze_rows(rows)
    root_groups = groups(rows)

    def selected_is_deterministic(root, chosen_key):
        chosen = root[0][chosen_key]
        return any(r["action_fingerprint"] == chosen and r["stochastic"] == "0"
                   for r in root)

    def deterministic_rows(chosen_key):
        selected = []
        for root in root_groups.values():
            if selected_is_deterministic(root, chosen_key):
                selected.extend(r for r in root if r["stochastic"] == "0")
        return selected

    def all_deterministic_rows():
        return [r for root in root_groups.values() for r in root
                if r["stochastic"] == "0"]

    one_k_rows = deterministic_rows("chosen_1k")
    three_seven_k_rows = deterministic_rows("chosen_37k")
    joint_rows = [r for root in root_groups.values()
                  if selected_is_deterministic(root, "chosen_1k")
                  and selected_is_deterministic(root, "chosen_37k")
                  for r in root if r["stochastic"] == "0"]
    deterministic_action_rows = all_deterministic_rows()

    one_k = _analyze_rows(one_k_rows) if one_k_rows else None
    three_seven_k = (_analyze_rows(three_seven_k_rows)
                     if three_seven_k_rows else None)
    joint = _analyze_rows(joint_rows) if joint_rows else None
    deterministic_actions = (_analyze_rows(deterministic_action_rows)
                             if deterministic_action_rows else None)

    def metric(scope, name, key):
        return scope[name][key] if scope is not None else None

    headline = {
        "roots": len(root_groups),
        "deterministic_action_rows": len(deterministic_action_rows),
        "roots_with_deterministic_candidates": len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in deterministic_action_rows}),
        "roots_for_1k_top_and_regret": len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in one_k_rows}),
        "roots_for_3.7k_top_and_regret": len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in three_seven_k_rows}),
        "roots_for_joint_budget_comparison": len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in joint_rows}),
        "excluded_stochastic_candidate_rows": len(rows) - len(deterministic_action_rows),
        "excluded_stochastic_selected_roots_1k": len(root_groups) - len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in one_k_rows}),
        "excluded_stochastic_selected_roots_3.7k": len(root_groups) - len({
            (r["run_seed"], r["floor"], r["encounter"],
             r["combat_decision_ordinal"])
            for r in three_seven_k_rows}),
        "top_action_agreement": {
            "silver_1k": metric(one_k, "top_action_agreement", "silver_1k"),
            "silver_3.7k": metric(three_seven_k, "top_action_agreement", "silver_3.7k"),
        },
        "mean_regret": {
            "silver_1k": metric(one_k, "mean_regret", "silver_1k"),
            "silver_3.7k": metric(three_seven_k, "mean_regret", "silver_3.7k"),
        },
        "median_regret": {
            "silver_1k": metric(one_k, "median_regret", "silver_1k"),
            "silver_3.7k": metric(three_seven_k, "median_regret", "silver_3.7k"),
        },
        "pairwise_ordering_agreement": (
            deterministic_actions["pairwise_ordering_agreement"]
            if deterministic_actions is not None else None),
        "reference_margin": {
            "silver_1k_mean": metric(one_k, "reference_margin", "mean"),
            "silver_1k_median": metric(one_k, "reference_margin", "median"),
            "silver_3.7k_mean": metric(three_seven_k, "reference_margin", "mean"),
            "silver_3.7k_median": metric(three_seven_k, "reference_margin", "median"),
        },
        "budget_change": (
            joint["budget_change"] if joint is not None else None),
        "regret_by_reference_margin": (
            joint["regret_by_reference_margin"] if joint is not None else None),
        "breakdowns": joint["breakdowns"] if joint is not None else None,
        "reference_stability": {
            "silver_1k": one_k["reference_stability"] if one_k is not None else None,
            "silver_3.7k": (three_seven_k["reference_stability"]
                             if three_seven_k is not None else None),
        },
    }
    all_results["all_roots_descriptive"] = all_results.copy()
    all_results.update(headline)
    all_results["reference_scope"] = headline
    return all_results


def self_test():
    base = {
        "run_seed": "1", "floor": "10", "encounter": "2", "combat_decision_ordinal": "3",
        "chosen_1k": "a", "chosen_37k": "b", "chosen_1k_visits": "8", "chosen_37k_visits": "12",
        "chosen_1k_q": "1", "chosen_37k_q": "3", "cur_hp": "20", "max_hp": "80",
        "potion_count": "1", "active_reroot_exact": "0", "active_fallback_reason": "none",
        "reference_rollout_calls": "10", "reference_value_stddev": "0.2",
    }
    rows = []
    for fp, value, visits1, visits37, typ in (("a", "1", "8", "5", "0"),
                                               ("b", "4", "5", "13", "4"),
                                               ("c", "2", "2", "8", "1")):
        row = dict(base)
        row.update({"action_fingerprint": fp, "reference_value": value,
                    "reference_win_bonus": "0", "reference_hp": value,
                    "reference_potion": "0", "reference_turn_penalty": "0",
                    "reference_monster_damage": "0", "reference_alive": "0",
                    "reference_energy_waste": "0", "reference_draw": "0",
                    "reference_survival": "0", "reference_rollout_win_rate": "0",
                    "reference_rollout_actions": "1", "reference_rollout_turns": "1",
                    "reference_terminal_wins": "0", "reference_terminal_losses": "1",
                    "reference_utility_sum": value, "action_type": typ, "stochastic": "0",
                    "chosen_1k_visits": visits1, "chosen_37k_visits": visits37,
                    "chosen_1k_q": "1", "chosen_37k_q": "2"})
        row.update({"current_1k_rollout_calls": "10", "current_1k_terminal_wins": "10",
                    "current_1k_terminal_losses": "0", "current_1k_rollout_actions": "20",
                    "current_1k_rollout_turns": "5", "current_1k_utility_sum": "30",
                    "current_37k_rollout_calls": "10", "current_37k_terminal_wins": "10",
                    "current_37k_terminal_losses": "0", "current_37k_rollout_actions": "20",
                    "current_37k_rollout_turns": "5", "current_37k_utility_sum": "30"})
        rows.append(row)
    result = analyze(rows)
    assert result["roots"] == 1
    assert result["top_action_agreement"]["silver_1k"] == 0.0
    assert result["top_action_agreement"]["silver_3.7k"] == 1.0
    assert result["mean_regret"]["silver_1k"] == 3.0
    assert result["pairwise_ordering_agreement"]["visits_3.7k"]["rate"] == 1.0
    assert result["reference_scope"]["deterministic_action_rows"] == 3
    assert result["reference_scope"]["roots_for_joint_budget_comparison"] == 1
    print("analyze_silver_root_diagnostic self-test PASS")


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
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.json_path:
        Path(args.json_path).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
