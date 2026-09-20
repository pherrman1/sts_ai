#!/usr/bin/env python3
"""Focused deterministic contracts for tactical-prefix analysis."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "silver_tactical_prefix_oracle", ROOT / "tools/analyze_silver_tactical_prefix_oracle.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TacticalPrefixContracts(unittest.TestCase):
    def test_complete_candidates_fail_closed_on_missing_replicate(self):
        rows = [{"accepted": True, "requested_prefix_key": "a", "replicate": i,
                 "original_root_corrected_utility": float(i),
                 "requested_prefix_fingerprints": ["a"],
                 "requested_prefix_descriptions": ["A"]} for i in range(31)]
        complete, _ = MODULE.complete_candidates(rows)
        self.assertEqual(complete, {})

    def test_cross_fit_uses_opposite_evaluation_half(self):
        metadata = {
            "a": {"requested_prefix_fingerprints": ["a"],
                  "requested_prefix_descriptions": ["A"]},
            "b": {"requested_prefix_fingerprints": ["b"],
                  "requested_prefix_descriptions": ["B"]},
        }
        candidates = {
            "a": {i: (10.0 if i < 16 else 0.0) for i in range(32)},
            "b": {i: (9.0 if i < 16 else 100.0) for i in range(32)},
        }
        result = MODULE.cross_fit_leaf(candidates, metadata, 1)
        self.assertEqual(result["selected_prefixes"], ["a", "b"])
        self.assertEqual(result["oracle_value"], 4.5)

    def test_source_seed_bootstrap_keeps_sibling_groups_together(self):
        rows = []
        for group, source in (("g1", "s"), ("g2", "s"), ("g3", "t")):
            for leaf in (f"{group}-a", f"{group}-b"):
                rows.append({"group_id": group, "leaf_snapshot_id": leaf,
                             "source_seed": source, "baseline_value": 0.0,
                             "oracle_value": 0.0, "teacher_a": 1.0, "teacher_b": 1.0})
        contract = MODULE.source_seed_contract(rows)
        self.assertEqual(contract["shared_source_seed_count"], 1)
        result = MODULE.bootstrap_difference(rows, 20)
        self.assertEqual(result["cluster_key"], "source_seed")
        self.assertEqual(result["cluster_count"], 2)

    def test_reference_check_is_exact_for_matching_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.jsonl"
            path.write_text('{"accepted":true,"leaf_snapshot_id":"l","replicate":0,'
                            '"action_fingerprint":"a","original_root_corrected_utility":3.5}\n')
            report = MODULE.reference_check({("l", 0, "a"): 3.5}, path)
            self.assertEqual(report["matched_rows"], 1)
            self.assertEqual(report["max_absolute_utility_difference"], 0.0)
            self.assertTrue(report["passed"])

    def test_reference_check_rejects_unmatched_reference_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.jsonl"
            path.write_text(
                '{"accepted":true,"leaf_snapshot_id":"l","replicate":0,'
                '"action_fingerprint":"a","original_root_corrected_utility":3.5}\n'
                '{"accepted":true,"leaf_snapshot_id":"l","replicate":1,'
                '"action_fingerprint":"a","original_root_corrected_utility":4.5}\n')
            report = MODULE.reference_check({("l", 0, "a"): 3.5}, path)
            self.assertFalse(report["passed"])
            self.assertEqual(report["unmatched_reference_rows"], 1)

    def test_reduce_metrics_distinguishes_represented_and_scorable_groups(self):
        rows = []
        for group, leaves in (("g1", ("a", "b")), ("g2", ("c", "d")),
                              ("g3", ("e",))):
            for leaf in leaves:
                rows.append({"group_id": group, "leaf_snapshot_id": leaf,
                             "source_seed": "s", "baseline_value": 1.0,
                             "oracle_value": 1.0, "teacher_a": 2.0,
                             "teacher_b": 2.0, "selected_prefix_lengths": [1, 1]})
        report = MODULE.reduce_metrics(rows, 1)
        self.assertEqual(report["leaves"], 5)
        self.assertEqual(report["represented_groups"], 3)
        self.assertEqual(report["scorable_sibling_groups"], 2)


if __name__ == "__main__":
    unittest.main()
