"""Synthetic encoder/model contract tests; no corpus reads or fitting."""
import copy
from dataclasses import fields
import unittest
import numpy as np
from tools.screen_leaf_model_379 import (encode_state, parse_option, pack_encoded, cached_batch,
    collate_encoded, fit_train_normalization, build_model, verify_feature_names, PROVISIONAL_MASK, canonical_shop_options)

BASE = np.zeros(461, dtype=np.float32)

def public_base(contents):
    result = BASE.copy()
    if contents['screen'] == 'shop':
        result[10] = sum(p not in (0, 1) for p in contents['ownedPotions'])
        result[11] = contents['ownedPotionCapacity']
    return result

def key(effect, source, target='none'):
    return f'ooc:v1:effect={effect}:source={source}:{target}'

def option(k):
    row, _ = parse_option(k)
    return {'key': k, 'effect': row[0], 'source': row[1]}

def shop():
    k = key(23, 3, 'shop=relic,12:price=77:occurrence=0')
    c = {'screen': 'shop', 'screenState': 8,
         'cards': [{'slot': i, 'id': None, 'price': -1, 'card': None} for i in range(7)],
         'relics': [{'slot': i, 'id': None, 'price': -1} for i in range(3)],
         'potionSlots': [{'slot': i, 'id': None, 'price': -1} for i in range(3)],
         'removeCost': 100, 'policyBuyableRelics': [{'id': 12, 'price': 77, 'key': k}],
         'ownedPotionCapacity': 3, 'ownedPotions': [1, 2, 3]}
    c['cards'][2] = {'slot': 2, 'id': 15, 'price': 41, 'card': {'id': 15, 'misc': 7, 'upgraded': True}}
    c['relics'][1] = {'slot': 1, 'id': 12, 'price': 77}
    return c, [k, key(25, 3)]

def reward(groups):
    return {'screen': 'rewards', 'screenState': 2, 'gold': [7, 8], 'relics': [11, 12],
            'potions': [3], 'emeraldKey': False, 'sapphireKey': True,
            'cardRewards': [{'group': i, 'cards': [{'id': n, 'misc': 0, 'upgraded': False} for n in g]}
                            for i, g in enumerate(groups)]}

class EncoderTests(unittest.TestCase):
    def test_public_permutation_exact(self):
        c, keys = shop(); a = encode_state(public_base(c), c, keys)
        for name in ('cards', 'relics', 'potionSlots', 'policyBuyableRelics', 'ownedPotions'):
            c[name].reverse()
        b = encode_state(public_base(c), c, keys[::-1])
        for f in fields(a):
            np.testing.assert_array_equal(getattr(a, f.name), getattr(b, f.name))

    def test_groups_not_flattened(self):
        a = encode_state(BASE, reward([[1, 2], [3, 4]]), [])
        b = encode_state(BASE, reward([[1, 3], [2, 4]]), [])
        self.assertFalse(np.array_equal(a.groups, b.groups))
        c = reward([[4, 3], [2, 1]])
        d = encode_state(public_base(c), c, [])
        np.testing.assert_array_equal(a.groups, d.groups)

    def test_grouped_candidate_is_typed(self):
        k = key(5, 7, 'reward=card,1,0,0:group=[2,0,1;1,0,0;]:groupOccurrence=0:occurrence=0:sapphirePaired=0')
        action, group = parse_option(k)
        self.assertEqual(group, ((1, 0, 0), (2, 0, 1)))
        self.assertEqual(action[3:7], (1, 1, 0, 0))

    def test_shop_remove_transaction(self):
        k = 'ooc:v1:effect=1:source=4:transaction:event=0:option=-1:cost=75:card=104:misc=0:upgraded=0:bottle=-1:occurrence=0'
        row, group = parse_option(k)
        self.assertEqual(row, (1, 4, 5, 1, 104, 0, 0, -1, 0, 75, 0, 0, 0, -1))
        self.assertEqual(group, ())
        c, keys = shop(); c['removeCost'] = 75
        a = encode_state(public_base(c), c, keys + [k])
        self.assertEqual(a.actions.shape[1], 14)

    def test_shop_fields_and_slots_preserved(self):
        c, keys = shop(); a = encode_state(public_base(c), c, keys)
        for mutate in (lambda v: v.update(removeCost=101),
                       lambda v: v['cards'][2]['card'].update(misc=8),
                       lambda v: v['ownedPotions'].__setitem__(0, 4)):
            d = copy.deepcopy(c); mutate(d); b = encode_state(public_base(d), d, keys)
            self.assertTrue(any(not np.array_equal(getattr(a, f.name), getattr(b, f.name)) for f in fields(a)))
        d = copy.deepcopy(c); d['cards'][2]['slot'], d['cards'][3]['slot'] = 3, 2
        self.assertFalse(np.array_equal(a.entities, encode_state(public_base(d), d, keys).entities))

    def test_input_allowlist_and_incomplete_reject(self):
        c, keys = shop()
        for bad_field in ('won', 'chosenKey', 'sourceSeed', 'branchId', 'rng', 'futureOutcome'):
            d = copy.deepcopy(c); d[bad_field] = 1
            with self.assertRaises(ValueError): encode_state(public_base(d), d, keys)
        with self.assertRaises(ValueError): encode_state(public_base(c), c, keys + [keys[0]])
        with self.assertRaises(ValueError): encode_state(public_base(c), c, keys[1:])
        with self.assertRaises(ValueError): encode_state(public_base(c), c, [key(26, 5, 'event=1:option=0')])
        with self.assertRaises(ValueError): encode_state(public_base(c), c, [keys[0] + ':won=1'])
        with self.assertRaises(ValueError): verify_feature_names(['won'] * 461)

    def test_shop_discard_historical_current_canonicalization(self):
        c, keys = shop(); c['ownedPotions'] = [3, 3, 4]
        c['potionSlots'][0] = {'slot': 0, 'id': 5, 'price': 10}
        base = public_base(c); base[4] = 10
        augmented = canonical_shop_options(base, c, keys)
        self.assertEqual(len(augmented), len(keys) + 3)
        a = encode_state(base, c, keys); b = encode_state(base, c, augmented[::-1])
        for f in fields(a): np.testing.assert_array_equal(getattr(a, f.name), getattr(b, f.name))
        with self.assertRaises(ValueError): encode_state(base, c, keys + [next(k for k in augmented if 'effect=29:' in k)])
        bad = augmented + [key(29, 3, 'reward=potion,9:group=[]:groupOccurrence=0:occurrence=0:sapphirePaired=0')]
        with self.assertRaises(ValueError): encode_state(base, c, bad)
        for mutate in (lambda b: b.__setitem__(322, 1), lambda b: b.__setitem__(4, 9)):
            other = base.copy(); mutate(other)
            self.assertEqual(canonical_shop_options(other, c, keys), sorted(keys))
            with self.assertRaises(ValueError): encode_state(other, c, augmented)
        c['ownedPotions'][0] = 1; other = public_base(c); other[4] = 10
        self.assertEqual(canonical_shop_options(other, c, keys), sorted(keys))

    def test_train_only_normalization(self):
        x = np.stack([BASE, np.ones(461, dtype=np.float32) * 2])
        n = fit_train_normalization(x, split='TRAIN')
        np.testing.assert_array_equal(n['mean'], np.ones(461))
        np.testing.assert_array_equal(n['scale'], np.ones(461))
        with self.assertRaises(ValueError): fit_train_normalization(x, split='VALIDATION')
        with self.assertRaises(ValueError): fit_train_normalization(x, split='TEST')

    def test_model_contract_and_matching_encoder(self):
        import torch
        torch.set_num_threads(1)
        c, keys = shop()
        states = [encode_state(public_base(c), c, keys),
                  encode_state(BASE, {'screen': 'boss_relic', 'screenState': 3, 'relics': [11, 12]},
                               [key(27, 9, 'relic=11:occurrence=0'), key(28, 9)]),
                  encode_state(BASE, {'screen': 'rest', 'screenState': 7, 'availableOptions': []}, []),
                  encode_state(BASE, {'screen': 'treasure', 'screenState': 6, 'chestSize': 1,
                                     'availableOptions': [option(key(15, 8))]}, [key(15, 8)])]
        cache = pack_encoded(states); b = cached_batch(cache, [0, 1, 2, 3])
        again = collate_encoded(states)
        for name in b: self.assertTrue(torch.equal(b[name], again[name]), name)
        norm = fit_train_normalization(np.stack([s.base for s in states]), split='TRAIN')
        torch.manual_seed(0); s1 = build_model('S1', norm).eval()
        torch.manual_seed(0); s2 = build_model('S2', norm).eval()
        for name, value in s1.state_dict().items():
            if not name.startswith('head.'):
                self.assertTrue(torch.equal(value, s2.state_dict()[name]), name)
        self.assertEqual(s1.head.out_features, len(PROVISIONAL_MASK))
        self.assertEqual(s2.head.out_features, 1)
        for model in (s1, s2):
            logits = model(b)
            self.assertEqual(tuple(logits.shape), (4,))
            self.assertTrue(torch.isfinite(logits).all())
            logits.sum().backward()
            self.assertIsNotNone(model.card_encoder[0].weight.grad)
        with self.assertRaises(ValueError):
            s1(collate_encoded([encode_state(BASE, reward([]), [])]))

if __name__ == '__main__':
    unittest.main()
