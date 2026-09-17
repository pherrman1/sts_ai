import unittest

import numpy as np
import torch

from tools import combat_transition_survival_deepset_train as experiment
from tools import test_combat_transition_deepset_distill as distill_tests


class SurvivalDeepSetsTrainTests(unittest.TestCase):
    def test_tiny_end_to_end(self):
        torch.manual_seed(17)
        model = experiment.SurvivalNet(torch.nn.Linear(10, 64))
        optimizer, proof = experiment.make_optimizer(model)
        initial = experiment.screen.state_digest(model.encoder.state_dict())
        features = torch.randn(8, 10)
        labels = torch.tensor([0., 1., 1., 0., 1., 1., 1., 0.])
        loss, gradients = experiment.update_batch(model, optimizer, [features], labels)
        self.assertTrue(np.isfinite(loss))
        self.assertTrue(all(value > 0 for value in gradients.values()))
        self.assertTrue(proof["exactParameterIds"])
        self.assertNotEqual(initial, experiment.screen.state_digest(model.encoder.state_dict()))
        cache = dict(ids=np.arange(8), win=labels.numpy().astype(bool), preHp=np.ones(8),
                     preMax=np.full(8, 10), boss=np.array([True, False] * 4))
        logits = model([features]).detach().numpy()
        result = experiment.compare(logits, logits, cache, np.arange(8))
        self.assertEqual(result["decision"], "SURVIVAL_DEEPSET_GO")
        self.assertEqual(result["slices"]["deaths"]["A"]["rows"], 3)

    def test_optimizer_groups_are_exact(self):
        model = experiment.SurvivalNet(torch.nn.Linear(10, 64))
        optimizer, _ = experiment.make_optimizer(model)
        self.assertEqual([group["lr"] for group in optimizer.param_groups], [1e-4, 1e-3])
        self.assertEqual({name.split(".")[0] for name, _ in model.named_parameters()}, {"encoder", "head"})

    def test_stopping_floor_patience_and_strict_tie(self):
        self.assertFalse(experiment.should_stop(11, 1))
        self.assertTrue(experiment.should_stop(12, 6))
        self.assertFalse(experiment.should_stop(12, 7))
        self.assertTrue(experiment.should_stop(40, 34))
        self.assertFalse(experiment.should_stop(40, 40))
        self.assertFalse(experiment.strict_minimum(0.06, 0.06))
        self.assertTrue(experiment.strict_minimum(0.059, 0.06))
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                experiment.strict_minimum(value, 0.06)

    def test_test_rows_and_mixed_splits_refused(self):
        cache = dict(split=np.array([0, 1, 2]), ids=np.arange(3))
        for indices, split in (([2], 1), ([2], 2), ([0, 1], 0), ([], 0)):
            with self.assertRaises(ValueError):
                experiment.inputs_for({}, cache, np.array(indices, dtype=int), "cpu", split)

    def test_invalid_population_cannot_qualify(self):
        cache = dict(ids=np.arange(2), win=np.array([True, False]), preHp=np.ones(2),
                     preMax=np.full(2, 10), boss=np.array([True, False]))
        result = experiment.compare(np.array([1., -1.]), np.array([1., -1.]),
                                    cache, np.arange(2), population_bound=False)
        self.assertEqual(result["decision"], "SURVIVAL_DEEPSET_REJECTED")

    def test_real_encoder_gradients_scope_and_normalization(self):
        encoder = experiment.screen.surrogate.DeepSetsEncoder(
            torch.nn, torch, np.arange(10, dtype=np.float32),
            np.full(10, 2, dtype=np.float32)).net
        model = experiment.SurvivalNet(encoder)
        initial = experiment.normalization_digest(encoder)
        optimizer, proof = experiment.make_optimizer(model)
        _, gradients = experiment.update_batch(model, optimizer,
            distill_tests.DeepSetsDistillTests()._inputs(), torch.tensor([0., 1.]))
        self.assertTrue(all(value > 0 for value in gradients.values()))
        self.assertEqual(initial, experiment.normalization_digest(encoder))
        self.assertEqual([group["elements"] for group in proof["groups"]], [94424, 65])

    def test_quality_miss_is_rejected(self):
        cache = dict(ids=np.arange(4), win=np.array([True, False, True, False]),
                     preHp=np.ones(4), preMax=np.full(4, 10), boss=np.array([True, False] * 2))
        result = experiment.compare(np.array([2., -2., 2., -2.]), np.zeros(4),
                                    cache, np.arange(4))
        self.assertEqual(result["decision"], "SURVIVAL_DEEPSET_REJECTED")
        self.assertFalse(result["gatesPassed"]["nllRelative"])


if __name__ == "__main__":
    unittest.main()
