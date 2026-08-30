import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_learned_replay", ROOT / "tools" / "analyze_silver_learned_visit_replay.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AnalyzeSilverLearnedVisitReplayTest(unittest.TestCase):
    def header(self):
        return {"judgment": MODULE.REPLAY_JUDGMENT}

    def rows(self):
        return [{"group_id": "root", "replicate": 0, "arm": arm, "budget": 32,
                 "search_seed": 7, "frozen_b_best_action_fingerprint": "best",
                 "frozen_b_best_q": 3.0}
                for arm in MODULE.ARMS]

    def comparisons(self, learned_top, learned_top_ci, learned_regret, learned_regret_ci):
        return [
            {"treatment": "oracle_visit_puct", "control": "current_uct",
             "mean_top_probability_delta": .10, "mean_regret_delta": -.40,
             "top_probability_delta_ci95": [.02, .18], "mean_regret_delta_ci95": [-.70, -.10]},
            {"treatment": "learned_visit_puct", "control": "current_uct",
             "mean_top_probability_delta": learned_top, "mean_regret_delta": learned_regret,
             "top_probability_delta_ci95": learned_top_ci, "mean_regret_delta_ci95": learned_regret_ci},
        ]

    def means(self):
        return {arm: {} for arm in MODULE.ARMS}

    def test_rejects_seed_mismatch_across_arms(self):
        rows = self.rows()
        rows[-1]["search_seed"] = 8
        with self.assertRaisesRegex(ValueError, "search-seed mismatch"):
            MODULE.validate_arm_alignment(self.header(), rows)

    def test_rejects_duplicate_or_missing_arm(self):
        rows = self.rows()
        rows[-1]["arm"] = "current_uct"
        with self.assertRaisesRegex(ValueError, "duplicate/missing arm"):
            MODULE.validate_arm_alignment(self.header(), rows)

    def test_positive_decision_boundary(self):
        decision = MODULE.replay_decision(
            self.means(), self.comparisons(.04, [.01, .08], -.20, [-.40, -.02]))
        self.assertEqual(decision["classification"], "POSITIVE")

    def test_negative_requires_neutral_harmful_points_and_both_recovery_intervals(self):
        negative = MODULE.replay_decision(
            self.means(), self.comparisons(0.0, [-.03, .01], 0.0, [-.05, .05]))
        self.assertEqual(negative["classification"], "NEGATIVE_LINEAR_MODEL")
        only_one_condition = MODULE.replay_decision(
            self.means(), self.comparisons(0.0, [-.03, .08], 0.0, [-.05, .05]))
        self.assertEqual(only_one_condition["classification"], "INCONCLUSIVE")

    def test_current_inconclusive_boundary(self):
        decision = MODULE.replay_decision(
            self.means(), self.comparisons(.0238095238, [-.03968254, .08730159],
                                           -.2820521291, [-.74003727, .17716170]))
        self.assertEqual(decision["classification"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
