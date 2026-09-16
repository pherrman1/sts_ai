import unittest

import numpy as np
import torch

from tools import combat_transition_shared_potion_encoder as screen


class SharedPotionEncoderScreenTests(unittest.TestCase):
    def test_teacher_pass_boundary(self):
        a = {"trajectoryNll": 1.0, "normalNoChangeBrier": 0.1,
             "normalActionModeAccuracy": .9, "normalCountAccuracy": .9,
             "illegalProbabilityMax": 0., "normalizationErrorMax": 0., "slices": {}}
        b = dict(a, trajectoryNll=1.019, normalNoChangeBrier=.109,
                 normalActionModeAccuracy=.891, normalCountAccuracy=.89)
        decision, gates = screen.compare_teacher(a, b)
        self.assertEqual(decision, "TEACHER_FORCED_PASS")
        self.assertAlmostEqual(gates["trajectoryNllRelative"], .019)

    def test_teacher_rejects_explicit_bounds(self):
        a = {"trajectoryNll": 1.0, "normalNoChangeBrier": 0.1,
             "normalActionModeAccuracy": .9, "normalCountAccuracy": .9,
             "illegalProbabilityMax": 0., "normalizationErrorMax": 0., "slices": {}}
        b = dict(a, trajectoryNll=1.021)
        self.assertEqual(screen.compare_teacher(a, b)[0], "TEACHER_FORCED_REJECTED")
        b = dict(a, normalNoChangeBrier=.111)
        self.assertEqual(screen.compare_teacher(a, b)[0], "TEACHER_FORCED_REJECTED")

    def test_teacher_rejects_obvious_slice_regression(self):
        a = {"trajectoryNll": 1.0, "normalNoChangeBrier": 0.1,
             "normalActionModeAccuracy": .9, "normalCountAccuracy": .9,
             "illegalProbabilityMax": 0., "normalizationErrorMax": 0.,
             "slices": {"brew": {"trajectoryNll": 1.0}}}
        b = dict(a, slices={"brew": {"trajectoryNll": 1.11}})
        self.assertEqual(screen.compare_teacher(a, b)[0], "TEACHER_FORCED_REJECTED")

    def test_candidate_upstream_loads_attention_checkpoint_with_10_scalars(self):
        width = len(screen.composed.base.CONTINUOUS_GLOBAL_FIELDS)
        classes = np.arange(-2, 3, dtype=np.int64)
        delta_values = np.arange(11, dtype=np.int64)
        source = screen.stochastic_hp.new_model(
            torch, np.zeros(width, np.float32), np.ones(width, np.float32),
            len(delta_values), classes, screen.RECIPE["seed"]
        )
        head = torch.nn.Linear(64, len(delta_values))
        student, loaded_head = screen.candidate_upstream(
            {"stateDict": source.state_dict(), "maxHpHeadStateDict": head.state_dict()},
            classes, delta_values, "cpu"
        )
        self.assertEqual(tuple(student.encoder.scalar_mean.shape), (width,))
        self.assertEqual(tuple(loaded_head.weight.shape), (len(delta_values), 64))


if __name__ == "__main__":
    unittest.main()
