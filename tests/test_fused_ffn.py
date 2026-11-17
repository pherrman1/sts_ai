"""tools/az_bench/fused_ffn.py: the fused LayerNorm + FFN + residual Triton kernel equals the PyTorch encoder layer's
feed-forward half (fp32 within 1e-5 in the interpreter, 5e-3 with TF32 on a GPU; fp16 within 2e-2), and AmberNet.forward_packed with fused_ffn = True equals it
without. Runs on a CUDA GPU, or on a CPU through Triton's interpreter (TRITON_INTERPRET=1); skipped without triton."""

import copy
import importlib.util
import os
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
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", "az_bench", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(RUNNABLE, "needs triton and a CUDA GPU or TRITON_INTERPRET=1")
class FusedFFN(unittest.TestCase):
    def test_kernel_matches_layer(self):
        F = load("fused_ffn")
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        torch.manual_seed(0)
        base = torch.nn.TransformerEncoderLayer(64, 2, 256, dropout=0.0, activation="gelu", batch_first=True,
                                                norm_first=True).eval()
        x32 = torch.randn(100, 64)
        with torch.no_grad():
            ref = x32 + base.linear2(torch.nn.functional.gelu(base.linear1(base.norm2(x32))))
        # fp32 tl.dot runs as TF32 on a GPU (~1e-3); exact in the interpreter
        tol32 = 5e-3 if dev == "cuda" else 1e-5
        for dt, tol in ((torch.float32, tol32), (torch.float16, 2e-2)):
            layer = copy.deepcopy(base).to(dev, dt)
            with torch.no_grad():
                out = F.fused_ffn(x32.to(dev, dt), layer)
            self.assertLess(float((out.float().cpu() - ref).abs().max()), tol, dt)

    def test_packed_forward_with_fused_ffn(self):
        A = load("amber_net")
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        torch.manual_seed(0)
        net = A.AmberNet(64, 2).eval().to(dev)
        tol = 2e-3 if dev == "cuda" else 1e-4   # TF32 on a GPU
        f = A.to_flat(A.synthetic_batch(8, live_frac=0.5, rng=np.random.default_rng(4)))
        f = {k: v.to(dev) for k, v in f.items()}
        pk, inv = A.pack_index(f["mask"], 16, inverse=True)
        b = dict(f, pack_idx=pk, unpack_idx=inv)
        with torch.no_grad():
            o1 = net(b)
            net.fused_ffn = A.load_fused_ffn()
            o2 = net(b)
        for x, y in zip(o1, o2):
            self.assertLess(float((x - y).abs().max()), tol)


if __name__ == "__main__":
    unittest.main()
