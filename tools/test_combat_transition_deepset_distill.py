import unittest

import numpy as np
import torch

from tools import combat_transition_deepset_distill as experiment


class DeepSetsDistillTests(unittest.TestCase):
    def _inputs(self):
        return [
            torch.zeros((2, 10), dtype=torch.float32),
            torch.zeros((2, 4), dtype=torch.int64),
            torch.tensor([[[1, 0, 0, 0], [2, 1, 3, 1], [0, 0, 0, 0]], [[3, 0, 0, 0], [0, 0, 0, 0], [4, 1, 2, 0]]], dtype=torch.int16),
            torch.tensor([[[1, 0, 0], [2, 1, 1], [0, 0, 0]], [[3, 0, 0], [0, 0, 0], [4, 1, 2]]], dtype=torch.int16),
            torch.tensor([[[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]], [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]], dtype=torch.int16),
            torch.tensor([[True, True, False], [True, False, True]]),
            torch.tensor([[True, True, False], [True, False, True]]),
        ]

    def test_shape_finite_and_parameter_count(self):
        model = experiment.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10, dtype=np.float32), np.ones(10, dtype=np.float32)).net
        output = model(*self._inputs())
        self.assertEqual(tuple(output.shape), (2, 64))
        self.assertTrue(torch.isfinite(output).all().item())
        self.assertEqual(experiment.parameter_count(model), 94_424)

    def test_masked_card_and_relic_pooling_is_permutation_invariant(self):
        torch.manual_seed(20260912)
        model = experiment.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10, dtype=np.float32), np.ones(10, dtype=np.float32)).net.eval()
        first = self._inputs()
        second = [value.clone() for value in first]
        card_order = torch.tensor([1, 0, 2])
        relic_order = torch.tensor([1, 0, 2])
        second[2] = second[2][:, card_order]
        second[5] = second[5][:, card_order]
        second[3] = second[3][:, relic_order]
        second[6] = second[6][:, relic_order]
        torch.testing.assert_close(model(*first), model(*second), rtol=0, atol=1e-6)

    def test_initialization_is_seed_deterministic(self):
        def make():
            torch.manual_seed(20260912)
            return experiment.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10, dtype=np.float32), np.ones(10, dtype=np.float32)).net
        left = experiment.reference.state_hash(make())
        right = experiment.reference.state_hash(make())
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
