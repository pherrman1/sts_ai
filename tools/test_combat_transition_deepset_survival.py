import unittest

import numpy as np
import torch

from tools import combat_transition_deepset_survival as experiment


class DeepSetsSurvivalTests(unittest.TestCase):
    def test_state_digest_is_order_independent(self):
        first = {"bias": torch.tensor([1.0]), "weight": torch.tensor([[2.0]])}
        second = {"weight": torch.tensor([[2.0]]), "bias": torch.tensor([1.0])}
        self.assertEqual(experiment.state_digest(first), experiment.state_digest(second))

    def test_auc_is_chance_for_tied_scores(self):
        labels = np.array([0, 1, 0, 1], dtype=np.int8)
        probabilities = np.full(4, 0.5, dtype=np.float32)
        self.assertAlmostEqual(experiment.auc_score(labels, probabilities), 0.5)

    def test_calibration_covers_each_row_once(self):
        labels = np.array([0, 1, 1], dtype=np.int8)
        probabilities = np.array([0.0, 0.5, 1.0], dtype=np.float32)
        table = experiment.calibration(probabilities, labels)
        self.assertEqual(sum(row["rows"] for row in table), len(labels))

    def test_representation_rows_are_train_and_validation_only(self):
        cache = {"ids": np.arange(6), "split": np.array([0, 0, 1, 1, 2, 2], dtype=np.int8)}
        target = np.flatnonzero(cache["split"] < 2)
        self.assertEqual(len(target), 4)
        self.assertTrue(np.array_equal(cache["ids"][target], [0, 1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
