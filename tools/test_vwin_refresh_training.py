"""Tiny synthetic CPU checks only; never opens the real corpus."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from tools import vwin_refresh_training as training


class TrainingTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(731)
        self.X = rng.normal(size=(96, 3)).astype(np.float32)
        self.y = (self.X[:, 1] + .3 * self.X[:, 0] > 0).astype(np.float32)
        self.names = ('gold', 'curHp', 'maxHp')
        self.args = (self.X[:64], self.y[:64], self.X[64:], self.y[64:], self.names)

    def test_grids_are_bounded_and_exact(self):
        self.assertEqual(len(training.XGB_GRID), 12)
        self.assertEqual(len(training.MLP_RECIPES), 12)
        self.assertEqual({x['max_depth'] for x in training.XGB_GRID}, {4, 6, 8})
        self.assertEqual({x['lr'] for x in training.MLP_RECIPES}, {1e-3, 3e-4, 1e-4})

    def test_runtime_fingerprint_cpu_is_stable_without_gpu(self):
        with mock.patch('torch.cuda.is_available', side_effect=AssertionError('GPU queried')):
            with mock.patch('torch.cuda.device_count', side_effect=AssertionError('GPU queried')):
                first = training.runtime_fingerprint()
                self.assertEqual(first, training.runtime_fingerprint('cpu'))
        self.assertEqual(json.loads(json.dumps(first)), first)
        self.assertTrue(first['python']['version'])
        self.assertTrue(first['python']['implementation'])
        for library in ('numpy', 'xgboost', 'torch'):
            self.assertTrue(first[library])
        self.assertIsNone(first['cuda'])
        self.assertEqual(first['prediction_device'], 'cpu')
        with mock.patch.object(training.np, '__version__', 'changed-version'):
            self.assertNotEqual(first, training.runtime_fingerprint())

    def test_runtime_fingerprint_cuda_configured_before_gpu_queries(self):
        def available():
            self.assertEqual(os.environ['CUBLAS_WORKSPACE_CONFIG'], ':4096:8')
            return True
        props = SimpleNamespace(name='Synthetic GPU', major=9, minor=0,
                                total_memory=1024, multi_processor_count=2)
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch('torch.cuda.is_initialized', return_value=False), \
                mock.patch('torch.cuda.is_available', side_effect=available), \
                mock.patch('torch.cuda.get_device_properties', return_value=props) as get_props, \
                mock.patch('torch.version.cuda', '12.test'), \
                mock.patch('torch.backends.cudnn.version', return_value=999):
            fingerprint = training.runtime_fingerprint('cuda:1')
            get_props.assert_called_once_with(1)
        self.assertEqual(fingerprint['cuda']['gpu']['name'], 'Synthetic GPU')
        self.assertEqual(fingerprint['cuda']['version'], '12.test')
        self.assertEqual(fingerprint['cuda']['cudnn'], 999)
        self.assertEqual(fingerprint['training_device'], 'cuda:1')
        self.assertEqual(fingerprint['prediction_device'], 'cpu')
        self.assertEqual(json.loads(json.dumps(fingerprint)), fingerprint)
        with mock.patch.dict(os.environ, {'CUBLAS_WORKSPACE_CONFIG': ':4096:8'}), \
                mock.patch('torch.cuda.is_available', return_value=False):
            with self.assertRaisesRegex(ValueError, 'available GPU'):
                training.runtime_fingerprint('cuda')

    def test_xgb_constraint_attaches_only_curhp(self):
        p = training.xgb_parameters(self.names, monotone=True)
        self.assertEqual(p['monotone_constraints'], '(0,1,0)')
        self.assertNotIn('monotone_constraints', training.xgb_parameters(self.names))
        with self.assertRaisesRegex(ValueError, 'requires curHp'):
            training.xgb_parameters(('gold',), monotone=True)

    def test_xgb_deterministic_projection_and_roundtrip(self):
        kwargs = dict(grid=[dict(max_depth=2, eta=.3, min_child_weight=1)],
                      max_rounds=12, patience=3)
        first, report = training.train_xgb(*self.args, **kwargs)
        second, _ = training.train_xgb(*self.args, **kwargs)
        np.testing.assert_array_equal(first.predict(self.X), second.predict(self.X))
        self.assertGreater(np.ptp(first.predict(self.X)), .1)
        np.testing.assert_array_equal(first.predict(self.X),
                                      first.predict(self.X[:, ::-1], self.names[::-1]))
        self.assertEqual(report['selected']['tree_count'], len(first.booster.get_dump()))
        # Learning curve uses the selected full parameter dict, without retuning.
        half, half_report = training.train_xgb_fixed(
            self.X[:32], self.y[:32], self.X[64:], self.y[64:], self.names,
            params=report['selected']['params'], max_rounds=12, patience=3)
        self.assertEqual(half_report['params'], report['selected']['params'])
        self.assertEqual(half.predict(self.X).shape, (96,))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model'
            first.save(path)
            np.testing.assert_array_equal(first.predict(self.X), training.load_predictor(path).predict(self.X))
            with self.assertRaises(FileExistsError):
                first.save(path)

    def test_x2_smoke_monotone(self):
        predictor, report = training.train_xgb(
            *self.args, monotone=True,
            grid=[dict(max_depth=2, eta=.3, min_child_weight=1)],
            max_rounds=12, patience=3)
        sweep = np.zeros((100, 3), dtype=np.float32)
        sweep[:, 1] = np.linspace(-3, 3, 100)
        self.assertTrue((np.diff(predictor.predict(sweep)) >= 0).all())
        self.assertEqual(report['arm'], 'X2')

    def test_train_only_normalization(self):
        mean, std = training.train_normalization(self.X[:64])
        np.testing.assert_allclose(mean, self.X[:64].astype(np.float64).mean(0))
        np.testing.assert_allclose(std, self.X[:64].astype(np.float64).std(0))
        self.assertFalse(np.allclose(mean, self.X.mean(0)))
        _, constant_std = training.train_normalization(np.ones((2, 3)))
        np.testing.assert_array_equal(constant_std, [1, 1, 1])

    def test_mlp_cpu_deterministic_normalization_and_roundtrip(self):
        kwargs = dict(recipes=[dict(lr=1e-3, weight_decay=1e-4, dropout=.1)],
                      max_epochs=3, patience=2, batch_size=32)
        first, report = training.train_mlp(*self.args, **kwargs)
        second, _ = training.train_mlp(*self.args, **kwargs)
        np.testing.assert_array_equal(first.predict(self.X), second.predict(self.X))
        np.testing.assert_array_equal(first.mean, training.train_normalization(self.X[:64])[0])
        self.assertEqual([r['seed'] for r in report['retrains']], [0, 1, 2])
        self.assertEqual(report['selected']['validation_nll'],
                         min(r['validation_nll'] for r in report['retrains']))
        np.testing.assert_array_equal(first.predict(self.X),
                                      first.predict(self.X[:, ::-1], self.names[::-1]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model'
            first.save(path)
            np.testing.assert_array_equal(first.predict(self.X), training.load_predictor(path).predict(self.X))
            meta = json.loads((path / 'predictor.json').read_text())
            self.assertEqual(meta['mean_hash'], report['normalization']['mean_hash'])
            np.savez(path / 'normalization.npz', mean=first.mean + 1, std=first.std)
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                training.load_predictor(path)

    def test_cuda_determinism_configuration_without_gpu(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch('torch.cuda.is_initialized', return_value=False):
                training._configure_cuda_determinism('cuda:0')
            self.assertEqual(os.environ['CUBLAS_WORKSPACE_CONFIG'], ':4096:8')
        with mock.patch.dict(os.environ, {'CUBLAS_WORKSPACE_CONFIG': 'bad'}):
            with self.assertRaisesRegex(ValueError, 'unsupported CUBLAS'):
                training._configure_cuda_determinism('cuda')
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch('torch.cuda.is_initialized', return_value=True):
                with self.assertRaisesRegex(ValueError, 'before CUDA initialization'):
                    training._configure_cuda_determinism('cuda')
        with mock.patch.dict(os.environ, {'CUBLAS_WORKSPACE_CONFIG': ':16:8'}):
            training._configure_cuda_determinism('cuda')
            self.assertEqual(os.environ['CUBLAS_WORKSPACE_CONFIG'], ':16:8')
        with mock.patch.dict(os.environ, {}, clear=True):
            training._configure_cuda_determinism('cpu')
            self.assertNotIn('CUBLAS_WORKSPACE_CONFIG', os.environ)

    def test_bad_inputs_fail(self):
        with self.assertRaisesRegex(ValueError, 'binary'):
            training.train_xgb(self.X[:64], np.full(64, .5), *self.args[2:])
        with self.assertRaisesRegex(ValueError, '1..12'):
            training.train_xgb(*self.args, grid=[])
        with self.assertRaisesRegex(ValueError, 'seeds 0,1,2'):
            training.train_mlp(*self.args, seeds=(0,))


if __name__ == '__main__':
    unittest.main()
