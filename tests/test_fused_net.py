"""tools/az_bench/fused_net.py: the whole-net Triton kernel equals AmberNet.forward_packed (fp32 within 1e-4 in the
interpreter; fp16 weights against the fp32 net within 3e-2) on packed variable-length rows, including rows
in the big-tile launch, empty rows past `rows`, and actions with no source / target. Runs on a CUDA GPU, or on a CPU
through Triton's interpreter (TRITON_INTERPRET=1); skipped without triton."""

import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy as np
    import torch
    import triton  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

RUNNABLE = HAVE and (torch.cuda.is_available() or os.environ.get("TRITON_INTERPRET") == "1")


def load(name):
    key = "az_test_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(ROOT, "tools", "az_bench", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sys.modules[key] = m
    return m


def batch(A, rows, tokens, actions, seed, extra_rows=0):
    return load("fused_net_bench").synthetic_packed(A, tokens, actions, seed=seed, extra_rows=extra_rows)


@unittest.skipUnless(RUNNABLE, "needs triton and a CUDA GPU or TRITON_INTERPRET=1")
class FusedNet(unittest.TestCase):
    def check(self, d, layers, hp_floors, tokens, actions, extra_rows=0, tile=None, big=None, max_rows=None,
              half=False):
        A = load("amber_net")
        K = load("fused_net")
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        torch.manual_seed(1)
        net = A.jitter_1d_params(A.AmberNet(d, layers, hp_floors=hp_floors).eval())
        with torch.no_grad():   # a_none starts at 0: make the "none" source / target matter
            net.a_none.normal_()
        net.sdpa = True
        rows = len(tokens)
        b, ref = batch(A, rows, tokens, actions, seed=d + layers, extra_rows=extra_rows)
        with torch.no_grad():
            want = net(ref)
        gpu = dev == "cuda"
        half = half or gpu
        fn = K.FusedNet(net.to(dev), torch.float16 if half else torch.float32)
        tiles = K.make_tiles(b["seq_off"].numpy(), rows, tile, big, max_rows)
        bd = {k: v.to(dev) for k, v in b.items()}
        if half:
            bd["f"], bd["a_f"] = bd["f"].half(), bd["a_f"].half()
        with torch.no_grad():
            got = fn(bd, tiles, rows)
        tol = 3e-2 if half else 1e-4
        for name, w, g in zip(("logits", "outcome", "hp", "hp_floor"), want, got):
            self.assertEqual(tuple(w.shape), tuple(g.shape), name)
            err = float((w[:rows].float() - g[:rows].float().cpu()).abs().max())
            self.assertLess(err, tol, f"{name}: max abs err {err}")
        return tiles

    def test_small_tiles(self):
        tokens = [5, 17, 3, 30, 12, 2, 9, 26, 31, 1, 14]
        t = self.check(64, 2, 56, tokens, actions=7, extra_rows=3, tile=32, big=64, max_rows=16)
        self.assertGreater(len(t["small"][0]), 1)

    def test_big_tile_rows(self):
        # rows longer than the 32-token tile go to the 64-token launch
        tokens = [40, 6, 8, 33, 64, 2, 20]
        t = self.check(64, 1, 1, tokens, actions=5, tile=32, big=64)
        self.assertEqual(list(t["big"][0]), [0, 3, 4])

    def test_row_cap(self):
        # many short rows: the row cap (16) closes tiles before the token budget
        tokens = [2, 3, 1, 2] * 9
        t = self.check(64, 1, 56, tokens, actions=3, tile=128, big=256, max_rows=16)
        self.assertTrue(all(e - s <= 16 for s, e in zip(*t["small"])))

    def test_full_size_default_tiles(self):
        # the 0.44M net (64 x 6) with the default tiles, token counts as in self-play (~26 per state with card stacks)
        rng = np.random.default_rng(3)
        tokens = [int(v) for v in rng.integers(8, 60, 23)] + [150]
        self.check(64, 6, 56, tokens, actions=16, extra_rows=2)

    def test_fp16_weights(self):
        # fp16 weights and inputs (the self-play inference dtype) against the fp32 net
        tokens = [5, 17, 3, 30, 12, 2, 9, 26]
        self.check(64, 6, 56, tokens, actions=9, tile=64, big=128, half=True)

    def test_make_tiles_cover(self):
        K = load("fused_net")
        rng = np.random.default_rng(0)
        n = rng.integers(0, 150, 500)
        so = np.concatenate([[0], np.cumsum(n)])
        t = K.make_tiles(so, 500, 128, 256, 16)
        seen = []
        for s, e in zip(*t["small"]):
            self.assertLessEqual(so[e] - so[s], 128)
            self.assertLessEqual(e - s, 16)
            seen += range(s, e)
        for s, e in zip(*t["big"]):
            self.assertGreater(so[e] - so[s], 128)
            seen += range(s, e)
        self.assertEqual(sorted(seen), list(range(500)))


if __name__ == "__main__":
    unittest.main()
