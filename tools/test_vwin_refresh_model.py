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
from tools.vwin_refresh_dataset import source_split, CorpusBinding, DEFAULT_CORPUS_BINDING


class SyntheticDataset:
    feature_names = ('curHp', 'maxHp', 'gold', 'potionCount', 'pot1')

    def __init__(self, binding=DEFAULT_CORPUS_BINDING):
        self.binding = binding

    def preflight(self, features):
        return {'selected_feature_names': list(self.feature_names),
                'corpus_binding': self.binding.to_dict(),
                'corpus_index_sha256': self.binding.index_sha256,
                'split_counts': dict(self.binding.split_counts)}

    def read(self, split, kind='MAP', allow_test=False, row_limit=None):
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

    def test_native_parity_fixture_is_lf_only(self):
        names = ['curHp'] + [f'feature{i}' for i in range(1016)]
        X = np.zeros((2, 1017), dtype=np.float32)
        X[:, 0] = [2, 6]
        expected = pipeline.Baseline(self.b0).predict(X, names)
        def run(command, **kwargs):
            raw = Path(command[3]).read_bytes()
            self.assertNotIn(b'\r', raw)
            self.assertEqual(raw.count(b'\n'), 3)
            return type('Result', (), {'stdout': '\n'.join(
                f'{i},{p}' for i, p in enumerate(expected))})()
        with patch.object(pipeline.subprocess, 'run', side_effect=run):
            result = pipeline.native_parity(X, names, self.b0, model=self.b0)
        self.assertEqual(result['max_abs_error'], 0.)

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

    def test_cli_binding_requires_strict_paired_inputs(self):
        for command in ('preflight', 'tune'):
            base = [command, 'index', '--output', 'output']
            if command == 'tune':
                base += ['--authorize-full-training']
            invalid = [
                ['--expected-index-sha', 'a' * 64],
                ['--expected-split-counts', '696,155,173'],
                ['--expected-index-sha', 'z' * 64, '--expected-split-counts', '696,155,173'],
                ['--expected-index-sha', 'a' * 63, '--expected-split-counts', '696,155,173'],
            ]
            invalid += [['--expected-index-sha', 'a' * 64, '--expected-split-counts', counts]
                        for counts in ('1,2', '1,2,3,4', '0,2,3', '-1,2,3', '1.0,2,3', 'True,2,3', '1, 2,3')]
            with patch.object(pipeline, command) as action:
                for flags in invalid:
                    with self.subTest(command=command, flags=flags), contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit):
                            pipeline.main(base + flags)
                action.assert_not_called()
            with patch.object(pipeline, command, return_value={}) as action, contextlib.redirect_stdout(io.StringIO()):
                pipeline.main(base)
                self.assertEqual(action.call_args.kwargs['binding'], DEFAULT_CORPUS_BINDING)
                pipeline.main(base + ['--expected-index-sha', 'A' * 64,
                                      '--expected-split-counts', '696,155,173'])
                self.assertEqual(action.call_args.kwargs['binding'].to_dict(),
                                 {'index_sha256': 'a' * 64, 'split_counts': {'TRAIN': 696, 'VALIDATION': 155, 'TEST': 173}})

    def test_preflight_propagates_binding_without_predictions(self):
        binding = CorpusBinding('a' * 64, {'TRAIN': 696, 'VALIDATION': 155, 'TEST': 173})
        output = self.root / 'preflight.json'
        with patch.object(pipeline, 'validated_dataset', return_value=SyntheticDataset(binding)) as access, \
             patch.object(pipeline, 'B0', self.b0), \
             patch.object(pipeline.Baseline, 'predict', side_effect=AssertionError('no predictions')):
            report = pipeline.preflight('synthetic-index', output, binding=binding)
        access.assert_called_once_with('synthetic-index', binding=binding)
        self.assertEqual(report['corpus_binding'], binding.to_dict())
        self.assertFalse(report['real_test_predictions_opened'])
        self.assertFalse(report['full_candidate_training_run'])
        self.assertEqual(json.loads(output.read_text())['corpus_binding'], binding.to_dict())

    def test_bounded_smoke_qualifies_path_but_cannot_freeze(self):
        index = self.root / 'index.json'
        index.write_text('{}')
        run = self.root / 'smoke'
        original_sha = pipeline.sha256
        with patch.object(pipeline, 'sha256', side_effect=lambda p: DEFAULT_CORPUS_BINDING.index_sha256 if Path(p) == index else original_sha(p)), \
             patch.object(pipeline, 'validated_dataset', return_value=SyntheticDataset()), \
             patch.object(pipeline, 'B0', self.b0):
            report = pipeline.validation_smoke(index, run)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['purpose'], 'smoke_only')
        self.assertEqual(set(report['arms']), {'B0', 'X1', 'X2', 'M1'})
        self.assertTrue(all(set(arm) == {'MAP', 'WIN_RAW'} for arm in report['arms'].values()))
        self.assertFalse((run / 'test-opened.json').exists())
        with self.assertRaisesRegex(ValueError, 'completed validation-selected'):
            pipeline.freeze(run)

    def test_synthetic_complete_lifecycle_and_tampering(self):
        self.complete_lifecycle(DEFAULT_CORPUS_BINDING)

    def test_explicit_1024_complete_lifecycle_and_tampering(self):
        self.complete_lifecycle(CorpusBinding('a' * 64, {'TRAIN': 696, 'VALIDATION': 155, 'TEST': 173}))

    def complete_lifecycle(self, binding):
        dataset = SyntheticDataset(binding)
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
        original_sha = pipeline.sha256
        with patch.object(pipeline, 'sha256', side_effect=lambda p: binding.index_sha256 if Path(p) == index else original_sha(p)), \
             patch.object(pipeline, 'validated_dataset', return_value=dataset) as corpus_access, \
             patch.object(pipeline, 'B0', self.b0), \
             patch.object(training, 'train_xgb', side_effect=small_xgb), \
             patch.object(training, 'train_xgb_fixed', side_effect=small_fixed), \
             patch.object(training, 'train_mlp', side_effect=small_mlp):
            kwargs = {} if binding == DEFAULT_CORPUS_BINDING else {'binding': binding}
            pipeline.tune(index, run, **kwargs)
            corpus_access.assert_called_with(index, binding=binding)
            for name in ('preflight.json', 'tuning.json', 'validation-resources.json'):
                self.assertEqual(json.loads((run / name).read_text())['corpus_binding'], binding.to_dict())
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
            qualification = run / 'validation-resources.json'
            original_qualification = qualification.read_text()
            qualification.unlink()
            with self.assertRaises(FileNotFoundError):
                pipeline.freeze(run)
            # Standalone qualification must reload the exact saved binding.
            pipeline.qualify_validation(run)
            corpus_access.assert_called_with(str(index.resolve()), binding=binding)
            qualification.unlink()
            altered = json.loads(original_tuning)
            altered['corpus_binding']['split_counts']['TRAIN'] += 1
            tuning_path.write_text(json.dumps(altered))
            with patch.object(pipeline, 'validated_dataset') as access:
                with self.assertRaisesRegex(ValueError, 'binding disagrees'):
                    pipeline.qualify_validation(run)
                access.assert_not_called()
            tuning_path.write_text(original_tuning)
            # Failure is recorded but does not burn TEST or create a qualification.
            with patch.object(pipeline, 'resource_evaluation', side_effect=ValueError('real-state-edge')):
                with self.assertRaisesRegex(ValueError, 'real-state-edge'):
                    pipeline.qualify_validation(run, data=dataset)
            self.assertFalse(qualification.exists())
            self.assertTrue(list(run.glob('validation-resources.failed-*.json')))
            self.assertFalse((run / 'test-opened.json').exists())
            for key, value in [('status', 'failed'), ('purpose', 'smoke_only'), ('split', 'TEST')]:
                changed = json.loads(original_qualification)
                changed[key] = value
                qualification.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'resource qualification required'):
                    pipeline.freeze(run)
            changed = json.loads(original_qualification)
            del changed['arms']['M1']['WIN_RAW']
            qualification.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'incomplete VALIDATION'):
                pipeline.freeze(run)
            changed = json.loads(original_qualification)
            changed['corpus_binding']['split_counts']['TRAIN'] += 1
            qualification.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'corpus binding mismatch'):
                pipeline.freeze(run)
            qualification.unlink()
            wrong_data = SyntheticDataset(CorpusBinding('b' * 64, dict(binding.split_counts)))
            with self.assertRaisesRegex(ValueError, 'dataset corpus binding mismatch'):
                pipeline.qualify_validation(run, data=wrong_data)
            qualification.write_text(original_qualification)
            checkpoint = run / 'X1/predictor.json'
            original_checkpoint = checkpoint.read_text()
            checkpoint.write_text(original_checkpoint + '\n')
            with self.assertRaisesRegex(ValueError, 'qualification identity mismatch'):
                pipeline.freeze(run)
            checkpoint.write_text(original_checkpoint)
            changed_tooling = dict(pipeline.tool_identity(), git_sha='0' * 40)
            with patch.object(pipeline, 'tool_identity', return_value=changed_tooling):
                with self.assertRaisesRegex(ValueError, 'tooling changed since tuning'):
                    pipeline.freeze(run)
            changed_runtime = dict(training.runtime_fingerprint(), numpy='different')
            with patch.object(training, 'runtime_fingerprint', return_value=changed_runtime):
                with self.assertRaisesRegex(ValueError, 'runtime changed since tuning'):
                    pipeline.freeze(run)
            frozen = pipeline.freeze(run)
            self.assertEqual(frozen['corpus_binding'], binding.to_dict())
            pipeline.verify_freeze(run)
            # Every persisted binding is mandatory and must agree before corpus access.
            for filename in ('preflight.json', 'tuning.json', 'validation-resources.json', 'freeze.json'):
                target_binding = run / filename
                saved_binding = target_binding.read_text()
                for mutation in ('missing', 'sha', 'counts'):
                    altered = json.loads(saved_binding)
                    if mutation == 'missing':
                        del altered['corpus_binding']
                    elif mutation == 'sha':
                        altered['corpus_binding']['index_sha256'] = 'b' * 64
                    else:
                        altered['corpus_binding']['split_counts']['TRAIN'] += 1
                    target_binding.write_text(json.dumps(altered))
                    with patch.object(pipeline, 'validated_dataset') as access:
                        with self.assertRaises(ValueError):
                            pipeline.open_test(run, 'OPEN_REAL_TEST_ONCE')
                        access.assert_not_called()
                    self.assertFalse((run / 'test-opened.json').exists())
                target_binding.write_text(saved_binding)
            target = run / 'X1/predictor.json'
            original = target.read_text()
            target.write_text(original + '\n')
            with self.assertRaisesRegex(ValueError, 'artifacts changed'):
                pipeline.verify_freeze(run)
            target.write_text(original)
            with patch.object(pipeline, 'tool_identity', return_value={'files': {}}):
                with self.assertRaisesRegex(ValueError, 'tooling changed'):
                    pipeline.verify_freeze(run)
            for dependency, value, message in [
                    ('tool_identity', changed_tooling, 'frozen tooling changed'),
                    ('runtime_fingerprint', changed_runtime, 'frozen runtime changed')]:
                module = pipeline if dependency == 'tool_identity' else training
                with patch.object(module, dependency, return_value=value), \
                     patch.object(pipeline, 'validated_dataset') as access:
                    with self.assertRaisesRegex(ValueError, message):
                        pipeline.open_test(run, 'OPEN_REAL_TEST_ONCE')
                    access.assert_not_called()
                    self.assertFalse((run / 'test-opened.json').exists())
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
            corpus_access.assert_called_with(str(index.resolve()), binding=binding)
            self.assertEqual(result['corpus_binding'], binding.to_dict())
            self.assertEqual(json.loads((run / 'test-opened.json').read_text())['corpus_binding'], binding.to_dict())
            self.assertEqual(set(result['arms']), {'B0','X1','X2','M1'})
            self.assertFalse(result['terminal_pricing_ready'])
            with self.assertRaisesRegex(ValueError, 'already opened'):
                pipeline.open_test(run, 'OPEN_REAL_TEST_ONCE')


if __name__ == '__main__':
    unittest.main()
