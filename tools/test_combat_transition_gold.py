import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import importlib.util
import unittest
import numpy as np
from tools import combat_transition_gold as g


def fixture(card, upgraded=False):
    pre = dict(gold=100, stolenGold=45, relics=[], potions=[1]*5)
    pi = dict(globals=dict(encounter=g.b._ENCOUNTER_IDS['CULTIST'], ascension=0),
              cards=[dict(cardId=g.b._CARD_IDS[card], upgraded=upgraded)])
    return pi, pre


class NativeGoldTest(unittest.TestCase):
    def test_exact_payout_and_pre_stolen_reset(self):
        self.assertEqual(g.native_posts(100, 'CULTIST', 0, 1), ((100, 0), (120, 0)))
        self.assertEqual(g.native_posts(100, 'CULTIST', 0, 2), ((100, 0), (125, 0)))
        self.assertEqual(g.native_posts(100, 'CULTIST', 0, 0), ((100, 0),))

    def test_thief_order_clipping_and_escape(self):
        self.assertEqual(g.native_posts(100, 'LOOTER', 0, 0),
                         ((55, 0), (55, 45), (70, 0), (70, 30), (85, 15), (100, 0)))
        posts = g.native_posts(17, 'TWO_THIEVES', 0, 0)
        self.assertIn((0, 2), posts)
        self.assertIn((0, 15), posts)
        self.assertNotIn((0, 1), posts)
        self.assertNotIn((85, 0), g.native_posts(100, 'LOOTER', 0, 0))

    def test_gold_gain_can_precede_clipped_theft(self):
        posts = g.native_posts(0, 'TWO_THIEVES', 0, 3)
        # Kill one thief with HoG: +20; surviving thief steals 15 then 5.
        self.assertIn((0, 20), posts)
        self.assertIn((40, 0), posts)
        self.assertNotIn((75, 0), posts)  # only two qualifying kills

    def test_native_ascension_and_split_kill_caps(self):
        self.assertIn((60, 40), g.native_posts(100, 'LOOTER', 17, 0))
        self.assertIn((100, 0), g.native_posts(0, 'SLIME_BOSS', 0, 2))
        self.assertNotIn((125, 0), g.native_posts(0, 'SLIME_BOSS', 0, 2))
        self.assertEqual(g.native_posts(0, 'GREMLIN_LEADER', 0, 2), ((0, 0), (25, 0)))
        self.assertEqual(g.native_posts(0, 'THREE_DARKLINGS', 0, 3), ((0, 0),))

    def test_upgrade_shared_feature_and_recursive_colorless_pool(self):
        pi, pre = fixture('TRANSMUTATION')
        mode, ordinary = g.mechanics(pi, pre, 0)
        pi['cards'][0]['upgraded'] = True
        upgraded_mode, upgraded = g.mechanics(pi, pre, 0)
        self.assertEqual((mode, upgraded_mode), (3, 3))
        self.assertEqual(ordinary[g.MECHANICAL_FIELDS.index('transmutation')], upgraded[g.MECHANICAL_FIELDS.index('transmutation')])
        self.assertEqual(upgraded[g.MECHANICAL_FIELDS.index('upgradedHogSource')], 1)
        hog, _ = fixture('HAND_OF_GREED', True)
        _, explicit_up = g.mechanics(hog, pre, 0)
        self.assertEqual(explicit_up[g.MECHANICAL_FIELDS.index('upgradedHogSource')], 1)

    def test_potion_condition_ectoplasm_and_input_purity(self):
        pi, pre = fixture('STRIKE_RED')
        pre['potions'][2] = g.b._POTION_IDS['COLORLESS_POTION']
        saved = copy.deepcopy((pi, pre))
        self.assertEqual(g.posts_for_input(pi, pre, 0), ((100, 0),))
        self.assertIn((125, 0), g.posts_for_input(pi, pre, 4))
        self.assertEqual((pi, pre), saved)
        pre['relics'].append(dict(id=g.b._RELIC_IDS['ECTOPLASM']))
        self.assertEqual(g.posts_for_input(pi, pre, 4), ((100, 0),))

    def test_malformed_domain_rejected(self):
        for gold in (-1, True, 40000):
            with self.assertRaises(ValueError):
                g.native_posts(gold, 'LOOTER', 0, 0)

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'optional torch')
    def test_shared_decoder_normalizes_masks_and_freezes_encoder(self):
        import torch
        decoder = g.new_decoder(torch)
        z = torch.zeros(2, 64, requires_grad=True)
        candidates = torch.zeros(2, 3, len(g.CANDIDATE_FIELDS))
        legal = torch.tensor([[True, True, False], [True, False, False]])
        logp = decoder(z, torch.zeros(2, len(g.MECHANICAL_FIELDS)), torch.zeros(2, 3), torch.zeros(2, 5), candidates, legal)
        self.assertTrue(torch.allclose(logp.exp().sum(-1), torch.ones(2)))
        self.assertEqual(logp[0, 2].exp().item(), 0)
        (-logp[:, 0].sum()).backward()
        self.assertIsNone(z.grad)
        self.assertTrue(any(p.grad is not None for p in decoder.parameters()))


if __name__ == '__main__':
    unittest.main()
