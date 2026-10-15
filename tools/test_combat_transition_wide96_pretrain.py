import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

from tools import combat_transition_wide96_pretrain as experiment
from tools import test_combat_transition_deepset_distill as fixtures


class Pretrain96Tests(unittest.TestCase):
    def make_student(self):
        return experiment.student_factory(torch, np.zeros(10), np.ones(10),
                                           11, np.arange(-200, 104), 20260912)

    def test_encoder_only_transfer_preserves_outputs_and_trains(self):
        student = self.make_student()
        with torch.no_grad():
            student.encoder.trunk[0].weight.add_(0.01)
        payload = dict(recipe=experiment.PRETRAIN_RECIPE, stateDict=student.state_dict())
        model = experiment.transfer_encoder(payload, np.zeros(10), np.ones(10))
        inputs = fixtures.DeepSetsDistillTests()._inputs()
        encoded = student.encoder(*inputs)
        self.assertEqual(tuple(encoded.shape), (2, 96))
        torch.testing.assert_close(encoded, model.encoder(*inputs), rtol=0, atol=0)
        self.assertEqual(tuple(model.head.weight.shape), (1, 96))
        self.assertFalse(any(name.startswith(('hp.', 'delta_embedding.')) for name in model.state_dict()))
        before = experiment.distill.reference.state_hash(model.encoder)
        optimizer, proof = experiment.fit.make_optimizer(model)
        _, gradients = experiment.fit.update_batch(model, optimizer, inputs, torch.tensor([0., 1.]))
        self.assertTrue(all(value > 0 for value in gradients.values()))
        self.assertNotEqual(before, experiment.distill.reference.state_hash(model.encoder))
        self.assertTrue(proof['exactParameterIds'])

    def test_copy_delta_only_and_fresh_hp_shapes(self):
        student = self.make_student()
        teacher = SimpleNamespace(hp_net=SimpleNamespace(delta_embedding=torch.nn.Embedding(11, 8)))
        delta_sha = experiment.distill.reference.state_hash(teacher.hp_net.delta_embedding)
        hp_sha = experiment.distill.reference.state_hash(student.hp)
        self.assertEqual(tuple(student.hp[0].weight.shape), (64, 104))
        self.assertEqual(tuple(student.hp[2].weight.shape), (304, 64))
        with patch.object(experiment, 'DELTA_SHA', delta_sha):
            evidence = experiment.initialize_delta(student, teacher)
        self.assertTrue(evidence['copiedDeltaOnly'])
        self.assertEqual(experiment.distill.reference.state_hash(student.hp), hp_sha)
        self.assertEqual(experiment.distill.reference.state_hash(student.delta_embedding), delta_sha)
        inputs = fixtures.DeepSetsDistillTests()._inputs()
        logits = student(inputs, torch.tensor([0, 1]), torch.tensor([30, 40]), torch.tensor([80, 80]))
        probabilities = logits.softmax(-1)
        self.assertEqual(tuple(logits.shape), (2, 304))
        self.assertTrue(torch.isfinite(probabilities).all())
        torch.testing.assert_close(probabilities.sum(-1), torch.ones(2))
        self.assertEqual(float(probabilities[0, :171].sum()), 0.)
        loss = experiment.distill.reference.torch_kl(probabilities.detach(), logits)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()

    def test_transfer_rejects_wrong_shape_recipe_or_normalization(self):
        student = self.make_student()
        payload = dict(recipe=experiment.PRETRAIN_RECIPE, stateDict=student.state_dict())
        wrong = copy.deepcopy(payload)
        wrong['stateDict']['encoder.trunk.0.weight'] = torch.zeros(128, 256)
        with self.assertRaises(RuntimeError):
            experiment.transfer_encoder(wrong, np.zeros(10), np.ones(10))
        with self.assertRaises(ValueError):
            experiment.transfer_encoder(payload, np.ones(10), np.ones(10))
        with self.assertRaises(ValueError):
            experiment.transfer_encoder(dict(payload, recipe={}), np.zeros(10), np.ones(10))

    def test_fixed_recipes_and_deterministic_initialization(self):
        self.assertEqual(experiment.distill.reference.state_hash(self.make_student()),
                         experiment.distill.reference.state_hash(self.make_student()))
        for key in ('epochs', 'batch', 'encoderLr', 'headLr', 'weightDecay', 'selection', 'loss', 'trainingPrecision'):
            self.assertEqual(experiment.PRETRAIN_RECIPE[key], experiment.distill.RECIPE[key])
        for key in ('maxEpochs', 'minEpochs', 'patience', 'batch', 'encoderLr', 'headLr', 'weightDecay', 'selection', 'loss'):
            self.assertEqual(experiment.SURVIVAL_RECIPE[key], experiment.wide.RECIPE[key])

    def test_deterministic_pretraining_then_survival_loss_decreases(self):
        torch.set_num_threads(1)
        student = self.make_student()
        teacher = SimpleNamespace(hp_net=SimpleNamespace(delta_embedding=torch.nn.Embedding(11, 8)))
        with patch.object(experiment, 'DELTA_SHA', experiment.distill.reference.state_hash(teacher.hp_net.delta_embedding)):
            experiment.initialize_delta(student, teacher)
        max_head = torch.nn.Linear(96, 11)
        inputs = fixtures.DeepSetsDistillTests()._inputs()
        delta, pre, maximum = torch.tensor([0, 1]), torch.tensor([30, 40]), torch.tensor([80, 80])
        teacher_max = torch.zeros(2, 11)
        teacher_max[:, 0] = 1.
        teacher_hp = torch.zeros(2, 304)
        teacher_hp[:, 200] = 1.
        optimizer = torch.optim.AdamW([
            dict(params=student.encoder.parameters(), lr=1e-4),
            dict(params=list(student.delta_embedding.parameters()) + list(student.hp.parameters()) + list(max_head.parameters()), lr=1e-3),
        ], weight_decay=1e-4)
        losses = []
        for step in range(12):
            optimizer.zero_grad(set_to_none=True)
            max_logits = max_head(student.encoder(*inputs))
            hp_logits = student(inputs, delta, pre, maximum)
            self.assertEqual(tuple(max_logits.shape), (2, 11))
            self.assertEqual(tuple(hp_logits.shape), (2, 304))
            loss = .5 * (experiment.distill.reference.torch_kl(teacher_max, max_logits)
                         + experiment.distill.reference.torch_kl(teacher_hp, hp_logits))
            self.assertTrue(torch.isfinite(loss))
            losses.append(float(loss.detach()))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(student.parameters()) + list(max_head.parameters()), 1.)
            optimizer.step()
        self.assertLess(losses[-1], losses[0])
        model = experiment.transfer_encoder(dict(recipe=experiment.PRETRAIN_RECIPE,
            stateDict=student.state_dict()), np.zeros(10), np.ones(10))
        torch.testing.assert_close(student.encoder(*inputs), model.encoder(*inputs), rtol=0, atol=0)
        optimizer, _ = experiment.fit.make_optimizer(model)
        for group in optimizer.param_groups:
            group['weight_decay'] = 1e-3
        losses = []
        for step in range(12):
            loss, _ = experiment.fit.update_batch(model, optimizer, inputs, torch.tensor([0., 1.]))
            losses.append(loss)
        self.assertLess(losses[-1], losses[0])
        self.assertEqual(tuple(model(inputs).shape), (2,))
        self.assertEqual(tuple(model.head.weight.shape), (1, 96))


if __name__ == '__main__':
    unittest.main()
