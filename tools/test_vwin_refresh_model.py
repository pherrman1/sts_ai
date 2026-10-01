"""Synthetic end-to-end coverage of tuning/freeze/TEST custody; never real TEST."""
import json
import contextlib
import io
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import vwin_refresh_model as pipeline
from tools import vwin_refresh_training as training
from tools.vwin_refresh_dataset import source_split


class SyntheticDataset:
    feature_names = ('curHp', 'maxHp', 'gold', 'potionCount', 'pot1')

    def preflight(self, features):
        return {'selected_feature_names': list(self.feature_names)}

    def read(self, split, kind='MAP', allow_test=False):
        if split == 'TEST' and not allow_test:
            raise ValueError('TEST blocked')
        seeds = [s for s in range(200) if source_split(s) == split][:6]
        rng = np.random.default_rng(42)
        hp = rng.integers(1, 8, 60)
        held = rng.integers(0, 2, 60)
        X = np.column_stack([hp, np.full(60, 8), rng.integers(0, 99, 60), held, held]).astype('float32')
        rows = [dict(sourceSeed=seeds[i % len(seeds)], branchId='source',
                     rowIdx=i, act=i % 3 + 1, actBoss=0, postAfterBattleHp=int(hp[i])) for i in range(60)]
        return X, (hp > 4).astype('float32'), rows

    def branches(self, split, allow_test=False):
        return []


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.b0 = self.root / 'b0.txt'
        self.b0.write_text('feat curHp\nlogistic 1\nbase_score 0.5\ntree 0 3\nS 0 4 1 2\nL -0.2\nL 0.2\n')

    def test_b0_projects_names_not_positions(self):
        b = pipeline.Baseline(self.b0)
        np.testing.assert_array_equal(b.predict([[999, 2], [-999, 6]], ['gold','curHp']),
                                      b.predict([[2], [6]], ['curHp']))
        with self.assertRaises(ValueError):
            b.predict([[2]], ['gold'])

    def test_unfrozen_test_fails_before_corpus_access(self):
        with patch.object(pipeline, 'validated_dataset') as access:
            with self.assertRaises(FileNotFoundError):
                pipeline.open_test(self.root, 'OPEN_REAL_TEST_ONCE')
            with self.assertRaises(ValueError):
                pipeline.open_test(self.root, 'yes')
            access.assert_not_called()

    def test_exclusive_output(self):
        pipeline.write_json(self.root / 'one.json', {'x': 1})
        with self.assertRaises(FileExistsError):
            pipeline.write_json(self.root / 'one.json', {'x': 2})

    def test_cli_requires_explicit_training_and_test_confirmation(self):
        cases = [
            ['tune', 'index', '--output', 'run'],
            ['open-test', 'run'],
            ['open-test', 'run', '--confirm', 'yes'],
        ]
        with patch.object(pipeline, 'validated_dataset') as access:
            for args in cases:
                with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        pipeline.main(args)
            access.assert_not_called()

    def test_synthetic_complete_lifecycle_and_tampering(self):
        dataset = SyntheticDataset()
        index = self.root / 'index.json'
        index.write_text('{}')
        run = self.root / 'run'
        original_xgb, original_fixed, original_mlp = training.train_xgb, training.train_xgb_fixed, training.train_mlp
        def small_xgb(*args, **kwargs):
            return original_xgb(*args, **kwargs, grid=[dict(max_depth=2,eta=.1,min_child_weight=1)], max_rounds=3, patience=2)
        def small_fixed(*args, **kwargs):
            # train_xgb itself supplies its synthetic bounds.
            kwargs.setdefault('max_rounds', 3); kwargs.setdefault('patience', 2)
            return original_fixed(*args, **kwargs)
        def small_mlp(*args, **kwargs):
            return original_mlp(*args, **kwargs, recipes=[dict(lr=.001,weight_decay=.0001,dropout=0.)], max_epochs=2, patience=1, batch_size=32)
        with patch.object(pipeline, 'validated_dataset', return_value=dataset), \
             patch.object(pipeline, 'B0', self.b0), \
             patch.object(training, 'train_xgb', side_effect=small_xgb), \
             patch.object(training, 'train_xgb_fixed', side_effect=small_fixed), \
             patch.object(training, 'train_mlp', side_effect=small_mlp):
            pipeline.tune(index, run)
            self.assertFalse((run / 'freeze.json').exists())
            self.assertFalse((run / 'test-opened.json').exists())
            tuning_path = run / 'tuning.json'
            original_tuning = tuning_path.read_text()
            for key, value in [('selection_split', 'TEST'), ('test_predictions_opened', True),
                               ('complete_arms', ['X1', 'X2'])]:
                altered = json.loads(original_tuning)
                altered[key] = value
                tuning_path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(ValueError, 'completed validation-selected'):
                    pipeline.freeze(run)
            tuning_path.write_text(original_tuning)
            pipeline.freeze(run)
            pipeline.verify_freeze(run)
            target = run / 'X1/predictor.json'
            original = target.read_text()
            target.write_text(original + '\n')
            with self.assertRaisesRegex(ValueError, 'artifacts changed'):
                pipeline.verify_freeze(run)
            target.write_text(original)
            with patch.object(pipeline, 'tool_identity', return_value={'files': {}}):
                with self.assertRaisesRegex(ValueError, 'tooling changed'):
                    pipeline.verify_freeze(run)
            # A failed prediction still consumes the latch; only synthetic copies
            # are used here to exercise both success and failure independently.
            failed_run = self.root / 'failed-run'
            shutil.copytree(run, failed_run)
            with patch.object(pipeline.Baseline, 'predict', side_effect=RuntimeError('synthetic failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                    pipeline.open_test(failed_run, 'OPEN_REAL_TEST_ONCE')
            with self.assertRaisesRegex(ValueError, 'already opened'):
                pipeline.open_test(failed_run, 'OPEN_REAL_TEST_ONCE')
            result = pipeline.open_test(run, 'OPEN_REAL_TEST_ONCE')
            self.assertEqual(set(result['arms']), {'B0','X1','X2','M1'})
            self.assertFalse(result['terminal_pricing_ready'])
            with self.assertRaisesRegex(ValueError, 'already opened'):
                pipeline.open_test(run, 'OPEN_REAL_TEST_ONCE')


if __name__ == '__main__':
    unittest.main()
