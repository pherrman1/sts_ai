"""tools/az_bench/amber_net.py input fixes of the pipeline audit 2026-11-24 (selfplay.py --intent-emb and
--select-many-bits): the plain net cannot tell a monster's current from its previous move (ids[1] / ids[2] summed in
one table) and the new table fixes that; the zero-initialised table leaves every forward layout bit-identical; the
SELECT_MANY mask is read as bits, and mask_bits_from_raw reproduces the raw-mask net; checkpoints with the new
weights load into a plain AmberNet; selfplay.load_opt_state does not hand a later group the moments of a group with
other shapes."""

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy as np
    import torch
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


def load(name, *path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class InputFixes(unittest.TestCase):
    def setUp(self):
        self.A = load("amber_net", "tools", "az_bench", "amber_net.py")
        torch.manual_seed(0)
        self.net = self.A.jitter_1d_params(self.A.AmberNet(64, 2).eval())

    def batch(self, seed):
        A = self.A
        b = A.synthetic_batch(16, live_frac=0.6, rng=np.random.default_rng(seed))
        rng = np.random.default_rng(seed + 100)
        ids = b["monster_ids"]
        ids[..., 1] = torch.from_numpy(rng.integers(600, 700, ids.shape[:-1]))   # two different move ids
        ids[..., 2] = torch.from_numpy(rng.integers(700, 800, ids.shape[:-1]))
        ids[..., 3] = torch.from_numpy(rng.integers(0, 900, ids.shape[:-1]))      # no encounter tokens
        sm = torch.from_numpy(rng.random(b["a_type"].shape) < 0.4)
        b["a_type"] = torch.where(sm, torch.full_like(b["a_type"], A.SELECT_MANY), b["a_type"] % A.SELECT_MANY)
        mask = torch.from_numpy(rng.integers(1, 1024, b["a_type"].shape).astype(np.float32))
        b["a_f"][..., A.MASK_SLOT] = torch.where(sm, mask, b["a_f"][..., A.MASK_SLOT])
        return b

    def layouts(self, b):
        A = self.A
        f = A.to_flat(b)
        pk = A.pack_index(f["mask"], 1)
        M = f["mask"].numel()
        ip = pk.clamp(max=M - 1)
        packed_tok = dict(f, pack_idx=pk, tok_type=f["tok_type"].reshape(M)[ip].clone(),
                          ids=f["ids"].reshape(M, -1)[ip].clone(), f=f["f"].reshape(M, -1)[ip].clone())
        return (("segments", b), ("flat", f), ("packed", dict(f, pack_idx=pk)), ("packed_tokens", packed_tok))

    def copy(self, **kw):
        net = self.A.AmberNet(64, 2, **kw).eval()
        sd = dict(self.net.state_dict())
        sd.update({k: v for k, v in net.state_dict().items() if k not in sd})
        net.load_state_dict(sd)
        return net

    @staticmethod
    def swapped(b):
        g = dict(b)
        ids = b["monster_ids"].clone()
        ids[..., [1, 2]] = ids[..., [2, 1]]
        g["monster_ids"] = ids
        return g

    def test_plain_net_is_order_blind(self):
        b = self.batch(1)
        with torch.no_grad():
            for x, y in zip(self.net(b), self.net(self.swapped(b))):
                self.assertLess(float((x - y).abs().max()), 1e-5)

    def test_intent_table_tells_order_apart(self):
        on = self.copy(intent_emb=True)
        with torch.no_grad():
            on.intent_emb.weight.normal_(0, 0.5)
            on.intent_emb.weight[0].zero_()
        b = self.batch(2)
        with torch.no_grad():
            diff = max(float((x - y).abs().max()) for x, y in zip(on(b), on(self.swapped(b))))
        self.assertGreater(diff, 1e-3)

    def test_intent_ids_only_combat_monsters(self):
        A = self.A
        mon, card = A.TOKEN_TYPES.index("monster"), A.TOKEN_TYPES.index("card")
        tt = torch.tensor([mon, mon, card])
        ids = torch.tensor([[5, 600, 700, 0], [5, 6, 7, A.ENC_KIND_BASE + 1], [9, 600, 0, 0]])
        self.assertEqual(A.intent_ids(tt, ids).tolist(), [600, 0, 0])

    def test_zero_intent_table_is_bit_identical(self):
        on = self.copy(intent_emb=True)
        for seed in (3, 4):
            for name, b in self.layouts(self.batch(seed)):
                with torch.no_grad():
                    for x, y in zip(self.net(b), on(b)):
                        self.assertTrue(torch.equal(x, y), (name, seed))

    def test_split_mask_bits(self):
        A = self.A
        a_type = torch.tensor([A.SELECT_MANY, 1, A.SELECT_MANY])
        a_f = torch.zeros(3, A.N_ACT_FEAT)
        a_f[:, A.MASK_SLOT] = torch.tensor([0b1000000101, 0.25, 6.0])
        a_f[:, 0] = 0.3
        f2, bits = A.split_mask_bits(a_type, a_f)
        self.assertEqual(f2[:, A.MASK_SLOT].tolist(), [0.0, 0.25, 0.0])
        self.assertTrue(torch.equal(f2[:, 0], a_f[:, 0]))
        self.assertEqual(bits[0].tolist(), [1, 0, 1, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(bits[1].tolist(), [0] * 10)
        self.assertEqual(bits[2].tolist(), [0, 1, 1, 0, 0, 0, 0, 0, 0, 0])

    def test_mask_bits_from_raw_reproduces_raw_net(self):
        A = self.A
        on = A.mask_bits_from_raw(self.copy(mask_bits=True))
        for seed in (5, 6):
            b = self.batch(seed)
            sm = b["a_type"] == A.SELECT_MANY
            for name, bb in self.layouts(b):
                with torch.no_grad():
                    ref, got = self.net(bb), on(bb)
                self.assertTrue(torch.equal(ref[0][~sm], got[0][~sm]), (name, seed))   # other actions: exact
                scale = float(ref[0][sm].abs().max())
                self.assertLess(float((ref[0][sm] - got[0][sm]).abs().max()), 1e-4 * max(1.0, scale), (name, seed))
                for x, y in zip(ref[1:], got[1:]):
                    self.assertTrue(torch.equal(x, y), (name, seed))

    def test_mask_bits_reads_bits_not_raw_slot(self):
        A = self.A
        on = self.copy(mask_bits=True)
        b = self.batch(7)
        g = dict(b)
        g["a_f"] = b["a_f"].clone()
        sm = b["a_type"] == A.SELECT_MANY
        g["a_f"][..., A.MASK_SLOT] = torch.where(sm, torch.full_like(g["a_f"][..., 0], 1023.0), g["a_f"][..., A.MASK_SLOT])
        with torch.no_grad():   # zero w_mask: SELECT_MANY logits no longer depend on the mask at all
            self.assertTrue(torch.equal(on(b)[0], on(g)[0]))
            self.assertFalse(torch.equal(self.net(b)[0], self.net(g)[0]))

    def test_checkpoint_weights_create_modules(self):
        A = self.A
        on = A.mask_bits_from_raw(self.copy(intent_emb=True, mask_bits=True))
        with torch.no_grad():
            on.intent_emb.weight[1:].normal_(0, 0.1)
        plain = A.AmberNet(64, 2).eval()
        plain.load_state_dict(on.state_dict())
        self.assertIsNotNone(plain.intent_emb)
        self.assertIsNotNone(plain.w_mask)
        self.assertEqual([n for n, _ in plain.named_parameters()], [n for n, _ in on.named_parameters()])
        b = self.batch(8)
        with torch.no_grad():
            for x, y in zip(plain(b), on(b)):
                self.assertTrue(torch.equal(x, y))

    def test_load_opt_state_checks_shapes(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools", "az_bench"))
        sp = load("selfplay_fix_test", "tools", "az_bench", "selfplay.py")
        A = sp.amber_net

        def make(**kw):
            net = A.AmberNet(64, 2, **kw)
            groups = [{"params": [p for n, p in net.named_parameters() if not sp.extra_param(n)]}]
            groups += [{"params": [p]} for n, p in net.named_parameters() if n in A.INPUT_FIX_PARAMS]
            return net, torch.optim.AdamW(groups, lr=1e-3)

        def step(net, opt):
            opt.zero_grad()
            sum(p.sum() for p in net.parameters()).backward()
            opt.step()

        old, old_opt = make(mask_bits=True)          # saved: main + w_mask [64, 10]
        step(old, old_opt)
        new, new_opt = make(intent_emb=True)         # now: main + intent_emb [1024, 64] (same group length 1)
        sp.load_opt_state(new_opt, old_opt.state_dict())
        self.assertNotIn(new.intent_emb.weight, new_opt.state)
        step(new, new_opt)                           # no shape error
        both, both_opt = make(intent_emb=True, mask_bits=True)
        sp.load_opt_state(both_opt, new_opt.state_dict())   # main + intent kept, w_mask fresh
        self.assertIn(both.intent_emb.weight, both_opt.state)
        self.assertNotIn(both.w_mask.weight, both_opt.state)


if __name__ == "__main__":
    unittest.main()
