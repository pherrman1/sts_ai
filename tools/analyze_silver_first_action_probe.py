#!/usr/bin/env python3
"""Analyze the diagnostic Teacher-first-action counterfactual."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def action_kind(description: str) -> str:
    text = description.lower()
    if "end turn" in text:
        return "end_turn"
    if "drink potion" in text or "discard potion" in text:
        return "potion"
    if "use card" in text:
        return "card"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    probe = json.loads(args.probe.read_text())
    leaves = probe["leaves"]
    accepted = [row for row in leaves if row.get("accepted")]
    stable = [row for row in accepted if row["teacher_a_b_action_agree"]]
    unstable = [row for row in accepted if not row["teacher_a_b_action_agree"]]
    stable_groups = {row["group_id"] for row in stable}
    baseline_abs = sum(abs(row["baseline_residual_vs_teacher_a"]) for row in stable)
    treatment_abs = sum(abs(row["treatment_residual_vs_teacher_a"]) for row in stable)
    fraction_removed = 1.0 - treatment_abs / baseline_abs if baseline_abs else None
    if len(stable_groups) >= 2 and fraction_removed is not None and fraction_removed >= 0.50:
        classification = "FIRST_ACTION_BIAS_MATERIAL"
    elif fraction_removed is not None and fraction_removed < 0.20:
        classification = "FIRST_ACTION_BIAS_NOT_PRIMARY"
    else:
        classification = "INCONCLUSIVE"

    mismatch_patterns = Counter()
    for row in stable:
        teacher_kind = action_kind(row["teacher_a_action_description"])
        # The stable selected leaves all have complete, deterministic first-action
        # counts; retain the concrete fingerprints/descriptions in the report.
        if row["baseline"]["first_action_agreement_rate"] == 0.0:
            mismatch_patterns[f"teacher_{teacher_kind}_vs_different_simpleagent_first_card"] += 1
        elif row["baseline"]["first_action_agreement_rate"] < 1.0:
            mismatch_patterns[f"teacher_{teacher_kind}_vs_mixed_simpleagent_first_action"] += 1
        else:
            mismatch_patterns["teacher_and_simpleagent_first_action_agree"] += 1

    group_rows = []
    for row in stable:
        group_rows.append({
            "group_id": row["group_id"],
            "leaf_snapshot_id": row["leaf_snapshot_id"],
            "baseline_abs_residual": abs(row["baseline_residual_vs_teacher_a"]),
            "treatment_abs_residual": abs(row["treatment_residual_vs_teacher_a"]),
            "fraction_baseline_absolute_error_removed": row["fraction_baseline_absolute_error_removed"],
        })
    report = {
        "schema": "silver_first_action_probe_analysis_v1",
        "source_probe": str(args.probe),
        "selection_rule": probe["selection"]["selection_rule"],
        "accepted_leaf_count": len(accepted),
        "stable_teacher_action_leaf_count": len(stable),
        "unstable_teacher_action_leaf_count": len(unstable),
        "stable_teacher_action_group_count": len(stable_groups),
        "aggregate_stable_baseline_absolute_residual": baseline_abs,
        "aggregate_stable_treatment_absolute_residual": treatment_abs,
        "aggregate_stable_fraction_baseline_absolute_error_removed": fraction_removed,
        "aggregate_stable_baseline_residual": sum(
            row["baseline_residual_vs_teacher_a"] for row in stable),
        "aggregate_stable_treatment_residual": sum(
            row["treatment_residual_vs_teacher_a"] for row in stable),
        "stable_mean_paired_utility_delta": (
            sum(row["paired_utility_delta_mean"] for row in stable) / len(stable)
            if stable else None),
        "classification": classification,
        "decision_rule": {
            "material_threshold": 0.50,
            "not_primary_threshold": 0.20,
            "multiple_groups_required_for_material": True,
        },
        "mismatch_patterns": dict(sorted(mismatch_patterns.items())),
        "stable_group_aggregate": group_rows,
        "stable_leaves": stable,
        "teacher_action_unstable_leaves": [
            {"group_id": row["group_id"], "leaf_snapshot_id": row["leaf_snapshot_id"],
             "teacher_a_action_description": row["teacher_a_action_description"],
             "teacher_b_action_description": row["teacher_b_action_description"],
             "baseline_residual_vs_teacher_a": row["baseline_residual_vs_teacher_a"],
             "treatment_residual_vs_teacher_a": row["treatment_residual_vs_teacher_a"]}
            for row in unstable],
        "note": "This is a mechanistic diagnostic, not a rollout-policy or default-promotion gate.",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "classification": classification,
        "stable_leaves": len(stable),
        "stable_groups": len(stable_groups),
        "aggregate_fraction_removed": fraction_removed,
        "unstable_leaves_excluded": len(unstable),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
