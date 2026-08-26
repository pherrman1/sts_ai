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


def analyze(rows):
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
        "reference_stability": {
            "max_replicate_value_stddev_mean": mean("reference_stddev_max"),
            "max_replicate_value_stddev_max": max((x["reference_stddev_max"] for x in summaries), default=None),
        },
        "largest_disagreement_examples": examples[:10],
    }


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
        rows.append(row)
    result = analyze(rows)
    assert result["roots"] == 1
    assert result["top_action_agreement"]["silver_1k"] == 0.0
    assert result["top_action_agreement"]["silver_3.7k"] == 1.0
    assert result["mean_regret"]["silver_1k"] == 3.0
    assert result["pairwise_ordering_agreement"]["visits_3.7k"]["rate"] == 1.0
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
