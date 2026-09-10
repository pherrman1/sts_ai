"""Synthetic analysis checks; no simulator or experimental corpus is consumed."""
import json
import unittest
from unittest.mock import patch

import numpy as np

from tools import analyze_ooc_semantic_confirmation as confirmation


def row(seed, action, source=7, q=0.1, compound=False):
    return {
        "_group": (seed, 0), "sourceSeed": str(seed), "decisionIdx": "0",
        "semanticSource": str(source), "semanticEffect": "17",
        "semanticPayload": '{"type":"none"}',
        "executedPrimitiveBits": json.dumps([action, 42] if compound else [action]),
        "semanticActionIdx": str(action), "qProduct": str(q), "richRow": "1,2,3",
    }


class ConfirmationTests(unittest.TestCase):
    def test_family_mapping_and_whole_decision_compounds(self):
        rows = [row(1, 0, 0, compound=True), row(1, 1, 1), row(2, 0, 4), row(2, 1, 3)]
        metadata = confirmation.group_metadata(rows)
        self.assertEqual(metadata[(1, 0)], {"indices": [0, 1], "family": "CAMPFIRE", "compound": True})
        self.assertEqual(metadata[(2, 0)]["family"], "SHOP")
        predictions = {name: np.asarray([1., 0., 0., 1.]) for name in ("SEMANTIC", "PRIMITIVE", "ACTION_AGNOSTIC")}
        report = confirmation.slice_report(rows, predictions, metadata[(1, 0)]["indices"])
        self.assertEqual((report["decisions"], report["rows"]), (1, 2))

    def test_all_seven_families_and_mixed_rejection(self):
        sources = (7, 1, 3, 5, 8, 9, 6)
        rows = [row(seed, 0, source) for seed, source in enumerate(sources)]
        self.assertEqual({item["family"] for item in confirmation.group_metadata(rows).values()}, set(confirmation.FAMILIES))
        with self.assertRaisesRegex(ValueError, "mixed semantic"):
            confirmation.group_metadata([row(1, 0, 7), row(1, 1, 3)])

    def test_bootstrap_pairs_decisions_not_rows_and_skips_tied_pairs(self):
        semantic = [{"group": [1, 0], "regret": 0., "pairwise_concordance": 1., "top_or_tied": 1},
                    {"group": [2, 0], "regret": .2, "pairwise_concordance": float("nan"), "top_or_tied": 0}]
        primitive = [{**item, "regret": item["regret"] + .1, "pairwise_concordance": .5} for item in semantic]
        result = confirmation.paired_intervals(semantic, primitive)
        self.assertEqual(result["mean_selected_regret"]["decisions"], 2)
        self.assertEqual(result["macro_pairwise_concordance"]["decisions"], 1)
        self.assertAlmostEqual(result["mean_selected_regret"]["difference"], -.1)
        self.assertEqual(result["macro_pairwise_concordance"]["ci95"], [.5, .5])

    def test_requested_rule_eligibility_does_not_add_stricter_requirements(self):
        metrics = {"mean_selected_regret": {"difference": -.03, "ci95": [-.04, -.02]},
                   "macro_pairwise_concordance": {"difference": .05, "ci95": [.01, .09]}}
        leave_out = {"family": {"SHOP": metrics}, "fold": {"0": metrics}}
        result = confirmation.classify(metrics, leave_out)
        self.assertTrue(result["requested_rule_evidence"]["semantic"]["point_and_at_least_one_ci_eligible"])
        self.assertEqual(result["classification_status"], "provisional_pending_explicit_interpretation")
        uncertain = {**metrics, "mean_selected_regret": {"difference": -.01, "ci95": [-.03, .01]}}
        result = confirmation.classify(uncertain, leave_out)
        self.assertTrue(result["requested_rule_evidence"]["semantic"]["point_and_at_least_one_ci_eligible"])
        adverse = {**metrics, "mean_selected_regret": {"difference": .01, "ci95": [-.01, .03]}}
        result = confirmation.classify(metrics, {"family": {"SHOP": adverse}})
        self.assertTrue(result["requested_rule_evidence"]["semantic"]["point_and_at_least_one_ci_eligible"])
        self.assertEqual(result["requested_rule_evidence"]["semantic"]["leave_out_direction_diagnostic"]["family"], {"favorable": 0, "total": 1})
        result = confirmation.classify(adverse, leave_out)
        self.assertFalse(result["requested_rule_evidence"]["semantic"]["point_and_at_least_one_ci_eligible"])

    def test_synthetic_end_to_end_grouped_cv_fixed_params_and_json(self):
        rows = [row(seed, action, (7, 1, 3, 5, 8, 9, 6)[seed % 7], q=.1 + .1 * action,
                    compound=(seed % 2 == 0 and action == 1)) for seed in range(14) for action in range(2)]
        calls = []

        class FakeModel:
            def predict(self, x):
                return np.zeros(len(x))

        def train(x, y, params):
            calls.append((len(x), y.copy(), params.copy()))
            return FakeModel()

        with patch.object(confirmation.probe, "train_model", train):
            report = confirmation.analyze(rows, {"synthetic": True})
        json.dumps(report, allow_nan=False)
        self.assertEqual(len(calls), 15)
        self.assertTrue(all(params == confirmation.MODEL_PARAMS for _, _, params in calls))
        self.assertTrue(all(abs(float(y.mean())) < 1e-12 for _, y, _ in calls))
        memberships = [tuple(group) for values in report["folds"]["membership"].values() for group in values]
        self.assertEqual(len(memberships), len(set(memberships)))
        self.assertEqual(len(memberships), 14)
        self.assertEqual(set(report["family_breakdown"]), set(confirmation.FAMILIES))
        compounds = report["compound_breakdown"]
        self.assertEqual(compounds["compound_containing_decisions"]["decisions"], 7)
        self.assertEqual(compounds["compound_containing_decisions"]["rows"], 14)
        self.assertEqual(report["cross_validation"]["arms"]["ACTION_AGNOSTIC"]["macro"]["pairwise_concordance"], .5)


if __name__ == "__main__":
    unittest.main()
