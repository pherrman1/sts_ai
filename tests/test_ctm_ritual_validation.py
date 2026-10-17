"""Actual-artifact diagnostic boundaries; no experiment/model fit is run."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import ctm_ritual_validation as diagnostic


class RitualValidationTest(unittest.TestCase):
    def test_artifact_encoding_contract_moves_tensors_to_host_before_numpy(self):
        # Emulate CUDA's refusal of implicit NumPy conversion without needing
        # a CUDA device in this unit test. The explicit host transfer is valid.
        class DeviceTensor:
            def __init__(self, value): self.value = value
            def __array__(self, *args): raise AssertionError('implicit CUDA conversion')
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return self.value
        enc = [{'z': DeviceTensor(np.full((1,64), i, np.float32)),
                'potion_z': DeviceTensor(np.full((1,64), i+1, np.float32)),
                'p_delta': np.full((1,11), 1/11)} for i in range(2)]
        z, zp, pd = diagnostic.encoding_batch(enc)
        self.assertEqual(z.shape, (2,64)); self.assertEqual(pd.shape, (2,11))
        np.testing.assert_array_equal(zp-z, np.ones((2,64)))

    def test_nonselected_json_payload_is_never_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rows.jsonl'
            # Deliberately invalid JSON represents protected/nonselected labels.
            path.write_bytes(b'{"index": 0, THIS_IS_NOT_JSON_TEST_POISON\n'
                             b'{"index": 1, "pre": {"selected": true}}\n'
                             b'{"index": 2, ALSO_INVALID_TEST_POISON\n')
            real = json.loads
            def decode(raw):
                self.assertNotIn(b'POISON', raw)
                return real(raw)
            with patch.object(diagnostic.json, 'loads', side_effect=decode):
                records = diagnostic.read_records(path, {1}, 3)
            self.assertEqual(records, {1: {'index': 1, 'pre': {'selected': True}}})

    def test_missing_or_reordered_record_indices_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rows.jsonl'; path.write_bytes(b'{"index": 0, "x": 1}\n')
            with self.assertRaisesRegex(ValueError, 'missing'): diagnostic.read_records(path, {1}, 3)
            path.write_bytes(b'{"index": 1, "x": 1}\n{"index": 0, "x": 1}\n')
            with self.assertRaisesRegex(ValueError, 'order'): diagnostic.read_records(path, {1}, 3)

    def test_initial_brew_dispatch_respects_capacity_and_not_sampled_generation(self):
        self.assertEqual(diagnostic.route({'potions': [9, 1, 8], 'potionCapacity': 2}, 9), 'standard')
        self.assertEqual(diagnostic.route({'potions': [1, 1, 9], 'potionCapacity': 2}, 9), 'fast')
        self.assertEqual(diagnostic.route({'potions': [1, 8, 1], 'potionCapacity': 2}, 9), 'fast')

    def test_active_tail_exclusion_preserves_mark_bloom_boundary(self):
        relic_ids = {'LIZARD_TAIL': 5, 'MARK_OF_THE_BLOOM': 6}
        record = {'pre': {'smokeBombUsed': False, 'relics': [{'id': 5, 'data': 1}]}}
        self.assertEqual(diagnostic.exclusions(record, relic_ids), ['active_tail_requires_composed_correction'])
        record['pre']['relics'].append({'id': 6, 'data': 0})
        self.assertEqual(diagnostic.exclusions(record, relic_ids), [])
        record['pre']['smokeBombUsed'] = True
        self.assertEqual(diagnostic.exclusions(record, relic_ids), ['pre_smoke_used'])

    def test_target_absent_from_native_support_is_zero_without_smoothing(self):
        self.assertEqual(diagnostic.target_mass([(0,), (3,)], np.array([.1, .9]), (7,)), 0.)
        self.assertEqual(diagnostic.target_mass([(0,), (3,)], np.array([.1, .9]), (3,)), .9)

    def test_zero_masses_are_reported_and_not_bootstrapped_as_finite(self):
        bootstrap = Mock(side_effect=AssertionError('nonfinite bootstrap forbidden'))
        result, _, _, gap = diagnostic.summary(np.array([.5, 0.]), np.array([0., 0.]), np.array([1, 2]), bootstrap)
        self.assertEqual(result['zeroTeacherMassRows'], 1)
        self.assertEqual(result['zeroMixtureMassRows'], 2)
        self.assertFalse(result['finiteGap']); self.assertIsNone(result['meanGap'])
        self.assertFalse(result['qualified']); self.assertTrue(np.isinf(gap[0])); self.assertTrue(np.isnan(gap[1]))
        bootstrap.assert_not_called()

    def test_gap_is_difference_of_log_mixture_not_average_log_probability(self):
        teacher, mixture = np.array([.5, .25]), np.array([.25, .25])
        bootstrap = Mock(return_value={'rows': 2})
        result, _, _, gap = diagnostic.summary(teacher, mixture, np.array([7, 8]), bootstrap)
        np.testing.assert_allclose(gap, [np.log(2), 0])
        self.assertAlmostEqual(result['meanGap'], np.log(2)/2)
        self.assertEqual(result['sourceBootstrap'], {'rows': 2})

    def test_teacher_posterior_uses_current_artifact_net_and_explicit_escape_bit(self):
        import torch
        graph = SimpleNamespace(inventories=np.array([[5, 1, 1, 1, 1]]))
        t = SimpleNamespace(brew=SimpleNamespace(draw_native=Mock(side_effect=AssertionError('no generation'))),
            target_graph=Mock(return_value=graph), log_probabilities=Mock(return_value=torch.log(torch.tensor([[.25, .75]]))),
            target_log_probability=Mock(return_value=torch.tensor(0.)),
            trace_posterior=Mock(return_value=(np.array([.2, .8]+[0.]*254), 1.)), EFFECT_IDS=(20, 21, 22))
        artifact = SimpleNamespace(potion_net=object(), escape=SimpleNamespace(eligible=lambda *_: True))
        pre = {'combatRng': [None]*4+[{'counter': 4}], 'potions': [5, 1, 1, 1, 1], 'potionCapacity': 3}
        post = {'combatRng': [None]*4+[{'counter': 4}], 'smokeBombUsed': False, 'curHp': 42, 'maxHp': 80}
        options = diagnostic.teacher_options(artifact, {'potion_z': np.zeros(64)}, {'pre': pre, 'post': post}, 2, False, t)
        self.assertEqual([weight for _, weight in options], [.2, .8])
        args = t.log_probabilities.call_args.args
        self.assertIs(args[0], artifact.potion_net)
        np.testing.assert_array_equal(args[-1], [0])
        np.testing.assert_array_equal(args[4], [2])
        self.assertEqual(options[1][0]['initialMask'], 1)
        # A structural zero never reaches posterior normalization.
        t.target_log_probability.return_value = torch.tensor(-torch.inf); t.trace_posterior.reset_mock()
        self.assertEqual(diagnostic.teacher_options(artifact, {'potion_z': np.zeros(64)}, {'pre': pre, 'post': post}, 2, False, t), [])
        t.trace_posterior.assert_not_called()


if __name__ == '__main__': unittest.main()
