import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch

from tools import combat_transition_survival_mlp_head as experiment
from tools import test_combat_transition_deepset_distill as fixtures


class MlpHeadTests(unittest.TestCase):
    def test_only_head_is_trainable(self):
        encoder = experiment.mlp.fit.screen.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10), np.ones(10)).net
        model = experiment.freeze_encoder(experiment.mlp.replace_head(experiment.fit.SurvivalNet(encoder)))
        optimizer, proof = experiment.head_optimizer(model)
        optimizer.zero_grad(set_to_none=True)
        logits = model(fixtures.DeepSetsDistillTests()._inputs())
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            logits, torch.tensor([0., 1.])
        )
        loss.backward()
        head_gradients = [parameter.grad for parameter in model.head.parameters()]
        self.assertTrue(all(gradient is not None and torch.isfinite(gradient).all() and gradient.abs().sum() > 0
                            for gradient in head_gradients))
        self.assertTrue(all(parameter.grad is None for parameter in model.encoder.parameters()))
        before = experiment.mlp.fit.screen.state_digest(model.encoder.state_dict())
        optimizer.step()
        self.assertEqual(before, experiment.mlp.fit.screen.state_digest(model.encoder.state_dict()))
        self.assertTrue(proof['frozenEncoder'])

    def test_training_preserves_encoder_and_selects_nll(self):
        encoder = experiment.mlp.fit.screen.surrogate.DeepSetsEncoder(torch.nn, torch, np.zeros(10), np.ones(10)).net
        model = experiment.freeze_encoder(experiment.mlp.replace_head(experiment.fit.SurvivalNet(encoder)))
        initial = experiment.mlp.fit.screen.state_digest(encoder.state_dict())
        values = iter([.7, .6] + [.6] * 10)
        cache = dict(win=np.array([0., 1., 0., 1.]))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(experiment.fit, 'inputs_for', return_value=fixtures.DeepSetsDistillTests()._inputs()), \
                patch.object(experiment.fit, 'predict', return_value=np.zeros(2)), \
                patch.object(experiment.fit, 'summarize', side_effect=lambda *args: dict(nll=next(values), brier=.1)):
            result = experiment.train(model, {}, cache, np.array([0, 1]), np.array([2, 3]), Path(directory), 'test', 'cpu')
        self.assertEqual(initial, result['encoderStateSha256'])
        self.assertEqual(result['selectedEpoch'], 2)
        self.assertEqual(result['completedEpochs'], 12)
        self.assertEqual(result['optimizerScope']['parameters'], 4225)


if __name__ == '__main__':
    unittest.main()
