"""tools/az_bench/amber_net.py: the flat layout (one token axis, az_driver nextBatchFlat) gives the same outputs as
the segmented layout on the same live tokens (fp32, within 1e-5), with and without padding; the SDPA trunk gives the
same outputs as nn.TransformerEncoder (fp32, within 1e-4)."""

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
        net = A.AmberNet(64, 2).eval()
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
            net = A.AmberNet(d, layers).eval()
            for live_frac in (1.0, 0.4):
                f = A.to_flat(A.synthetic_batch(16, live_frac=live_frac, rng=np.random.default_rng(2)))
                with torch.no_grad():
                    net.sdpa = False
                    o1 = net(f)
                    net.sdpa = True
                    o2 = net(f)
                for x, y in zip(o1, o2):
                    self.assertLess(float((x - y).abs().max()), 1e-4, (d, live_frac))


if __name__ == "__main__":
    unittest.main()
