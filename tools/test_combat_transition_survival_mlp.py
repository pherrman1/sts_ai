import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch

from tools import combat_transition_survival_mlp as experiment
from tools import test_combat_transition_deepset_distill as fixtures


class MlpTests(unittest.TestCase):
    def test_head_only_replacement_and_joint_gradients(self):
        encoder = experiment.fit.screen.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10), np.ones(10)).net
        model = experiment.fit.SurvivalNet(encoder)
        before = experiment.fit.screen.state_digest(encoder.state_dict())
        experiment.replace_head(model)
        self.assertEqual(before, experiment.fit.screen.state_digest(encoder.state_dict()))
        self.assertEqual(sum(parameter.numel() for parameter in model.head.parameters()), 4225)
        optimizer, proof = experiment.fit.make_optimizer(model)
        _, gradients = experiment.fit.update_batch(model, optimizer, fixtures.DeepSetsDistillTests()._inputs(), torch.tensor([0., 1.]))
        self.assertTrue(all(value > 0 for value in gradients.values()))
        self.assertEqual([record['lr'] for record in proof['groups']], [1e-4, 1e-3])

    def test_mlp_schema_loads_and_forward_passes(self):
        encoder = experiment.fit.screen.surrogate.DeepSetsEncoder(
            torch.nn, torch, np.zeros(10), np.ones(10)
        ).net
        model = experiment.replace_head(experiment.fit.SurvivalNet(encoder))
        state = model.state_dict()
        for key in ('head.0.weight', 'head.0.bias', 'head.2.weight', 'head.2.bias'):
            self.assertIn(key, state)
        reloaded = experiment.replace_head(experiment.fit.SurvivalNet(encoder))
        reloaded.load_state_dict(state, strict=True)
        logits = reloaded(fixtures.DeepSetsDistillTests()._inputs())
        self.assertEqual(tuple(logits.shape), (2,))
        self.assertTrue(torch.isfinite(logits).all())

    def test_selection_floor_patience_and_decay(self):
        model = experiment.replace_head(experiment.fit.SurvivalNet(torch.nn.Linear(10, 64)))
        cache = dict(win=np.array([0., 1., 0., 1.]))
        values = iter([.7, .6] + [.6] * 10)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(experiment.fit, 'inputs_for', return_value=[torch.ones(2, 10)]), \
                patch.object(experiment.fit, 'predict', return_value=np.zeros(2)), \
                patch.object(experiment.fit, 'summarize', side_effect=lambda *args: dict(nll=next(values), brier=.1)):
            result = experiment.train(model, {}, cache, np.array([0, 1]), np.array([2, 3]), Path(directory), 'test', 'cpu')
        self.assertEqual(result['selectedEpoch'], 2)
        self.assertEqual(result['completedEpochs'], 12)
        self.assertEqual([item['weightDecay'] for item in result['optimizerScope']['groups']], [1e-3, 1e-3])
        generator = np.random.default_rng(20260912)
        for entry in result['history']:
            self.assertEqual(entry['batchOrderSha256'], experiment.fit.screen.array_digest(generator.permutation(np.array([0, 1]))))


if __name__ == '__main__':
    unittest.main()
