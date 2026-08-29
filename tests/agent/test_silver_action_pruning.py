import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_action_pruning", ROOT / "tools" / "analyze_silver_action_pruning.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SilverActionPruningAuditTest(unittest.TestCase):
    def test_boundary_ties_are_never_split(self):
        retained, ties = MODULE.candidate_indices([4.0, 3.0, 3.0, 1.0], "top_2")
        self.assertEqual(retained, {0, 1, 2})
        self.assertEqual(ties, [[1, 2]])

    def test_regret_and_multi_action_candidate_retention(self):
        rows = [
            {"silver_order": 0, "model_score": 4.0, "reference_q": 1.0,
             "action_fingerprint": "sa/t=1/x=a", "scores": {}},
            {"silver_order": 1, "model_score": 3.0, "reference_q": 4.0,
             "action_fingerprint": "sa/t=1/x=b", "scores": {}},
            {"silver_order": 2, "model_score": 2.0, "reference_q": 2.0,
             "action_fingerprint": "sa/t=5/x=c", "scores": {}},
        ]
        top_one = MODULE.one_parent(rows, "frozen_model", "top_1")
        self.assertFalse(top_one["best_retained"])
        self.assertEqual(top_one["regret"], 3.0)
        self.assertEqual(top_one["retained_fraction"], 1 / 3)

    def test_bootstrap_is_deterministic_at_parent_level(self):
        candidate = {"a": {"best_retained": True, "regret": 0.0, "retained_fraction": .5},
                     "b": {"best_retained": False, "regret": 1.0, "retained_fraction": .5}}
        control = {"a": {"best_retained": False, "regret": 1.0, "retained_fraction": 1.0},
                   "b": {"best_retained": False, "regret": 2.0, "retained_fraction": 1.0}}
        self.assertEqual(MODULE.bootstrap_delta(candidate, control, 50, 91),
                         MODULE.bootstrap_delta(candidate, control, 50, 91))


if __name__ == "__main__":
    unittest.main()
