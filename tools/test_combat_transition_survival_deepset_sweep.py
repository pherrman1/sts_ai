import unittest

from tools import combat_transition_survival_deepset_sweep as sweep


class SurvivalDeepSetsSweepTests(unittest.TestCase):
    def test_arms_and_order_are_exact(self):
        self.assertEqual(sweep.ARM_ORDER, ("baseline", "lowerLr", "muchLowerLr",
                                           "moreWd", "strongWd", "lowerLrWd"))
        self.assertEqual(sweep.ARMS, {
            "baseline": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-4),
            "lowerLr": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=1e-4),
            "muchLowerLr": dict(encoderLr=2e-5, headLr=2e-4, weightDecay=1e-4),
            "moreWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=5e-4),
            "strongWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-3),
            "lowerLrWd": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=5e-4),
        })

    def test_stage_b_uses_fivefold_learning_rates(self):
        stage_a = dict(selectedEpoch=23)
        recipe = sweep.stage_b_recipe("baseline", stage_a)
        self.assertEqual(recipe["encoderLr"], 2e-5)
        self.assertEqual(recipe["headLr"], 2e-4)
        self.assertEqual(recipe["maxEpochs"], 15)
        self.assertEqual(recipe["minEpochs"], 5)

    def test_sweep_uses_unmodified_survival_gates(self):
        self.assertEqual(sweep.GATES, dict(nllRelative=0.02, brierRelative=0.05,
                                           deathNllRelative=0.10, lowPreHpNllRelative=0.10))


if __name__ == "__main__":
    unittest.main()
