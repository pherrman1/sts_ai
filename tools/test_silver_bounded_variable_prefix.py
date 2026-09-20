#!/usr/bin/env python3
"""Focused deterministic contracts for the bounded Phase-A selector."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "silver_bounded_variable_prefix",
    ROOT / "tools/analyze_silver_bounded_variable_prefix.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def surface(values):
    metadata = {}
    candidates = {}
    for key, samples in values.items():
        metadata[key] = {"requested_prefix_fingerprints": key.split("/"),
                         "requested_prefix_descriptions": [key]}
        candidates[key] = {i: value for i, value in enumerate(samples)}
    return candidates, metadata


class BoundedPrefixContracts(unittest.TestCase):
    def test_selection_halves_are_disjoint_and_stage_two_is_fresh(self):
        candidates, metadata = surface({"a": [1.0] * 32, "b": [0.0] * 32,
                                         "a/x": [0.0] * 32, "a/y": [2.0] * 32})
        result = MODULE.beam_direction(candidates, metadata, 0, 1, 2, 2)
        self.assertEqual(result["stage1_indices"], [0, 1])
        self.assertEqual(result["stage2_indices"], [2, 3])
        self.assertTrue(set(result["stage1_indices"]).isdisjoint(result["stage2_indices"]))

    def test_stop_parent_is_a_stage_two_finalist(self):
        candidates, metadata = surface({"a": [3.0] * 32, "a/x": [2.0] * 32,
                                         "a/y": [1.0] * 32})
        result = MODULE.beam_direction(candidates, metadata, 0, 1, 1, 1)
        self.assertEqual(result["finalist_count"], 3)
        self.assertEqual(result["selected"], "a")

    def test_only_retained_parent_children_enter_stage_two(self):
        candidates, metadata = surface({"a": [3.0] * 32, "a/x": [4.0] * 32,
                                         "b": [2.0] * 32, "b/x": [100.0] * 32,
                                         "c": [1.0] * 32, "c/x": [100.0] * 32})
        result = MODULE.beam_direction(candidates, metadata, 0, 1, 1, 1)
        self.assertEqual(result["retained_first_action_count"], 1)
        self.assertEqual(result["retained_child_count"], 1)
        self.assertEqual(result["finalist_count"], 2)
        self.assertEqual(result["selected"], "a/x")

    def test_cost_accounting_is_exact(self):
        candidates, metadata = surface({"a": [3.0] * 32, "a/x": [3.0] * 32,
                                         "b": [2.0] * 32, "b/x": [2.0] * 32})
        result = MODULE.beam_direction(candidates, metadata, 0, 2, 1, 2)
        # 2 first actions * 1 + (2 parents + 2 children) * 2.
        self.assertEqual(result["selector_cost"], 10)

    def test_deterministic_prefix_key_tie_break(self):
        candidates, metadata = surface({"z": [1.0] * 32, "a": [1.0] * 32})
        result = MODULE.flat_direction(candidates, metadata, 0, 1)
        self.assertEqual(result["selected"], "z")

    def test_flat_k16_has_full_selection_half(self):
        candidates, metadata = surface({"a": [1.0] * 32, "b": [2.0] * 32})
        result = MODULE.flat_direction(candidates, metadata, 0, 16)
        self.assertEqual(result["stage1_indices"], list(range(16)))
        self.assertEqual(result["selected"], "b")

    def test_evaluation_uses_the_opposite_entire_half(self):
        candidates, metadata = surface({"a": [10.0] * 16 + [1.0] * 16,
                                         "b": [9.0] * 16 + [100.0] * 16})
        result_a = MODULE.flat_direction(candidates, metadata, 0, 1)
        result_b = MODULE.flat_direction(candidates, metadata, 16, 1)
        self.assertEqual(result_a["selected"], "a")
        self.assertEqual(result_a["evaluation_value"], 1.0)
        self.assertEqual(result_b["selected"], "b")
        self.assertEqual(result_b["evaluation_value"], 9.0)

    def test_stage_two_can_choose_extension_over_stop(self):
        candidates, metadata = surface({"a": [0.0] * 32, "a/x": [2.0] * 32})
        result = MODULE.beam_direction(candidates, metadata, 0, 1, 1, 1)
        self.assertEqual(result["selected"], "a/x")

    def test_duplicate_candidate_replicate_is_rejected(self):
        rows = [{"accepted": True, "requested_prefix_key": "a", "replicate": 0,
                 "original_root_corrected_utility": 1.0,
                 "requested_prefix_fingerprints": ["a"]},
                {"accepted": True, "requested_prefix_key": "a", "replicate": 0,
                 "original_root_corrected_utility": 2.0,
                 "requested_prefix_fingerprints": ["a"]}]
        with self.assertRaises(ValueError):
            MODULE.complete_candidates(rows)

    def test_expected_oracle_mismatch_fails_closed(self):
        with self.assertRaises(SystemExit):
            MODULE.require_k16_reproduction({"passed": False}, Path("expected.json"))
        MODULE.require_k16_reproduction({"passed": True}, Path("expected.json"))
        MODULE.require_k16_reproduction({"passed": False}, None)

    def test_expensive_classification_does_not_require_teacher_b(self):
        report = {"recovered_oracle_fraction": 0.60,
                  "teacher_b_regret_reduction": -0.50,
                  "clustered_bootstrap": {
                      "baseline_minus_arm_regret": {"p025": 0.10}},
                  "cost": {"mean": 13.0}}
        self.assertEqual(MODULE.classify_arm(report), "expensive")

    def test_promising_classification_still_requires_teacher_b(self):
        report = {"recovered_oracle_fraction": 0.60,
                  "teacher_b_regret_reduction": -0.06,
                  "clustered_bootstrap": {
                      "baseline_minus_arm_regret": {"p025": 0.10}},
                  "cost": {"mean": 12.0}}
        self.assertIsNone(MODULE.classify_arm(report))

    def test_cheap_bad_teacher_b_blocks_global_expensive_classification(self):
        def report(cost, teacher_b):
            return {"recovered_oracle_fraction": 0.60,
                    "teacher_b_regret_reduction": teacher_b,
                    "clustered_bootstrap": {
                        "baseline_minus_arm_regret": {"p025": 0.10}},
                    "cost": {"mean": cost, "p95": cost},
                    "candidate_counts": {
                        "retained_first_action_count": {"maximum": 1}}}

        result = MODULE.classify_experiment(
            {"cheap_bad_teacher_b": report(10.0, -0.50),
             "expensive_signal": report(20.0, -0.50)},
            ("cheap_bad_teacher_b", "expensive_signal"))
        self.assertEqual(result["signal_arms"],
                         ["cheap_bad_teacher_b", "expensive_signal"])
        self.assertEqual(result["expensive_arms"], ["expensive_signal"])
        self.assertEqual(result["classification"],
                         "BOUNDED_PREFIX_SELECTOR_INSUFFICIENT")

    def test_bootstrap_contract_clusters_shared_source_seed(self):
        rows = []
        for group, source in (("g1", "s"), ("g2", "s"), ("g3", "t")):
            for leaf in (f"{group}-a", f"{group}-b"):
                rows.append({"group_id": group, "leaf_snapshot_id": leaf,
                             "source_seed": source, "baseline_value": 0.0,
                             "arm_value": 0.0, "teacher_a": 1.0,
                             "teacher_b": 1.0})
        result = MODULE.bootstrap_difference(rows, "arm_value", 20)
        self.assertEqual(result["cluster_key"], "source_seed")
        self.assertEqual(result["cluster_count"], 2)


if __name__ == "__main__":
    unittest.main()
