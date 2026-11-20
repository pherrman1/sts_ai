"""AmberNet packed heads (tools/az_bench/amber_net.py _heads_packed, tools/az_bench/row_mean.py): the row summary on
the packed tokens and the action head on the live actions only give the outputs of the padded heads on the live
rows and actions, also with padding rows of length 0 and trash entries. Runs on a CUDA GPU or on a CPU through
Triton's interpreter (TRITON_INTERPRET=1); skipped without triton."""

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


def load_amber_net():
    spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    return A


def act_index(a_mask, rows, step):
    """The live action slots of the first `rows` rows, padded with the trash slot B * A to a multiple of step."""
    B, A = a_mask.shape
    idx = torch.nonzero(a_mask[:rows].reshape(-1)).squeeze(1)
    npad = -(-idx.numel() // step) * step
    return torch.cat([idx, idx.new_full((npad - idx.numel(),), B * A)])


@unittest.skipUnless(RUNNABLE, "needs triton and a CUDA GPU or TRITON_INTERPRET=1")
class PackedHeads(unittest.TestCase):
    dev = "cuda" if HAVE and torch.cuda.is_available() else "cpu"

    def test_row_mean(self):
        A = load_amber_net()
        row_mean = A.load_kernel("row_mean")
        g = torch.Generator().manual_seed(1)
        n = torch.tensor([1, 0, 2, 33, 34, 65, 96, 7, 0])
        off = torch.cat([torch.zeros(1, dtype=torch.long), n.cumsum(0)]).int()
        for dt, tol in ((torch.float32, 1e-5), (torch.float16, 2e-3)):
            x = torch.randn(int(n.sum()) + 3, 64, generator=g).to(dt)
            got = row_mean(x.to(self.dev), off.to(self.dev)).float().cpu()
            for r in range(len(n)):
                s, k = int(off[r]), int(n[r])
                want = x[s + 1:s + k].float().mean(0) if k > 1 else torch.zeros(64)
                self.assertLess(float((got[r] - want).abs().max()), tol, (r, k, dt))

    def test_packed_heads_match_padded(self):
        A = load_amber_net()
        f = A.to_flat(A.synthetic_batch(12, actions=10, live_frac=0.6, rng=np.random.default_rng(4)))
        f["a_mask"][:, 6:] &= torch.rand(12, 4, generator=torch.Generator().manual_seed(2)) < 0.5   # ragged actions
        f["a_src"][3, 0] = -1                                                                        # a "none" pick
        f = {k: v.to(self.dev) for k, v in f.items()}
        for d, layers, hp_floors in ((64, 2, 56), (32, 1, 1)):
            torch.manual_seed(0)
            net = A.jitter_1d_params(A.AmberNet(d, layers, hp_floors=hp_floors, soft_policy=True).eval()).to(self.dev)
            net.varlen_attn = A.load_kernel("varlen_attn")
            net.fused_layer = A.load_fused_layer()
            net.row_mean = A.load_kernel("row_mean")
            b = dict(f, pack_idx=A.pack_index(f["mask"], 16), seq_off=A.seq_offsets(f["mask"]))
            with torch.no_grad():
                want = net(b)
                net.packed_heads = True
                same = net(b)                                 # no act_idx: still the padded heads
                # rows 9 .. 11 as padding rows: length 0 in seq_off, their actions not listed
                so = b["seq_off"].clone()
                so[10:] = so[9]
                got = net(dict(b, seq_off=so, act_idx=act_index(f["a_mask"], 9, 16)))
            for x, y in zip(want, same):
                self.assertTrue(torch.equal(x, y))
            self.assertEqual(len(got), 4)
            live = f["a_mask"][:9]
            self.assertLess(float((got[0][:9] - want[0][:9]).abs()[live].max()), 1e-4, d)
            self.assertTrue(bool((got[0][:9][~live] == -1e4).all()))
            for x, y in zip(got[1:], want[1:]):
                self.assertLess(float((x[:9] - y[:9]).abs().max()), 1e-4, d)

    def test_training_mode_keeps_padded_heads(self):
        """The soft policy output exists only in training mode and only in the padded heads: a net in training
        mode ignores packed_heads."""
        A = load_amber_net()
        f = A.to_flat(A.synthetic_batch(4, rng=np.random.default_rng(6)))
        f = {k: v.to(self.dev) for k, v in f.items()}
        net = A.AmberNet(64, 1, soft_policy=True).to(self.dev).train()
        net.row_mean = A.load_kernel("row_mean")
        net.packed_heads = True
        b = dict(f, pack_idx=A.pack_index(f["mask"], 16), seq_off=A.seq_offsets(f["mask"]),
                 act_idx=act_index(f["a_mask"], 4, 16))
        with torch.no_grad():
            self.assertEqual(len(net(b)), 5)


if __name__ == "__main__":
    unittest.main()
