"""tools/az_bench/amber_net.py: the flat layout (one token axis, az_driver nextBatchFlat) gives the same outputs as
the segmented layout on the same live tokens (fp32, within 1e-5), with and without padding; the SDPA trunk and the packed
forward (per-token work on live tokens only) give the same outputs as nn.TransformerEncoder (fp32, within 1e-4)."""

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


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class AmberFlatEquivalence(unittest.TestCase):
    def test_flat_matches_segments(self):
        spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
        A = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(A)
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        for live_frac in (1.0, 0.6, 0.3):
            b = A.synthetic_batch(16, live_frac=live_frac, rng=np.random.default_rng(1))
            f = A.to_flat(b)
            with torch.no_grad():
                o1, o2 = net(b), net(f)
            for x, y in zip(o1, o2):
                self.assertLess(float((x - y).abs().max()), 1e-5, live_frac)

    def test_sdpa_trunk_matches_trunk(self):
        spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
        A = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(A)
        torch.manual_seed(0)
        for d, layers in ((64, 2), (128, 2)):
            net = A.jitter_1d_params(A.AmberNet(d, layers).eval())
            for live_frac in (1.0, 0.4):
                f = A.to_flat(A.synthetic_batch(16, live_frac=live_frac, rng=np.random.default_rng(2)))
                with torch.no_grad():
                    net.sdpa = False
                    o1 = net(f)
                    net.sdpa = True
                    o2 = net(f)
                for x, y in zip(o1, o2):
                    self.assertLess(float((x - y).abs().max()), 1e-4, (d, live_frac))

    def test_packed_matches_flat(self):
        spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
        A = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(A)
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        for live_frac, step in ((1.0, 1), (0.4, 1), (0.4, 64)):
            f = A.to_flat(A.synthetic_batch(16, live_frac=live_frac, rng=np.random.default_rng(3)))
            with torch.no_grad():
                net.sdpa = False
                o1 = net(f)
                o2 = net(dict(f, pack_idx=A.pack_index(f["mask"], step)))
                pk, inv = A.pack_index(f["mask"], step, inverse=True)
                o3 = net(dict(f, pack_idx=pk, unpack_idx=inv))
                net.attn_math = True
                o4 = net(dict(f, pack_idx=pk, unpack_idx=inv))
                net.attn_math = False
            for x, y, z, w in zip(o1, o2, o3, o4):
                self.assertLess(float((x - y).abs().max()), 1e-4, (live_frac, step))
                self.assertLess(float((x - z).abs().max()), 1e-4, (live_frac, step))
                self.assertLess(float((x - w).abs().max()), 1e-4, (live_frac, step))

    def test_dead_slot_contents_do_not_matter(self):
        """nextBatchFlat leaves old data in dead token slots (az_driver.cpp): any type / id / floats there must give
        exactly the same outputs as zeros, for the flat (trunk, SDPA) and packed (scatter, gather) forwards."""
        spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
        A = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(A)
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        f = A.to_flat(A.synthetic_batch(16, live_frac=0.5, rng=np.random.default_rng(6)))
        # to_flat pads only to the longest row (equal counts here): append 9 dead slots to every row
        f = dict(f, tok_type=torch.nn.functional.pad(f["tok_type"], (0, 9)),
                 ids=torch.nn.functional.pad(f["ids"], (0, 0, 0, 9)), f=torch.nn.functional.pad(f["f"], (0, 0, 0, 9)),
                 mask=torch.nn.functional.pad(f["mask"], (0, 9)))
        g = dict(f)
        dead = ~f["mask"]
        self.assertGreater(int(dead.sum()), 0)
        rng = torch.Generator().manual_seed(1)
        g["tok_type"] = torch.where(dead, torch.randint(0, len(A.TOKEN_TYPES), dead.shape, generator=rng), f["tok_type"])
        g["ids"] = torch.where(dead[..., None], torch.randint(0, A.ID_VOCAB, f["ids"].shape, generator=rng), f["ids"])
        g["f"] = torch.where(dead[..., None], 300 * torch.randn(f["f"].shape, generator=rng), f["f"])
        with torch.no_grad():
            for sdpa in (False, True):
                net.sdpa = sdpa
                for x, y in zip(net(f), net(g)):
                    self.assertEqual(float((x - y).abs().max()), 0.0, ("flat", sdpa))
            net.sdpa = False
            for step in (1, 64):
                pk, inv = A.pack_index(f["mask"], step, inverse=True)
                for extra in ({"pack_idx": pk}, {"pack_idx": pk, "unpack_idx": inv}):
                    for x, y in zip(net(dict(f, **extra)), net(dict(g, **extra))):
                        self.assertEqual(float((x - y).abs().max()), 0.0, ("packed", step, len(extra)))


if __name__ == "__main__":
    unittest.main()
