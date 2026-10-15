import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch

from tools import combat_transition_survival_wide96 as experiment
from tools import test_combat_transition_deepset_distill as fixtures


class Wide96Tests(unittest.TestCase):
    def test_shapes_gradients_and_initialization(self):
        model = experiment.build_model(np.zeros(10), np.ones(10))
        same = experiment.build_model(np.zeros(10), np.ones(10))
        self.assertEqual(experiment.fit.screen.state_digest(model.state_dict()),
                         experiment.fit.screen.state_digest(same.state_dict()))
        for name in ('card_mlp', 'relic_mlp', 'potion_mlp'):
            self.assertEqual(getattr(model.encoder, name)[0].out_features, 96)
            self.assertEqual(getattr(model.encoder, name)[2].out_features, 96)
        self.assertEqual(model.encoder.global_mlp[0].out_features, 96)
        self.assertEqual(model.encoder.trunk[0].weight.shape, (192, 384))
        self.assertEqual(model.encoder.trunk[2].weight.shape, (96, 192))
        self.assertEqual(model.head.weight.shape, (1, 96))
        self.assertEqual([model.encoder.card_id.embedding_dim, model.encoder.relic_id.embedding_dim,
                          model.encoder.potion_id.embedding_dim, model.encoder.potion_slot.embedding_dim], [48, 48, 32, 8])
        inputs = fixtures.DeepSetsDistillTests()._inputs()
        self.assertEqual(model(inputs).shape, (2,))
        optimizer, _ = experiment.fit.make_optimizer(model)
        _, gradients = experiment.fit.update_batch(model, optimizer, inputs, torch.tensor([0., 1.]))
        self.assertTrue(all(value > 0 for value in gradients.values()))

    def test_normalization_train_only_and_constant_features(self):
        arrays = dict(globals_continuous=np.array([[0., 2.], [8., 2.], [1000., 1000.]], dtype=np.float32))
        cache = dict(ids=np.arange(3), split=np.array([0, 0, 1]))
        mean, std = experiment.normalization(arrays, cache, np.array([0, 1]))
        np.testing.assert_array_equal(mean, [4., 2.])
        np.testing.assert_array_equal(std, [4., 0.])
        with self.assertRaises(ValueError):
            experiment.normalization(arrays, cache, np.array([0, 1, 2]))

    def test_selection_optimizer_and_checkpoint(self):
        model = experiment.build_model(np.zeros(10), np.ones(10))
        values = iter([.7, .6] + [.6] * 10)
        cache = dict(win=np.array([0., 1., 0., 1.]))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(experiment.fit, 'inputs_for', return_value=fixtures.DeepSetsDistillTests()._inputs()), \
                patch.object(experiment.fit, 'predict', return_value=np.zeros(2)), \
                patch.object(experiment.fit, 'summarize', side_effect=lambda *args: dict(nll=next(values), brier=.1)):
            result = experiment.train_model(model, {}, cache, np.array([0, 1]), np.array([2, 3]), Path(directory), 'test', 'cpu')
            payload = torch.load(Path(directory) / 'selected.pt', weights_only=False)
            self.assertEqual(payload['recipe'], experiment.RECIPE)
        self.assertEqual(result['selectedEpoch'], 2)
        self.assertEqual(result['completedEpochs'], 12)
        self.assertEqual([record['weightDecay'] for record in result['optimizerScope']['groups']], [1e-3, 1e-3])
        self.assertEqual([record['lr'] for record in result['optimizerScope']['groups']], [1e-4, 1e-3])
        generator = np.random.default_rng(20260912)
        for entry in result['history']:
            self.assertEqual(entry['batchOrderSha256'], experiment.fit.screen.array_digest(generator.permutation(np.array([0, 1]))))


if __name__ == '__main__':
    unittest.main()
