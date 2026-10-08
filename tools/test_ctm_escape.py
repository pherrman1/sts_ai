import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

try:
    from tools import ctm_escape as e
    from tools import combat_transition_potion_trajectory as trajectory
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_escape as e
    import combat_transition_potion_trajectory as trajectory

ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
POTIONS = (1, 1, 1, 5, 12, 17, 37)


def features(folder, n=4000, seed=7):
    """Synthetic ctmescapefeatures output: escapes depend on z[0] and end at low HP."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=(n, 64)).astype('<f4')
    eligible = rng.random(n) < 0.5
    escaped = eligible & (rng.random(n) < 1 / (1 + np.exp(-(2 * z[:, 0] - 1))))
    pre = rng.integers(30, 70, n)
    post = np.where(escaped, rng.integers(1, 10, n), np.minimum(pre, 70) - rng.integers(0, 5, n)).clip(1)
    z.tofile(f'{folder}/f.f32')
    with open(f'{folder}/f.csv', 'w') as out:
        out.write('source_seed,fight_idx,supported,reason,z_row,delta_class,hp_class,pre_hp,post_max_hp,escaped,eligible,boss\n')
        for i in range(n):
            out.write(f'{i},0,1,supported,{i},0,{post[i] - pre[i] + 160},{pre[i]},80,{int(escaped[i])},{int(eligible[i])},0\n')
    return f'{folder}/f'


class TestCtmEscape(unittest.TestCase):
    def test_potion_legality_matches_the_trajectory_model(self):
        rng = np.random.default_rng(3)
        for _ in range(300):
            inventory = rng.choice(POTIONS, 5)
            capacity, boss = int(rng.integers(1, 6)), bool(rng.random() < 0.3)
            self.assertTrue(np.array_equal(e.potion_legal(inventory, capacity, boss, None),
                                           trajectory.legal_actions(tuple(inventory), capacity, boss)))
            slots = torch.as_tensor(inventory[None])
            base = torch.as_tensor(e.potion_legal(inventory, capacity, boss, None)[None])
            for escape in (0, 1):
                conditioned = trajectory.escape_condition(base, slots, np.asarray([escape]))[0].numpy()
                self.assertTrue(np.array_equal(conditioned, e.potion_legal(inventory, capacity, boss, escape)))

    def test_escape_one_always_ends_in_smoke_use(self):
        legal = e.potion_legal([37, 5, 1, 1, 1], 3, False, 1)
        self.assertFalse(legal[0])                      # stopping is illegal
        self.assertFalse(legal[1])                      # discarding the Smoke Bomb is illegal
        self.assertTrue(legal[33] and legal[2])         # use it, or clear another slot first
        self.assertFalse(e.potion_legal([37, 5, 1, 1, 1], 3, False, 0)[33])

    def test_fit_column_keeps_escape_bit_zero_identical(self):
        metadata, tensors = e.read_artifact(STANDARD)
        classes = metadata['hpClasses']
        with tempfile.TemporaryDirectory() as d:
            prefix = features(d)
            receipt = e.fit(STANDARD, prefix, Path(d) / 'fit', epochs=3)
            head = receipt['escapeHead']['TEST']
            self.assertLess(head['model']['nll'], head['constant']['nll'])
            self.assertLess(receipt['hpNll']['after']['TEST']['escaped'], receipt['hpNll']['before']['TEST']['escaped'])
            fitted = torch.load(Path(d) / 'fit' / 'escape.pt', weights_only=False)['tensors']
            self.assertEqual(fitted['hp.hp.0.weight'].shape, (64, 73))
            self.assertTrue(np.array_equal(fitted['hp.hp.0.weight'][:, :72], tensors['hp.hp.0.weight']))
            z = np.random.default_rng(1).normal(size=64)
            base = dict(tensors, **{'hp.hp.0.weight': np.concatenate((tensors['hp.hp.0.weight'], np.zeros((64, 1), np.float32)), 1)})
            self.assertTrue(np.array_equal(e.hp_probabilities(fitted, classes, z, 0, 50, 80, 0),
                                           e.hp_probabilities(base, classes, z, 0, 50, 80, 0)))
            torch_head = e.TorchEscape(fitted)
            self.assertLess(abs(torch_head.probability(z)[0] - e.escape_probability(fitted, z)), 1e-6)
            self.assertLess(np.abs(torch_head.hp_distribution(z, 0, 50, 80, 1, classes) -
                                   e.hp_probabilities(fitted, classes, z, 0, 50, 80, 1)).max(), 1e-5)
            with self.assertRaises(ValueError):
                e.fit(STANDARD, prefix, Path(d) / 'fit')

    def test_extend_requires_a_research_candidate(self):
        metadata, tensors = e.read_artifact(STANDARD)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            prefix = features(d, n=1500)
            e.fit(STANDARD, prefix, d / 'fit', epochs=1)
            with self.assertRaises(ValueError):
                e.extend(STANDARD, d / 'fit' / 'escape.pt', d / 'out.native')
            # A candidate copy differs in bytes, so the fit's base identity no longer matches either.
            candidate = d / 'candidate.native'
            e.write_artifact(candidate, dict(metadata, researchCandidate={'candidateId': 'x'}), tensors)
            with self.assertRaises(ValueError):
                e.extend(candidate, d / 'fit' / 'escape.pt', d / 'out.native')
            e.fit(candidate, prefix, d / 'fit2', epochs=1)
            result = e.extend(candidate, d / 'fit2' / 'escape.pt', d / 'out.native')
            extended, wide = e.read_artifact(d / 'out.native')
            self.assertEqual(extended['capabilities'], {'escape': {'checkpointSha256': e.sha256(d / 'fit2' / 'escape.pt')}})
            self.assertEqual(extended['supportExclusions'], ['pre_smoke_bomb_used', 'writhing_ritual_intersection'])
            self.assertEqual(extended['tensors']['hp.hp.0.weight'], [64, 73])
            self.assertEqual(extended['tensors']['escape.escape.weight'], [1, 64])
            self.assertEqual(result['artifactSha256'], e.sha256(d / 'out.native'))
            self.assertTrue(np.array_equal(wide['relic.delta.weight'], tensors['relic.delta.weight']))


if __name__ == '__main__':
    unittest.main()
