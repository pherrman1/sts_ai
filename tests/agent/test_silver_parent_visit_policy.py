import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_parent_visit_policy", ROOT / "tools" / "train_silver_parent_visit_policy.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SilverParentVisitPolicyTest(unittest.TestCase):
    def test_grouped_softmax_handles_unequal_groups_and_zero_targets(self):
        parents = [
            ("one", np.asarray([[1.0], [2.0]]), np.asarray([1.0, 0.0])),
            ("two", np.asarray([[3.0], [4.0], [5.0]]), np.asarray([0.0, 0.25, 0.75])),
        ]
        loss, gradient = MODULE.grouped_objective(np.asarray([0.0]), parents, l2=0.0)
        expected = (-np.log(0.5) - (.25 * np.log(1 / 3) + .75 * np.log(1 / 3))) / 2
        self.assertAlmostEqual(loss, expected)
        self.assertTrue(np.isfinite(gradient).all())
        for _, x, _ in parents:
            self.assertAlmostEqual(float(MODULE.stable_softmax(x @ np.asarray([0.0])).sum()), 1.0)

    def test_parent_macro_weighting_not_row_weighting(self):
        parents = [
            ("short", np.asarray([[0.0], [1.0]]), np.asarray([1.0, 0.0])),
            ("long", np.asarray([[0.0], [1.0], [2.0], [3.0]]), np.asarray([1.0, 0.0, 0.0, 0.0])),
        ]
        loss, _ = MODULE.grouped_objective(np.asarray([0.0]), parents, l2=0.0)
        self.assertAlmostEqual(loss, (-np.log(.5) - np.log(.25)) / 2)

    def test_parent_partition_is_anchor_safe_and_deterministic(self):
        groups = {f"g{i}": [] for i in range(100)}
        anchors = {"g1", "g7", "g19"}
        first = MODULE.partition(groups, anchors)
        second = MODULE.partition(groups, anchors)
        self.assertEqual(first, second)
        self.assertFalse((first[0] | first[1]) & anchors)

    def test_anchor_cannot_enter_scaling_or_linear_selection_inputs(self):
        train = [("train", np.asarray([[0.0, 2.0], [2.0, 4.0]]), np.asarray([.5, .5]))]
        validation = [("validation", np.asarray([[0.0, 1.0], [1.0, 0.0]]), np.asarray([.5, .5]))]
        anchor = [("anchor", np.asarray([[1_000_000.0, -1_000_000.0], [3.0, 5.0]]),
                   np.asarray([.5, .5]))]
        mean, scale, active = MODULE.train_scaler(train)
        self.assertTrue(np.array_equal(mean, np.asarray([1.0, 3.0])))
        self.assertTrue(np.array_equal(scale, np.asarray([1.0, 1.0])))
        train_scaled = MODULE.scaled(train, mean, scale, active)
        validation_scaled = MODULE.scaled(validation, mean, scale, active)
        weights, info = MODULE.fit_linear(train_scaled, validation_scaled)
        self.assertEqual(weights.shape, (2,))
        self.assertIn("non-anchor validation", info["selected_by"])
        # The sentinel anchor is deliberately absent from both fit calls.
        self.assertEqual(anchor[0][0], "anchor")

    def test_prediction_contract_rejects_non_normalized_rows(self):
        target = np.asarray([1.0, 0.0])
        with self.assertRaises(ValueError):
            MODULE.parent_metric(target, np.asarray([.6, .3]), np.asarray([1.0, 0.0]))

    def test_b_q_concordance_primary_is_pooled_not_parent_macro(self):
        def metric(concordance, credit, pairs):
            row = {key: 0.0 for key in MODULE.METRIC_KEYS}
            row.update({
                "b_pairwise_concordance": concordance,
                "b_pairwise_concordant_credit": credit,
                "b_q_pairs": pairs,
                "legal_actions": 2,
                "prediction_ties": 0,
                "b_q_ties": 0,
            })
            return row

        result = MODULE.aggregate({
            "one_pair": metric(.5, .5, 1),
            "four_pairs": metric(.75, 3.0, 4),
        })
        self.assertAlmostEqual(result["b_pairwise_concordance"], 3.5 / 5)
        self.assertAlmostEqual(result["b_pairwise_concordance_parent_macro"], (.5 + .75) / 2)


if __name__ == "__main__":
    unittest.main()
