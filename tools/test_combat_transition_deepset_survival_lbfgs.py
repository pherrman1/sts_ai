import unittest

import torch

from tools import combat_transition_deepset_survival_lbfgs as experiment


class DeepSetsSurvivalLbfgsTests(unittest.TestCase):
    def test_objective_includes_fixed_l2_penalty(self):
        head = torch.nn.Linear(2, 1, bias=False)
        with torch.no_grad():
            head.weight.fill_(1.0)
        features = torch.zeros((2, 2), dtype=torch.float32)
        labels = torch.tensor([0.0, 1.0])
        nll = torch.nn.functional.binary_cross_entropy_with_logits(
            head(features).flatten(), labels
        )
        self.assertGreater(float(experiment.objective(head, features, labels)), float(nll))


if __name__ == "__main__":
    unittest.main()
