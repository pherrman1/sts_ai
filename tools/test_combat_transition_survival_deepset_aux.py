import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch

from tools import combat_transition_survival_deepset_aux as experiment
from tools import test_combat_transition_deepset_distill as distill_tests


class AuxiliaryTests(unittest.TestCase):
    def test_paired_initialization_and_all_train_normalization(self):
        arrays = dict(globals_continuous=np.repeat([[0.], [8.], [1000.]], 10, axis=1).astype(np.float32))
        cache = dict(split=np.array([0, 0, 1]), ids=np.arange(3))
        mean, std = experiment.normalization(arrays, cache, np.array([0, 1]))
        np.testing.assert_array_equal(mean, np.full(10, 4.))
        with self.assertRaises(ValueError):
            experiment.normalization(arrays, cache, np.array([0]))
        old = experiment.initialize(np.zeros(10), np.ones(10)).encoder.state_dict()
        old['card_id.weight'] = old['card_id.weight'] + 1.
        warm = experiment.initialize(mean, std, old)
        scratch = experiment.initialize(mean, std)
        for name in ('head', 'hp'):
            for left, right in zip(getattr(warm, name).parameters(), getattr(scratch, name).parameters()):
                torch.testing.assert_close(left, right, rtol=0, atol=0)
        torch.testing.assert_close(warm.encoder.scalar_mean, scratch.encoder.scalar_mean)
        torch.testing.assert_close(warm.encoder.card_id.weight, old['card_id.weight'])
        self.assertFalse(torch.equal(warm.encoder.card_id.weight, scratch.encoder.card_id.weight))

    def test_auxiliary_masks_deaths_and_empty_survivors(self):
        logits = torch.tensor([0., 0.], requires_grad=True)
        hp = torch.tensor([0., 0.], requires_grad=True)
        survival, auxiliary = experiment.joint_loss(logits, hp, torch.tensor([0., 1.]), torch.tensor([float('nan'), .8]))
        self.assertAlmostEqual(float(survival.detach()), np.log(2), places=6)
        self.assertAlmostEqual(float(auxiliary.detach()), .09, places=6)
        (survival + auxiliary).backward()
        self.assertEqual(float(hp.grad[0]), 0.)
        self.assertNotEqual(float(hp.grad[1]), 0.)
        _, auxiliary = experiment.joint_loss(logits, hp, torch.zeros(2), torch.full((2,), float('nan')))
        self.assertEqual(float(auxiliary.detach()), 0.)

    def test_actual_joint_gradients(self):
        model = experiment.initialize(np.zeros(10), np.ones(10))
        logits, hp = model.joint(distill_tests.DeepSetsDistillTests()._inputs())
        losses = experiment.joint_loss(logits, hp, torch.tensor([0., 1.]), torch.tensor([float('nan'), .8]))
        sum(losses).backward()
        for module in (model.encoder, model.head, model.hp):
            self.assertGreater(sum(float(parameter.grad.abs().sum()) for parameter in module.parameters() if parameter.grad is not None), 0.)

    def test_strict_nll_selection_ignores_brier_hp(self):
        model = experiment.JointNet(torch.nn.Linear(10, 64))
        cache = dict(split=np.array([0, 0, 1, 1]), ids=np.arange(4), win=np.array([0., 1., 0., 1.]))
        arrays = dict(y_hp=np.array([np.nan, .7, np.nan, .8], dtype=np.float32))
        values = iter([.7, .6, .6, .8, .9])
        recipe = dict(experiment.RECIPE, maxEpochs=12, batch=2)
        with tempfile.TemporaryDirectory() as directory, patch.dict(experiment.RECIPE, recipe), \
                patch.object(experiment.fit, 'inputs_for', return_value=[torch.ones(2, 10)]), \
                patch.object(experiment.fit, 'predict', return_value=np.zeros(2)), \
                patch.object(experiment.fit, 'summarize', side_effect=lambda *args: dict(nll=next(values), brier=.01)), \
                patch.object(experiment, 'hp_metrics', return_value=dict(mae=0., rmse=0.)):
            result = experiment.fit_arm(model, arrays, cache, np.array([0, 1]), np.array([2, 3]), Path(directory), 'test', 'cpu')
        self.assertEqual(result['selectedEpoch'], 2)
        self.assertEqual(result['completedEpochs'], 5)
        generator = np.random.default_rng(experiment.RECIPE['seed'])
        for entry in result['history']:
            self.assertEqual(entry['batchOrderSha256'], experiment.fit.screen.array_digest(generator.permutation(np.array([0, 1]))))


if __name__ == '__main__':
    unittest.main()
