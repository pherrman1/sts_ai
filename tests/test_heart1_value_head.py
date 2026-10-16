"""No seeds or real corpus: mathematical fit and frozen-policy safety checks."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import torch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('train_value_head', TOOLS / 'heart1/train_value_head.py')
head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(head)


class ValueHeadTests(unittest.TestCase):
    def test_linear_fit_recovers_known_head(self):
        x = torch.tensor([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
        y = .1 + x[:, 0] * .2 + x[:, 1] * .3
        w, b = head.solve_head(x, y, torch.full((4,), .25).double(), 0.)
        torch.testing.assert_close(w, torch.tensor([[.2, .3]]))
        torch.testing.assert_close(b, torch.tensor([.1]))

    def test_regularization_does_not_penalize_bias(self):
        x = torch.tensor([[0.], [1.], [2.]])
        y = torch.full((3,), .75)
        w, b = head.solve_head(x, y, torch.full((3,), 1/3).double(), 100.)
        torch.testing.assert_close(w, torch.zeros_like(w), atol=1e-7, rtol=0)
        torch.testing.assert_close(b, torch.tensor([.75]))

    def test_source_balancing(self):
        w = head.source_weights([{'seed': 1}, {'seed': 2}, {'seed': 2}])
        torch.testing.assert_close(w, torch.tensor([.5, .25, .25]).double())

    def test_frozen_trunk_or_policy_change_is_rejected(self):
        before = {'value_head.weight': torch.zeros(1, 2), 'choice_logits.weight': torch.ones(1, 2)}
        after = {k: v.clone() for k, v in before.items()}
        after['value_head.weight'] += 1
        self.assertEqual(head.assert_frozen(before, after), ['value_head.weight'])
        after['choice_logits.weight'] += 1
        with self.assertRaisesRegex(ValueError, 'frozen tensor'):
            head.assert_frozen(before, after)

    def test_no_training_is_rejected(self):
        before = {'value_head.weight': torch.zeros(1, 2)}
        with self.assertRaises(ValueError):
            head.assert_frozen(before, before)

    def test_map_trim_keeps_input_unchanged(self):
        rec = {'obs.mapY': 2, 'obs.map.ys': [1, 2, 3], 'obs.map.xs': [0, 1, 2],
               'obs.map.roomTypes': [4, 5, 6], 'obs.map.pathXs': [7, 8, 9]}
        trimmed = head.trim_record(rec)
        self.assertEqual(trimmed['obs.map.ys'], [2, 3])
        self.assertEqual(trimmed['obs.map.pathXs'], [8, 9])
        self.assertEqual(rec['obs.map.ys'], [1, 2, 3])

    def test_load_tv_only_opens_tv_archive(self):
        # Fail closed before rows; specifically forbid accidental TEST archive access.
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'corpus-manifest.json').write_text(json.dumps({'corpus-train-validation.tar': 'tv'}))
            accessed = []
            def fake_sha(path):
                accessed.append(Path(path).name)
                if 'TEST' in Path(path).name or 'test' in Path(path).name:
                    self.fail('TEST touched')
                return head.CORPUS_MANIFEST_SHA256 if Path(path).suffix == '.json' else 'wrong'
            with patch.object(head, 'sha', side_effect=fake_sha):
                with self.assertRaisesRegex(ValueError, 'archive changed'):
                    head.load_tv(root)
            self.assertEqual(accessed, ['corpus-manifest.json', 'corpus-train-validation.tar'])

    @unittest.skipUnless(os.environ.get('STS_TEST_SILVERBOT') and os.environ.get('STS_TEST_ARM_C'),
                         'optional original silverbot dependency and pinned checkpoint')
    def test_actual_arm_c_cached_head_matches_forward_and_preserves_policy(self):
        from test_heart_rollout_distill import record
        repo = Path(os.environ['STS_TEST_SILVERBOT'])
        checkpoint = Path(os.environ['STS_TEST_ARM_C'])
        self.assertEqual(head.sha(checkpoint), head.CHECKPOINT_SHA)
        torch.set_num_threads(2)
        for device in ['cpu'] + (['cuda'] if torch.cuda.is_available() else []):
            with self.subTest(device=device):
                network, net = head.load_net(repo, checkpoint, device)
                rows = [{'record': record()}]
                features, initial, policy = head.encode(network, net, rows, device, time.monotonic()+60)
                with torch.no_grad():
                    net.value_head.weight.fill_(.0123)
                    net.value_head.bias.fill_(.45)
                cached = net.value_head(features.to(device)).squeeze(1).cpu()
                after_features, after_values, after_policy = head.encode(network, net, rows, device, time.monotonic()+60)
                self.assertEqual(policy, after_policy)
                self.assertTrue(torch.equal(features, after_features))
                torch.testing.assert_close(cached, torch.tensor(after_values), atol=1e-6, rtol=0)


if __name__ == '__main__':
    unittest.main()
