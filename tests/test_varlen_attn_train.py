"""tools/az_bench/varlen_attn_train.py against a padded torch reference (outputs and gradients), on a CUDA GPU or on
a CPU through Triton's interpreter (TRITON_INTERPRET=1); skipped without triton."""

import importlib.util
import os
import sys
import unittest

try:
    import torch
    import triton  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNABLE = HAVE and (torch.cuda.is_available() or os.environ.get("TRITON_INTERPRET") == "1")


def load(name):
    key = "az_bench_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(ROOT, "tools", "az_bench", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[key] = m
    spec.loader.exec_module(m)
    return m


def reference(qkv_pad, mask, H, cls, tab, keys=None):
    """Padded attention with the class bias (fp32), restricted to `keys` [B, T] when given; [B, T, d]."""
    B, T, D3 = qkv_pad.shape
    d = D3 // 3
    q, k, v = qkv_pad.view(B, T, 3, H, d // H).permute(2, 0, 3, 1, 4)
    s = (q @ k.transpose(-1, -2)) * (d // H) ** -0.5
    if tab is not None:
        C = tab.shape[-1]
        s = s + tab.reshape(H, C * C)[:, cls[:, :, None] * C + cls[:, None, :]].permute(1, 0, 2, 3)
    kk = mask if keys is None else mask & keys
    s = s.masked_fill(~kk[:, None, None, :], float("-inf"))
    o = torch.softmax(s, -1) @ v
    return o.transpose(1, 2).reshape(B, T, d)


@unittest.skipUnless(RUNNABLE, "needs triton and a CUDA GPU or TRITON_INTERPRET=1")
class VarlenAttnTrain(unittest.TestCase):
    dev = "cuda" if HAVE and torch.cuda.is_available() else "cpu"

    def run_case(self, B, T, H, dh, dtype, with_tab, split, seed):
        V = load("varlen_attn_train")
        g = torch.Generator().manual_seed(seed)
        d = H * dh
        C = 7
        n = torch.randint(1, T + 1, (B,), generator=g)
        mask = torch.arange(T)[None, :] < n[:, None]
        cls = torch.randint(0, C, (B, T), generator=g)
        cls[::2] = torch.where((cls[::2] >= 1) & (cls[::2] <= 3), torch.zeros_like(cls[::2]), cls[::2])
        e = torch.zeros(C, dtype=torch.bool)
        e[1:4] = True
        tab = (torch.randn(H, C, C, generator=g) * (e[:, None] | e[None, :])) if with_tab else None
        qkv_pad = torch.randn(B, T, 3 * d, generator=g)
        dout_pad = torch.randn(B, T, d, generator=g)
        # reference in fp32 on the values rounded to dtype
        qr = qkv_pad.to(dtype).float().clone().requires_grad_(True)
        tr = tab.clone().requires_grad_(True) if with_tab else None
        ref = reference(qr, mask, H, cls, tr)
        (ref * dout_pad * mask[..., None]).sum().backward()
        pk = mask.reshape(-1).nonzero().squeeze(1)
        so = torch.cat([torch.zeros(1, dtype=torch.int32), mask.sum(1).cumsum(0).to(torch.int32)])
        qkv = qkv_pad.detach().reshape(B * T, -1)[pk].to(dtype).to(self.dev).requires_grad_(True)
        cp = cls.reshape(-1)[pk].to(torch.int32).to(self.dev)
        tt = tab.to(self.dev).requires_grad_(True) if with_tab else None
        rf = V.row_flags(cp, so.to(self.dev)) if split else None
        out = V.varlen_attn_train(qkv, so.to(self.dev), H, T, cp, tt, rf)
        (out.float() * dout_pad.reshape(B * T, d)[pk].to(self.dev)).sum().backward()
        tol = 1e-4 if dtype == torch.float32 and self.dev == "cpu" else 3e-2
        self.assertLess(float((out.float().cpu() - ref.reshape(B * T, d)[pk].detach()).abs().max()), tol)
        gq = qr.grad.reshape(B * T, -1)[pk]
        self.assertLess(float((qkv.grad.float().cpu() - gq).abs().max()), tol * 3, (B, T, dtype, with_tab, split))
        if with_tab:
            # split: rows without encounter tokens run without the bias, so only the entries with an encounter class
            # (the ones AmberNet._tab keeps) get their full gradient
            em = (e[:, None] | e[None, :]) if split else torch.ones(C, C, dtype=torch.bool)
            self.assertLess(float((tt.grad.cpu() - tr.grad)[:, em].abs().max()), tol * 10, ("dtab", split))

    def test_fp32(self):
        for with_tab in (False, True):
            for split in (False, True):
                self.run_case(5, 20, 2, 32, torch.float32, with_tab, split, 1)
                self.run_case(3, 90, 4, 32, torch.float32, with_tab, split, 2)

    def test_half(self):
        dt = torch.bfloat16 if self.dev == "cuda" else torch.float16
        self.run_case(6, 70, 4, 32, dt, True, True, 3)

    def test_rows_only(self):
        """rows_only: rows with rf == 0 get zero outputs and gradients; the others as the full call."""
        V = load("varlen_attn_train")
        g = torch.Generator().manual_seed(4)
        B, T, H, dh = 4, 40, 2, 32
        d = H * dh
        n = torch.randint(1, T + 1, (B,), generator=g)
        mask = torch.arange(T)[None, :] < n[:, None]
        pk = mask.reshape(-1).nonzero().squeeze(1)
        so = torch.cat([torch.zeros(1, dtype=torch.int32), mask.sum(1).cumsum(0).to(torch.int32)]).to(self.dev)
        qkv = torch.randn(B * T, 3 * d, generator=g)[pk].to(self.dev).requires_grad_(True)
        rf = torch.tensor([1, 0, 1, 0], dtype=torch.int32, device=self.dev)
        full = V.varlen_attn_train(qkv, so, H, T)
        part = V.varlen_attn_train(qkv, so, H, T, rf=rf, rows_only=True)
        row = torch.bucketize(torch.arange(len(pk), device=self.dev), so[1:].long(), right=True)
        on = rf[row] != 0
        self.assertLess(float((part[on] - full[on]).abs().max()), 1e-4 if self.dev == "cpu" else 1e-2)
        self.assertEqual(float(part[~on].abs().max()), 0.0)
        part.sum().backward()
        self.assertEqual(float(qkv.grad[~on].abs().max()), 0.0)


    def test_net_training_matches_sdpa_path(self):
        """AmberNet in training with train_attn (packed tokens, own kernels) gives the outputs and gradients of the
        padded SDPA path (_attend_enemy), with the bias and the gate as the mix and as the key gate."""
        V = load("varlen_attn_train")
        sys.path.insert(0, os.path.join(ROOT, "tools", "az_bench"))
        es = load("enemy_speed")
        A = es.A
        f = es.batch(24, 0.4, 30, 5)
        f = {k: v.to(self.dev) for k, v in f.items()}
        f["pack_idx"] = A.pack_index(f["mask"], 16)
        for key in (False, True):
            torch.manual_seed(0)
            net = A.jitter_1d_params(A.AmberNet(64, 2, enemy_bias=True, enemy_gate=True)).to(self.dev).train()
            net.sdpa = True
            net.gate_key = key
            with torch.no_grad():
                net.enemy_bias.normal_(0, 0.5)
                net.enemy_gate.copy_(torch.tensor([0.3, 0.6, 0.4]))
            outs, grads = [], []
            for ta in (None, V.varlen_attn_train):
                net.train_attn = ta
                net.zero_grad()
                o = net(f)
                loss = o[0].float().masked_fill(~f["a_mask"], 0).sum() + o[1].float().logsumexp(-1).sum() \
                    + o[2].float().logsumexp(-1).sum() + o[3].float().sum()
                loss.backward()
                outs.append([x.detach() for x in o])
                grads.append({n_: p_.grad.detach().clone() for n_, p_ in net.named_parameters() if p_.grad is not None})
            tol = 1e-3 if self.dev == "cpu" else 2e-2
            for x, y in zip(*outs):
                self.assertLess(float((x - y).abs().max()), tol, key)
            for n_ in grads[0]:
                a_, b_ = grads[0][n_], grads[1][n_]
                self.assertLess(float((a_ - b_).abs().max()), tol * max(1.0, float(a_.abs().max())), (key, n_))


if __name__ == "__main__":
    unittest.main()
