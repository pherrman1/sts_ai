import unittest

import numpy as np
import torch

from tools import combat_transition_deepset_downstream as experiment


class DeepSetsDownstreamTests(unittest.TestCase):
    def test_non_z_fingerprints_exclude_only_z(self):
        cache = {
            "ids": np.array([4, 5], dtype=np.int64),
            "z": np.zeros((2, 64), dtype=np.float32),
            "potionZ": np.ones((2, 64), dtype=np.float32),
            "observed": np.array([[True, False], [False, True]]),
        }
        before = experiment.cache_fingerprints(cache)
        cache["z"][0, 0] = 9
        self.assertEqual(before, experiment.cache_fingerprints(cache))
        cache["potionZ"][0, 0] = 9
        self.assertNotEqual(before, experiment.cache_fingerprints(cache))

    def test_optimizer_scope_is_exactly_downstream_networks(self):
        nets = torch.nn.ModuleDict({"head": torch.nn.Linear(3, 2)})
        optimizer = torch.optim.AdamW(nets.parameters(), lr=0.001)
        experiment.assert_optimizer_scope(nets, optimizer)

        outsider = torch.nn.Parameter(torch.ones(1))
        bad = torch.optim.AdamW(list(nets.parameters()) + [outsider], lr=0.001)
        with self.assertRaisesRegex(ValueError, "outside downstream"):
            experiment.assert_optimizer_scope(nets, bad)

    def test_candidate_shape_and_finite_contract(self):
        valid = np.zeros((3, 64), dtype=np.float32)
        self.assertEqual(valid.shape, (3, 64))
        self.assertTrue(np.isfinite(valid).all())
        invalid = valid.copy()
        invalid[1, 2] = np.inf
        self.assertFalse(np.isfinite(invalid).all())

    def test_representation_rows_exclude_test_split(self):
        cache = {"split": np.array([0, 1, 2, 2, 0], dtype=np.int8)}
        np.testing.assert_array_equal(experiment.generated_representation_ids(cache), [0, 1, 4])


if __name__ == "__main__":
    unittest.main()
