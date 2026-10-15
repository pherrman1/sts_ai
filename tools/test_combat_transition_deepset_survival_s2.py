import unittest

import torch

from tools import combat_transition_deepset_survival_s2 as experiment


class DeepSetsSurvivalS2Tests(unittest.TestCase):
    def test_matched_decoder_shape_and_parameter_count(self):
        head = experiment.new_head()
        self.assertEqual(tuple(head(torch.zeros((3, 64))).shape), (3, 1))
        self.assertEqual(sum(parameter.numel() for parameter in head.parameters()), 4225)

    def test_objective_is_unregularized_bce(self):
        head = experiment.new_head()
        features = torch.zeros((2, 64))
        labels = torch.tensor([0.0, 1.0])
        expected = torch.nn.functional.binary_cross_entropy_with_logits(
            head(features).flatten(), labels
        )
        self.assertAlmostEqual(float(experiment.objective(head, features, labels)), float(expected))


if __name__ == "__main__":
    unittest.main()
