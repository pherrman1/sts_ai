import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("rank4_replay", ROOT / "tools" / "analyze_silver_rank4_interaction_replay.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Rank4ReplayDecisionTest(unittest.TestCase):
    def means(self):
        return {"current_uct": {"mean_b_best_probability": .4, "mean_b_regret": 4.0},
                "oracle_visit_puct": {"mean_b_best_probability": .5, "mean_b_regret": 3.5}}

    def test_supported_and_rejected_boundaries(self):
        supported = {"mean_b_best_probability_delta": .02, "mean_frozen_b_regret_delta": -.15,
                     "b_best_probability_delta_ci95": [.001, .04], "mean_frozen_b_regret_delta_ci95": [-.3, .05]}
        self.assertEqual(MODULE.decision(supported, self.means())["classification"], "INTERACTION_SUPPORTED")
        rejected = {"mean_b_best_probability_delta": 0., "mean_frozen_b_regret_delta": 0.,
                    "b_best_probability_delta_ci95": [-.04, .01], "mean_frozen_b_regret_delta_ci95": [-.05, .02]}
        self.assertEqual(MODULE.decision(rejected, self.means())["classification"], "INTERACTION_REJECTED")


if __name__ == "__main__":
    unittest.main()
