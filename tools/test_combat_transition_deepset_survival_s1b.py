import unittest

import numpy as np
import torch

from tools import combat_transition_deepset_survival_s1b as experiment


class DeepSetsSurvivalS1bTests(unittest.TestCase):
    def test_constant_dimensions_are_stable_when_scale_is_one(self):
        representation = np.array([[2.0, 4.0], [2.0, 6.0]], dtype=np.float32)
        normalized = experiment.normalize_representation(
            representation,
            np.array([2.0, 5.0], dtype=np.float64),
            np.array([1.0, 1.0], dtype=np.float64),
        )
        np.testing.assert_allclose(normalized, [[0.0, -1.0], [0.0, 1.0]])

    def test_s1b_objective_has_no_regularization_term(self):
        head = torch.nn.Linear(2, 1, bias=False)
        with torch.no_grad():
            head.weight.fill_(1.0)
        features = torch.zeros((2, 2), dtype=torch.float32)
        labels = torch.tensor([0.0, 1.0])
        expected = torch.nn.functional.binary_cross_entropy_with_logits(
            head(features).flatten(), labels
        )
        self.assertAlmostEqual(
            float(experiment.objective(head, features, labels)), float(expected)
        )


if __name__ == "__main__":
    unittest.main()
