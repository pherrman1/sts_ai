"""tools/az_bench/amber_net.py: the flat layout (one token axis, az_driver nextBatchFlat) gives the same outputs as
the segmented layout on the same live tokens (fp32, within 1e-5), with and without padding."""

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


if __name__ == "__main__":
    unittest.main()
