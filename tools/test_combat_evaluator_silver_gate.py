#!/usr/bin/env python3
"""Focused synthetic checks for the decision-level Silver gate analyzer."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_combat_evaluator_silver_gate import (
    arm_metrics,
    automatic_gate_classification,
    bootstrap_test,
    candidate_gates,
    group_rows,
    join_inputs,
    ranking_metrics,
    select_gate,
    target_mismatch,
)


def synthetic_frame() -> pd.DataFrame:
    rows = []
    # A realistic source count is needed for the frozen stable split helper.
    # Each group
    # has two siblings and deliberately distinct predictor/Silver rankings.
    for source in range(1, 41):
        q_best = 0.60 + source / 100.0
        silver_best = "a" if source % 3 else "b"
        model_best = "b" if source % 4 == 1 else "a"
        p_min = 0.60 if source % 7 == 0 else 0.99
        expected = {"a": 0.10, "b": 0.20} if model_best == "b" else {"a": 0.20, "b": 0.10}
        p = {"a": p_min, "b": 0.995}
        for key in ("a", "b"):
            rows.append({
                "sourceSeed": source, "decisionIdx": 0, "semanticKey": key,
                "futureIdentity": 0, "branchFightIdx": 0, "semanticActionIdx": 0 if key == "a" else 1,
                "qProduct": q_best if key == silver_best else q_best - 0.10,
                "silverSimulations": 100 if key == "a" else 300,
                "expected_signed_outcome": expected[key], "p_win": p[key],
                "predicted_win_hp_frac": 0.8, "predicted_loss_remaining_frac": 0.2,
                "family": "REWARDS", "act": 1, "floor": source,
                "combat_encounter": "Cultist", "combat_roomClass": "NORMAL",
                "actual_won": 1, "actual_true_death": 0, "actual_label_valid": 1,
            })
    return pd.DataFrame(rows)


class SilverGateTest(unittest.TestCase):
    def test_model_metrics_use_complete_decisions_and_actual_branch_cost(self):
        groups = group_rows(synthetic_frame())
        accepted = {(g["sourceSeed"], g["decisionIdx"]) for g in groups[:1]}
        metrics = arm_metrics(groups, accepted)
        self.assertEqual(metrics["accepted_action_rows"], 2)
        self.assertEqual(metrics["avoided_silver_simulations"], 400)
        self.assertEqual(metrics["total_silver_simulations"], 40 * 400)
        # One accepted group contributes both siblings; no per-action mixing.
        self.assertEqual(metrics["rejected_decisions"], 39)

    def test_ranking_metrics_report_silver_ties_and_regret(self):
        groups = group_rows(synthetic_frame())
        report = ranking_metrics(groups)
        self.assertEqual(report["decisions"], 40)
        self.assertGreater(report["mean_regret"], 0.0)
        self.assertGreaterEqual(report["top_or_silver_tied_agreement"], 0.0)
        self.assertLessEqual(report["top_or_silver_tied_agreement"], 1.0)

    def test_gate_grid_is_decision_level_and_validation_selection_is_fixed(self):
        groups = group_rows(synthetic_frame())
        gates = candidate_gates(groups)
        self.assertEqual(len(gates), 5 * 7)
        for gate in gates:
            self.assertEqual(gate["accepted_action_rows"], gate["accepted_decisions"] * 2)

    def test_gate_selection_is_quality_first_then_savings(self):
        common = {"accepted_decisions": 1, "mean_regret": 0.004, "p95_regret": 0.02,
                  "margin": 0.0, "survival_threshold": 0.0, "signal": "min_p_win"}
        chosen = select_gate([
            {**common, "simulation_savings_fraction": 0.50},
            {**common, "simulation_savings_fraction": 0.75, "survival_threshold": 0.50},
            {**common, "simulation_savings_fraction": 0.99, "mean_regret": 0.006},
        ])
        self.assertEqual(chosen["simulation_savings_fraction"], 0.75)

    def test_bootstrap_resamples_source_seeds_not_sibling_rows(self):
        groups = group_rows(synthetic_frame())
        accepted = {(g["sourceSeed"], g["decisionIdx"]) for g in groups}
        result = bootstrap_test(groups, accepted, replicates=5000, seed=123)
        self.assertEqual(result["unit"], "sourceSeed")
        self.assertEqual(result["replicates"], 5000)
        self.assertEqual(result["source_groups"], 40)
        self.assertEqual(result["simulation_savings_fraction"]["estimate"], 1.0)

    def test_target_mismatch_reports_action_and_within_decision_views(self):
        groups = group_rows(synthetic_frame())
        result = target_mismatch(groups)
        self.assertEqual(result["all"]["decisions"], 40)
        self.assertEqual(result["all"]["action_rows"], 80)
        self.assertEqual(result["all_siblings_survive"]["decisions"], 40)
        self.assertEqual(result["at_least_one_sibling_dies"]["decisions"], 0)

    def test_target_mismatch_distinguishes_all_surviving_ranking_disagreement(self):
        groups = group_rows(synthetic_frame())
        disagreements = [group for group in groups
                         if group["all_siblings_survive"] and group["model_choice"] != group["silver_choice"]]
        self.assertTrue(disagreements)
        result = target_mismatch(groups)["all_siblings_survive"]
        self.assertLess(result["within_decision_spearman_macro"], 1.0)
        self.assertLess(result["macro_pairwise_concordance"], 1.0)

    def test_automatic_classification_is_provisional_and_cannot_emit_target_mismatch(self):
        groups = group_rows(synthetic_frame())
        accepted = {(group["sourceSeed"], group["decisionIdx"]) for group in groups}
        result = automatic_gate_classification(groups[0], groups, accepted)
        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertTrue(result["target_mismatch_requires_coordinator"])
        self.assertNotIn("TARGET MISMATCH", result["label"])

    def test_join_rejects_prediction_identity_mismatch(self):
        semantic = [{
            "sourceSeed": "1", "decisionIdx": "0", "semanticKey": "a", "futureIdentity": "0",
            "semanticActionIdx": "0", "qProduct": "0.5", "silverSimulations": "10",
            "act": "1", "floor": "1",
        }]
        combat = pd.DataFrame([{
            "sourceSeed": 1, "decisionIdx": 0, "semanticKey": "a", "futureIdentity": 0,
            "branchFightIdx": 0, "semanticActionIdx": 0, "act": 1, "floor": 1,
            "encounter": "Cultist", "roomClass": "NORMAL", "semanticSource": 7,
            "won": 1, "trueDeath": 0, "labelValid": 1,
        }])
        with tempfile.TemporaryDirectory() as directory:
            prediction_path = Path(directory) / "predictions.csv"
            with prediction_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "sourceSeed", "decisionIdx", "semanticKey", "futureIdentity", "branchFightIdx",
                    "p_win", "predicted_win_hp_frac", "predicted_loss_remaining_frac", "expected_signed_outcome",
                ])
                writer.writeheader()
                writer.writerow({"sourceSeed": 1, "decisionIdx": 0, "semanticKey": "different",
                                 "futureIdentity": 0, "branchFightIdx": 0, "p_win": .9,
                                 "predicted_win_hp_frac": .8, "predicted_loss_remaining_frac": .2,
                                 "expected_signed_outcome": .68})
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                join_inputs(semantic, combat, prediction_path)


if __name__ == "__main__":
    unittest.main()
