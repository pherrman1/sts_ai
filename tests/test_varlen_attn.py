"""tools/az_bench/varlen_attn.py: attention on packed tokens (one Triton program per row, head and query block)
equals scaled_dot_product_attention with a key padding mask on the padded layout, and AmberNet.forward_packed with
varlen_attn equals it without (fp32 within 1e-4 in the interpreter; TF32 on a GPU within 5e-3). Runs on a CUDA GPU
or on a CPU through Triton's interpreter (TRITON_INTERPRET=1); skipped without triton."""

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
class VarlenAttn(unittest.TestCase):
    dev = "cuda" if HAVE and torch.cuda.is_available() else "cpu"
    tol = 5e-3 if HAVE and torch.cuda.is_available() else 1e-4

    def test_kernel_matches_sdpa(self):
        A, V = load("amber_net"), load("varlen_attn")
        g = torch.Generator().manual_seed(0)
        for B, T, H, dh in ((5, 20, 2, 32), (3, 90, 4, 32)):   # T = 90: several key / query blocks
            d = H * dh
            n = torch.randint(1, T + 1, (B,), generator=g)
            mask = torch.arange(T)[None, :] < n[:, None]
            qkv_pad = torch.randn(B, T, 3 * d, generator=g)
            q, k, v = qkv_pad.view(B, T, 3, H, dh).permute(2, 0, 3, 1, 4)
            ref = torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=mask[:, None, None, :])
            ref = ref.transpose(1, 2).reshape(B * T, d)[mask.reshape(-1)]
            pk = A.pack_index(mask, 1)
            qkv = qkv_pad.reshape(B * T, -1)[pk].contiguous().to(self.dev)
            out = V.varlen_attn(qkv, A.seq_offsets(mask).to(self.dev), H, T)
            self.assertLess(float((out.cpu() - ref).abs().max()), self.tol, (B, T))

    def test_packed_forward_with_varlen(self):
        A = load("amber_net")
        torch.manual_seed(0)
        net = A.AmberNet(64, 2).eval().to(self.dev)
        f = A.to_flat(A.synthetic_batch(8, live_frac=0.5, rng=np.random.default_rng(5)))
        f = {k: v.to(self.dev) for k, v in f.items()}
        pk, inv = A.pack_index(f["mask"], 16, inverse=True)
        b = dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]))
        with torch.no_grad():
            o1 = net(b)
            net.varlen_attn = A.load_kernel("varlen_attn")
            o2 = net(b)
        for x, y in zip(o1, o2):
            self.assertLess(float((x - y).abs().max()), self.tol)


if __name__ == "__main__":
    unittest.main()
