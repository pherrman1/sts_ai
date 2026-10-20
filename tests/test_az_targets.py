from pathlib import Path
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'/'heart1'))
import az_targets as az


def cand(i, prior, q, visits, tokens, kind='token'):
    return {'id': i, 'prior': prior, 'q': q, 'visits': visits, 'heart1Tokens': tokens, 'heart1Map': kind}


def decision(cands, state=3, full=True, singleton=False, tokens=4):
    return {'type': 'decision', 'searched': True, 'decisionIndex': 7, 'stateIndex': state, 'act': 2,
            'heart1Tokens': tokens, 'heart1Record': {'screen_state': 5},
            'root': {'candidates': cands, 'fullBudget': full, 'singleton': singleton, 'aborted': False,
                     'rootMeanQ': 0.5, 'selectedId': 0}}


def run(dec, killed=True):
    return [{'type': 'header', 'provenance': {'heart1WingBootsCounter': 1}},
            {'type': 'state', 'index': 3, 'supported': True, 'act': 2, 'screen': 5, 'record': {'screen_state': 5}},
            {'type': 'state', 'index': 4, 'supported': True, 'act': 2, 'screen': 5, 'record': {'screen_state': 5}},
            {'type': 'state', 'index': 5, 'supported': False, 'act': 2, 'screen': 5, 'record': {}},
            dec,
            {'type': 'outcome', 'complete': True, 'integrityPassed': True, 'heartKilled': killed}]


class ImprovedPolicy(unittest.TestCase):
    def test_beta_zero_is_the_prior(self):
        pi = az.improved_policy([2, 6], [0.9, 0.1], [5, 5], 0.5, 0.0)
        self.assertAlmostEqual(pi[0], 0.25); self.assertAlmostEqual(pi[1], 0.75)

    def test_q_shifts_mass_by_beta(self):
        pi = az.improved_policy([0.5, 0.5], [0.9, 0.1], [5, 5], 0.5, 2.0)
        self.assertAlmostEqual(pi[0] / pi[1], math.exp(2.0))

    def test_unvisited_takes_root_q_and_visit_scaling(self):
        # unvisited q 0.0 is ignored: completed Q = root 0.5, between 0.1 and 0.9
        pi = az.improved_policy([1, 1, 1], [0.9, 0.1, 0.0], [3, 1, 0], 0.5, 0.1, visit_scaled=True)
        s = (az.C_VISIT + 3) * 0.1
        self.assertAlmostEqual(pi[2] / pi[1], math.exp(0.5 * s))


class Rows(unittest.TestCase):
    def test_token_targets_mask_split_and_renormalise(self):
        root = {'candidates': [cand(0, .4, 0, 1, [0]), cand(1, .2, 0, 1, [1, 2]), cand(2, .2, 0, 1, [], 'discard_potion')]}
        logits, dropped = az.token_targets(root, [0.5, 0.3, 0.2], 4)
        self.assertAlmostEqual(dropped, 0.2)
        self.assertIsNone(logits[3])
        p = [math.exp(x) for x in logits[:3]]
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertAlmostEqual(p[1], p[2])
        self.assertAlmostEqual(p[0], 0.5 / 0.8)

    def test_one_covered_token_is_no_policy_row(self):
        root = {'candidates': [cand(0, .5, 0, 1, [0]), cand(1, .5, 0, 1, [], 'gold')]}
        self.assertIsNone(az.token_targets(root, [.5, .5], 2)[0])

    def test_convert_policy_row_replaces_its_value_row(self):
        rows, stats = az.convert_run(9, run(decision([cand(0, .5, .8, 9, [0]), cand(1, .5, .2, 3, [1])])), 2.0)
        self.assertEqual(stats['policy'], 1); self.assertEqual(stats['value'], 1)
        pol = [r for r in rows if 'logits' in r]
        self.assertEqual(len(pol), 1)
        self.assertEqual(pol[0]['z'], 1); self.assertEqual(pol[0]['wing_boots_counter'], 1)
        self.assertEqual(len(pol[0]['logits']), 4)
        self.assertGreater(pol[0]['logits'][0], pol[0]['logits'][1])
        self.assertTrue(all(r['z'] == 1 for r in rows))

    def test_stopped_or_singleton_roots_give_value_rows_only(self):
        c = [cand(0, .5, .8, 9, [0]), cand(1, .5, .2, 3, [1])]
        for d in (decision(c, full=False), decision(c, singleton=True)):
            rows, stats = az.convert_run(9, run(d, killed=False), 2.0)
            self.assertEqual(stats['policy'], 0); self.assertEqual(stats['value'], 2)
            self.assertTrue(all(r['z'] == 0 and 'logits' not in r for r in rows))

    def test_incomplete_run_is_skipped(self):
        rows = run(decision([cand(0, .5, .8, 9, [0]), cand(1, .5, .2, 3, [1])]))
        rows[-1]['integrityPassed'] = False
        self.assertEqual(az.convert_run(9, rows, 2.0), ([], {'policy': 0, 'value': 0, 'dropped_mass': 0.0,
                                                               'short': 0, 'skipped_run': 1}))

    def test_checkpoint_policy_uses_the_checkpoint(self):
        root = decision([cand(0, .5, .0, 0, [0]), cand(1, .5, .0, 0, [1])])['root']
        root['checkpoints'] = [{'simulations': 512, 'actions': [{'id': 0, 'q': .9, 'visits': 3},
                                                                {'id': 1, 'q': .1, 'visits': 1}]}]
        pi = az.checkpoint_policy(root, 512, 1.0)
        self.assertAlmostEqual(pi[0] / pi[1], math.e)
        self.assertIsNone(az.checkpoint_policy(root, 1024, 1.0))


if __name__ == '__main__':
    unittest.main()
