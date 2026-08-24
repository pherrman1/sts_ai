#!/usr/bin/env python3
"""Reconstruct the Searcher3 always-Q Phase A root-race summary.

The 4000-simulation reference is arm-specific: each arm's shallow probes are
compared with that same arm's 4000-simulation probe.  The root-race CSV does
not contain a full visible-state hash, so metadata-matched roots are reported
as pairable, not as proven identical states.
"""

import argparse
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

STATE_FIELDS = ("seed", "floor", "encounter", "turn", "decision_index")
BUDGETS = ("250", "500", "1000")
REQUIRED = {
    "seed", "floor", "encounter", "turn", "decision_index", "action_bits",
    "chosen_250", "chosen_500", "chosen_1000", "chosen_4000", "deep_regret",
}


def read_root_csv(path):
    path = Path(path)
    try:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            missing = sorted(REQUIRED - fields)
            if missing:
                raise ValueError(f"{path}: missing columns: {', '.join(missing)}")
            grouped = defaultdict(list)
            for row in reader:
                key = tuple(row[field] for field in STATE_FIELDS)
                grouped[key].append(row)
    except FileNotFoundError as exc:
        raise ValueError(f"missing input: {path}") from exc
    if not grouped:
        raise ValueError(f"{path}: no root rows")
    return grouped


def chosen(group, budget):
    values = {row[f"chosen_{budget}"] for row in group}
    if len(values) != 1:
        raise ValueError(f"inconsistent chosen_{budget} within one root")
    return next(iter(values))


def regret_summary(grouped):
    disagreements = {}
    regrets = {}
    for budget in BUDGETS:
        selected_regrets = []
        count = 0
        for group in grouped.values():
            if chosen(group, budget) == chosen(group, "4000"):
                continue
            count += 1
            selected = next(
                (row for row in group if row["action_bits"] == chosen(group, budget)),
                None,
            )
            if selected is not None:
                value = float(selected["deep_regret"])
                if math.isfinite(value):
                    selected_regrets.append(value)
        disagreements[budget] = count
        regrets[budget] = selected_regrets
    return disagreements, regrets


def print_arm(label, grouped):
    seeds = {key[0] for key in grouped}
    print(f"{label}: rows={sum(map(len, grouped.values()))} states={len(grouped)} seeds={len(seeds)}")
    print("encounter_counts=" + ",".join(
        f"{enc}:{count}" for enc, count in sorted(Counter(key[2] for key in grouped).items(), key=lambda x: int(x[0]))
    ))
    disagreements, regrets = regret_summary(grouped)
    pooled = [value for values in regrets.values() for value in values]
    print(
        f"pooled_disagreement_regret n={len(pooled)}"
        f" mean={statistics.mean(pooled) if pooled else 0.0:.6f}"
        f" median={statistics.median(pooled) if pooled else 0.0:.6f}"
    )
    for budget in BUDGETS:
        agree = len(grouped) - disagreements[budget]
        values = regrets[budget]
        mean = statistics.mean(values) if values else 0.0
        median = statistics.median(values) if values else 0.0
        print(
            f"budget={budget} own_arm_4000_agreement={agree}/{len(grouped)}"
            f" ({agree / len(grouped):.4f}) disagreements={disagreements[budget]}"
            f" regret_n={len(values)} regret_mean={mean:.6f} regret_median={median:.6f}"
        )


def compare_metadata(control, treatment):
    common = set(control) & set(treatment)
    print(
        f"metadata_pairing: control_states={len(control)} treatment_states={len(treatment)}"
        f" common_metadata_states={len(common)} exact_state_equality=UNVERIFIED"
    )
    for budget in BUDGETS + ("4000",):
        differences = sum(
            chosen(control[key], budget) != chosen(treatment[key], budget)
            for key in common
        )
        print(f"paired_chosen_action_differences budget={budget} count={differences}/{len(common)}")


def run(control_path, treatment_path):
    control = read_root_csv(control_path)
    treatment = read_root_csv(treatment_path)
    print("reference_scope=ARM_SPECIFIC_4000_SIMULATION")
    print_arm("control", control)
    print_arm("always_q", treatment)
    compare_metadata(control, treatment)


def self_test():
    def row(action, chosen):
        values = {field: "1" for field in STATE_FIELDS}
        values.update({
            "action_bits": str(action),
            "chosen_250": str(chosen), "chosen_500": str(chosen),
            "chosen_1000": str(chosen), "chosen_4000": "10",
            "deep_regret": "0.5",
        })
        return values

    group = [row(10, 10), row(20, 10)]
    grouped = {tuple("1" for _ in STATE_FIELDS): group}
    disagreements, regrets = regret_summary(grouped)
    assert disagreements == {"250": 0, "500": 0, "1000": 0}
    assert all(not values for values in regrets.values())
    assert chosen(group, "4000") == "10"
    print("self_test=PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("control", nargs="?")
    parser.add_argument("treatment", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.control and args.treatment:
            run(args.control, args.treatment)
        else:
            parser.error("provide control and treatment CSVs, or use --self-test")
    except (ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
