"""tools/az_bench/amber_net.py zero_consequence_inputs (selfplay.py --consequences on a net trained without them):
with the consequence input columns at 0, the net gives bit-identical outputs whatever the consequence slots hold,
equal to the original net on the encoding without them (segmented, flat and packed forwards, fp32; the 1.2M size of
the live run), and the zeroed columns get gradients, so they train from the first step."""

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


def load_amber_net():
    spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    return A


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class ConsequenceZeroInit(unittest.TestCase):
    def setUp(self):
        self.A = load_amber_net()

    def batches(self, seed):
        """(old, new): one segmented batch without consequence values (their slots 0) and the same batch with random
        values in them."""
        A = self.A
        new = A.synthetic_batch(16, live_frac=0.6, rng=np.random.default_rng(seed))
        old = dict(new)
        for t, (lo, hi) in A.CONSEQUENCE_FLOATS.items():
            old[t + "_f"] = new[t + "_f"].clone()
            old[t + "_f"][..., lo:hi] = 0
        old["a_f"] = new["a_f"].clone()
        old["a_f"][..., slice(*A.CONSEQUENCE_ACT_FEATS)] = 0
        return old, new

    def test_zeroed_net_is_the_old_net(self):
        A = self.A
        torch.manual_seed(0)
        d, layers = A.SIZES["1.2M"]
        base = A.jitter_1d_params(A.AmberNet(d, layers).eval())
        zeroed = A.AmberNet(d, layers).eval()
        zeroed.load_state_dict(base.state_dict())
        n = A.zero_consequence_inputs(zeroed)
        self.assertEqual(n, d * (15 + 19 + 19 + 1))
        for name, cols in A.consequence_inputs():   # the source had nonzero weights there
            self.assertGreater(float(dict(base.named_parameters())[name].detach()[:, cols].abs().sum()), 0, name)
        for seed in (1, 2):
            old, new = self.batches(seed)
            fo, fn = A.to_flat(old), A.to_flat(new)
            pk, inv = A.pack_index(fo["mask"], 1, inverse=True)
            with torch.no_grad():
                ref = [base(old), base(fo), base(dict(fo, pack_idx=pk, unpack_idx=inv))]
                got = [zeroed(new), zeroed(fn), zeroed(dict(fn, pack_idx=pk, unpack_idx=inv))]
                moved = base(new)
            for path, (r, g) in enumerate(zip(ref, got)):
                for x, y in zip(r, g):
                    self.assertTrue(torch.equal(x, y), (seed, path))
            # the consequence values do reach the un-zeroed net (the check above is not vacuous)
            self.assertFalse(all(torch.equal(x, y) for x, y in zip(ref[0], moved)))

    def test_zeroed_columns_train(self):
        A = self.A
        torch.manual_seed(0)
        net = A.AmberNet(64, 2)
        A.zero_consequence_inputs(net)
        _, new = self.batches(3)
        out = net(new)
        (out[0].logsumexp(-1).sum() + out[1].sum()).backward()
        params = dict(net.named_parameters())
        for name, cols in A.consequence_inputs():
            self.assertGreater(float(params[name].grad[:, cols].abs().sum()), 0, name)

    def test_dict_form(self):
        A = self.A
        net = A.AmberNet(64, 2)
        named = {n: p.detach().clone() for n, p in net.named_parameters()}
        A.zero_consequence_inputs(named)
        for name, cols in A.consequence_inputs():
            self.assertEqual(float(named[name][:, cols].abs().sum()), 0.0, name)
            self.assertGreater(float(named[name].abs().sum()), 0.0, name)


if __name__ == "__main__":
    unittest.main()
