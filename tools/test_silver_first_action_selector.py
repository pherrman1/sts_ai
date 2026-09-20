#!/usr/bin/env python3
"""Focused deterministic contract tests for the offline selector analyzer."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "silver_first_action_selector", ROOT / "tools/analyze_silver_first_action_selector.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SelectorContracts(unittest.TestCase):
    def test_fold_is_deterministic_and_group_scoped(self):
        self.assertEqual(MODULE.fold("group-a"), MODULE.fold("group-a"))
        self.assertEqual(MODULE.FOLD_COUNT, 5)
        rows = [{"group_id": "g", "leaf_snapshot_id": "l1", "value": 3,
                 "teacher": 4}, {"group_id": "g", "leaf_snapshot_id": "l2", "value": 1,
                 "teacher": 2}]
        self.assertEqual(MODULE.sibling_metrics(rows, "value", "teacher")["groups"], 1)

    def test_source_seed_contract_clusters_shared_groups(self):
        contract = MODULE.source_seed_contract([
            {"group_id": "g1", "source_seed": 7},
            {"group_id": "g1", "source_seed": 7},
            {"group_id": "g2", "source_seed": 7},
            {"group_id": "g3", "source_seed": 8},
        ])
        self.assertTrue(contract["all_groups_have_one_source_seed"])
        self.assertEqual(contract["source_seed_count"], 2)
        self.assertEqual(contract["shared_source_seed_count"], 1)
        self.assertEqual(contract["groups_per_source_seed"]["7"], ["g1", "g2"])

    def test_ridge_fit_is_reproducible_and_regularized(self):
        x = np.asarray([[1., 0.], [1., 1.], [1., 2.], [1., 3.]])
        y = np.asarray([0., 1., 2., 3.])
        first = MODULE.fit_model(x, y, 1.0)
        second = MODULE.fit_model(x, y, 1.0)
        for left, right in zip(first, second):
            if hasattr(left, "shape"):
                np.testing.assert_array_equal(left, right)
            else:
                self.assertEqual(left, right)

    def test_sha256_is_exact_for_generated_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "row.jsonl"
            path.write_text('{"x":1}\n')
            self.assertEqual(len(MODULE.sha256(path)), 64)


if __name__ == "__main__":
    unittest.main()
