"""Synthetic nonlinear-head checks; no game seeds or research corpus access."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import torch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path[:0] = [str(TOOLS / 'heart1'), str(TOOLS)]
import train_nonlinear_value as nonlinear


class NonlinearValueTests(unittest.TestCase):
    def test_architecture_is_small_and_standardization_train_only(self):
        x = torch.arange(8*64).reshape(8, 64).float()
        model = nonlinear.ValueHead(x)
        self.assertEqual(sum(p.numel() for p in model.parameters()), 4225)
        torch.testing.assert_close(model.mean, x.mean(0))
        torch.testing.assert_close(model.scale, x.std(0, unbiased=False))
        before = {k: v.clone() for k, v in model.state_dict().items()}
        model(torch.full((2, 64), 1e5))
        for key, value in before.items():
            self.assertTrue(torch.equal(value, model.state_dict()[key]))

    def test_zero_variance_features_remain_finite(self):
        x = torch.ones(4, 64)
        self.assertTrue(torch.isfinite(nonlinear.ValueHead(x)(x)).all())

    def test_only_full_train_prefix_can_be_selected_by_protocol(self):
        self.assertEqual(nonlinear.SIZES, (10, 20, 40))
        self.assertEqual(nonlinear.INITS, (0, 1))

    def test_cache_tampering_refuses_before_tensor_load(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'result.json').write_text('{}')
            (root / 'freeze.json').write_text('{}')
            with patch.object(torch, 'load', side_effect=AssertionError('must not load')) as load:
                with self.assertRaisesRegex(ValueError, 'audited affine fit'):
                    nonlinear.check_parent(root, root / 'checkpoint.pt')
            load.assert_not_called()

    def test_raw_mse_is_source_balanced(self):
        rows = [{'seed': 1}, {'seed': 2}, {'seed': 2}]
        weights = nonlinear.linear.source_weights(rows)
        result = nonlinear.raw_mse(torch.tensor([1., 0., 0.]), torch.zeros(3), weights)
        self.assertEqual(result, .5)

    def test_small_fit_learns_and_best_checkpoint_is_retained(self):
        torch.set_num_threads(2)
        torch.manual_seed(8)
        x = torch.randn(64, 64)
        target = .3 + .2 * torch.relu(x[:, 0])
        rows = [{'seed': 1 + i % 2} for i in range(len(x))]
        weights = nonlinear.linear.source_weights(rows)
        best, logs = nonlinear.fit_one(x, target, rows, x, target.double(), weights, 0,
                                       time.monotonic()+20, steps=100, evaluate_every=10)
        self.assertEqual(best['validationRawMse'], min(r['validationRawMse'] for r in logs))
        self.assertLess(best['validationRawMse'], .001)
        model = nonlinear.ValueHead(x)
        model.load_state_dict(best['state'])
        actual = nonlinear.raw_mse(model(x), target.double(), weights)
        self.assertEqual(actual, best['validationRawMse'])

    def test_expired_budget_refuses_training(self):
        x = torch.zeros(2, 64)
        rows = [{'seed': 1}, {'seed': 1}]
        with self.assertRaises(TimeoutError):
            nonlinear.fit_one(x, torch.ones(2), rows, x, torch.ones(2).double(),
                torch.ones(2).double() / 2, 0, time.monotonic()-1, steps=1)


if __name__ == '__main__':
    unittest.main()
