"""tools/az_bench/amber_net.py run_log_slots (selfplay.py --run-log-loopcount): with the RUN token's float slot 7
log-scaled, every forward layout (segments, flat, packed, packed tokens) gives the outputs of the plain net on
inputs whose slot 7 was log-scaled beforehand; other token types and other slots are untouched; with the default
(no slots) the outputs are bit-identical to a net that never had the attribute set."""

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
class RunLogLoopCount(unittest.TestCase):
    def setUp(self):
        self.A = load_amber_net()
        torch.manual_seed(0)
        self.net = self.A.jitter_1d_params(self.A.AmberNet(64, 2).eval())

    def batch(self, seed):
        A = self.A
        b = A.synthetic_batch(16, live_frac=0.6, rng=np.random.default_rng(seed))
        rng = np.random.default_rng(seed + 100)
        b["run_f"][..., 7] = torch.from_numpy(rng.integers(0, 6000, b["run_f"].shape[:-1]).astype(np.float32))
        return b

    def pre_scaled(self, b):
        g = dict(b)
        f = b["run_f"].clone()
        f[..., 7] = torch.log1p(f[..., 7])
        g["run_f"] = f
        return g

    def test_helper_touches_only_run_slot(self):
        A = self.A
        tt = torch.tensor([[0, 1, 4, 0]])
        f = torch.full((1, 4, 64), 100.0)
        out = A.log_run_slots(tt, f, A.RUN_LOG_LOOPCOUNT_SLOTS)
        self.assertTrue(torch.equal(f, torch.full((1, 4, 64), 100.0)))   # input not written
        expect = f.clone()
        expect[0, 0, 7] = expect[0, 3, 7] = float(np.log1p(100.0))
        self.assertTrue(torch.allclose(out, expect))
        self.assertIs(A.log_run_slots(tt, f, ()), f)

    def test_default_is_identity(self):
        A = self.A
        b = A.to_flat(self.batch(1))
        ref = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        ref.load_state_dict(self.net.state_dict())
        self.assertEqual(self.net.run_log_slots, ())
        with torch.no_grad():
            for x, y in zip(self.net(b), ref(b)):
                self.assertTrue(torch.equal(x, y))

    def test_all_layouts_match_pre_scaled_input(self):
        A = self.A
        on = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        on.load_state_dict(self.net.state_dict())
        on.run_log_slots = A.RUN_LOG_LOOPCOUNT_SLOTS
        for seed in (2, 3):
            b = self.batch(seed)
            ref_seg = self.pre_scaled(b)
            f, f_ref = A.to_flat(b), A.to_flat(ref_seg)
            pk = A.pack_index(f["mask"], 1)
            M = f["mask"].numel()
            ip = pk.clamp(max=M - 1)
            packed_tok = dict(f, pack_idx=pk, tok_type=f["tok_type"].reshape(M)[ip].clone(),
                              ids=f["ids"].reshape(M, -1)[ip].clone(), f=f["f"].reshape(M, -1)[ip].clone())
            with torch.no_grad():
                want = self.net(f_ref)
                for name, got in (("segments", on(b)), ("flat", on(f)), ("packed", on(dict(f, pack_idx=pk))),
                                  ("packed_tokens", on(packed_tok))):
                    for x, y in zip(got, want):
                        self.assertLess(float((x - y).abs().max()), 1e-4, (name, seed))
                # and the flag does change the outputs on these inputs (slot 7 is large)
                raw = self.net(f)
                self.assertGreater(max(float((x - y).abs().max()) for x, y in zip(raw, want)), 1e-3)

    def test_input_options_from_ckpt(self):
        A = self.A
        for args, want in (({"run_log_loopcount": True}, A.RUN_LOG_LOOPCOUNT_SLOTS), ({"run_log_loopcount": False}, ()),
                           ({}, ()), (None, ())):
            net = A.AmberNet(64, 2)
            net.run_log_slots = (3,)
            ck = {"net": {}} if args is None else {"net": {}, "args": args}
            self.assertIs(A.input_options_from_ckpt(net, ck), net)
            self.assertEqual(net.run_log_slots, want, args)

    def test_explain_load_net_honours_flag(self):
        import sys
        import tempfile
        sys.path.insert(0, os.path.join(ROOT, "tools", "az_bench"))
        spec = importlib.util.spec_from_file_location("explain", os.path.join(ROOT, "tools", "az_bench", "explain.py"))
        ex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ex)
        net = ex.amber_net.AmberNet(64, 2, hp_floors=56)
        with tempfile.TemporaryDirectory() as td:
            for flag in (True, False):
                path = os.path.join(td, f"ck{flag}.pt")
                torch.save({"net": net.state_dict(), "args": {"run_log_loopcount": flag}}, path)
                got = ex.load_net(path)
                self.assertEqual(got.run_log_slots, ex.amber_net.RUN_LOG_LOOPCOUNT_SLOTS if flag else ())


if __name__ == "__main__":
    unittest.main()
