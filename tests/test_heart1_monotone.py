from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'heart1'))
import monotone as mo
import torch

EMPTY, CURSES = 1, [70, 133]


def batch():
    """collate_fn-shaped tensors for 4 rows: hp/mhp/gold, 3 potion slots, a 5-slot deck, deck misc."""
    fo = torch.tensor([[50, 80, 100, 3], [80, 80, 0, 3], [1, 80, 1790, 3], [0, 200, 10, 3]], dtype=torch.int32)
    pv = torch.tensor([[1, 4, 1], [1, 1, 1], [21, 0, 0], [6, 1, 0]], dtype=torch.int32)
    pm = torch.tensor([[0, 0, 0], [0, 0, 0], [0, 1, 1], [0, 0, 1]], dtype=torch.bool)
    dv = torch.zeros(4, 5, 2, dtype=torch.int32); dm = torch.ones(4, 5, dtype=torch.bool)
    for i, n in enumerate((2, 5, 0, 3)):
        dv[i, :n, 0] = 321; dm[i, :n] = False
    return {'fixed_obs': {'fixed_observation': fo, 'boss': torch.zeros(4)},
            'potions': {'value': pv, 'mask': pm}, 'deck': {'value': dv, 'mask': dm},
            'extra': {'deck_misc': torch.full((4, 5, 1), 7.0), 'act': torch.zeros(4)}, 'choices': {}}


def clone(b):
    if isinstance(b, dict): return {k: clone(v) for k, v in b.items()}
    return b.clone()


def same(x, y):
    if isinstance(x, dict): return all(same(x[k], y[k]) for k in x)
    return torch.equal(x, y)


class MonotoneTest(unittest.TestCase):
    def test_fixed_rules(self):
        b = batch(); orig = clone(b)
        c, s = mo.perturb(b, 'hp', EMPTY, CURSES, fixed=True)
        self.assertEqual(s.tolist(), [-1, -1, 0, 0])
        self.assertEqual(c['fixed_obs']['fixed_observation'][:, 0].tolist(), [47, 77, 1, 0])
        c, s = mo.perturb(b, 'mhp', EMPTY, CURSES, fixed=True)
        self.assertEqual(s.tolist(), [1, 1, 1, 0])
        self.assertEqual(c['fixed_obs']['fixed_observation'][:, 1].tolist(), [85, 85, 85, 200])
        c, s = mo.perturb(b, 'gold', EMPTY, CURSES, fixed=True)
        self.assertEqual(s.tolist(), [1, 1, 0, 1])
        self.assertEqual(c['fixed_obs']['fixed_observation'][:, 2].tolist(), [150, 50, 1790, 60])
        c, s = mo.perturb(b, 'potion', EMPTY, CURSES, fixed=True)
        self.assertEqual(s.tolist(), [-1, 0, -1, -1])
        self.assertEqual(c['potions']['value'].tolist(), [[1, 1, 1], [1, 1, 1], [1, 0, 0], [1, 1, 0]])
        c, s = mo.perturb(b, 'curse', EMPTY, CURSES, fixed=True)
        self.assertEqual(s.tolist(), [-1, 0, -1, -1])
        self.assertEqual((~c['deck']['mask']).sum(-1).tolist(), [3, 5, 1, 4])
        self.assertEqual(c['deck']['value'][0, 2].tolist(), [70, 0])
        self.assertEqual(c['deck']['value'][2, 0].tolist(), [70, 0])
        self.assertEqual(c['extra']['deck_misc'][0, :, 0].tolist(), [7, 7, 0, 7, 7])
        self.assertTrue(same(b, orig))  # copies never write into the source batch

    def test_random_rules_stay_valid(self):
        g = torch.Generator().manual_seed(0)
        for _ in range(200):
            b = batch()
            c, s = mo.perturb(b, 'hp', EMPTY, CURSES, g)
            hp = c['fixed_obs']['fixed_observation'][:, 0]; d = hp - b['fixed_obs']['fixed_observation'][:, 0]
            self.assertEqual(s.tolist(), [1, -1, 1, 0])
            self.assertTrue(((hp >= 1) | (s == 0)).all() and (hp <= 80).all())
            self.assertTrue((d.sign() == s).all() and (d.abs() <= 10).all())
            c, s = mo.perturb(b, 'gold', EMPTY, CURSES, g)
            self.assertTrue((c['fixed_obs']['fixed_observation'][:, 2] <= mo.GOLD_CAP).all())
            c, s = mo.perturb(b, 'curse', EMPTY, CURSES, g)
            self.assertTrue(set(c['deck']['value'][0, 2, 0:1].tolist()) <= set(CURSES))

    def test_mixed_changes_one_rule_per_row(self):
        g = torch.Generator().manual_seed(1)
        for _ in range(100):
            b = batch(); c, s = mo.perturb_mixed(b, list(mo.RULES), EMPTY, CURSES, g)
            for i in range(4):
                changed = [not torch.equal(c['fixed_obs']['fixed_observation'][i, j], b['fixed_obs']['fixed_observation'][i, j])
                           for j in range(3)]
                changed += [not torch.equal(c['potions']['value'][i], b['potions']['value'][i]),
                            not torch.equal(c['deck']['mask'][i], b['deck']['mask'][i])]
                self.assertEqual(sum(changed), 1 if s[i] != 0 else 0)
            self.assertNotEqual(s[0].item(), 0)

    def test_penalty_and_violations(self):
        v = torch.tensor([0.0, 1.0, 2.0, 3.0]); vc = torch.tensor([1.0, 0.5, 2.0, 9.0]); s = torch.tensor([1, 1, -1, 0])
        # row 0: copy better and higher -> 0; row 1: copy better but lower -> 0.5; row 2 tie -> 0; row 3 ignored
        self.assertAlmostEqual(mo.penalty(v, vc, s).item(), 0.5 / 3)
        self.assertEqual(mo.violations(v, vc, s).tolist(), [1.0, -0.5, 0.0])

    def test_penalty_fixes_a_wrong_sign_value(self):
        """A value linear in (hp, mhp, gold) that starts with a negative max-HP weight learns a non-negative one."""
        w = torch.tensor([0.02, -0.03, 0.001], requires_grad=True)
        opt = torch.optim.SGD([w], lr=1e-4); g = torch.Generator().manual_seed(2)
        val = lambda b: b['fixed_obs']['fixed_observation'][:, :3].float() @ w
        for _ in range(300):
            b = batch(); c, s = mo.perturb_mixed(b, ['hp', 'mhp', 'gold'], EMPTY, CURSES, g)
            loss = mo.penalty(val(b), val(c), s); opt.zero_grad(); loss.backward(); opt.step()
        self.assertGreaterEqual(w[1].item(), -1e-3)
        self.assertGreater(w[0].item(), 0)


if __name__ == '__main__':
    unittest.main()
