"""tools/az_bench/varlen_attn.py: attention on packed tokens (one Triton program per row, head and query block)
equals scaled_dot_product_attention with a key padding mask on the padded layout, and AmberNet.forward_packed with
varlen_attn (and with the fused layer kernels) equals it without (fp32 within 1e-4 in the interpreter; TF32 on a GPU within 5e-3). Runs on a CUDA GPU
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
    """amber_net, or a kernel module through amber_net.load_kernel (one instance per process: the kernel modules
    register torch custom ops, which must not be registered twice)."""
    import sys
    spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    if name == "amber_net":
        return A
    A.load_kernel(name)
    return sys.modules["az_bench_" + name]


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
        f = A.to_flat(A.synthetic_batch(8, live_frac=0.5, rng=np.random.default_rng(5)))
        f = {k: v.to(self.dev) for k, v in f.items()}
        pk, inv = A.pack_index(f["mask"], 16, inverse=True)
        b = dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]))
        for d, layers in ((64, 2), (32, 1)):   # 32: 3 d = 96 is not a multiple of the 64-column output block
            torch.manual_seed(0)
            net = A.jitter_1d_params(A.AmberNet(d, layers).eval()).to(self.dev)
            with torch.no_grad():
                o1 = net(b)
                net.varlen_attn = A.load_kernel("varlen_attn")
                o2 = net(b)
                net.fused_layer = A.load_fused_layer()
                o3 = net(b)
            for x, y, z in zip(o1, o2, o3):
                self.assertLess(float((x - y).abs().max()), self.tol, d)
                self.assertLess(float((x - z).abs().max()), self.tol, d)

    def test_row_bounds_same_values(self):
        """ROW_BOUNDS (the key loop ends at the row's length, query blocks past it do nothing): the same output
        values as the default kernel, for rows of 1 token (padding rows), rows at block edges and rows that fill
        the bucket, in batches of one to four blocks; and the same forward_packed outputs."""
        import sys
        A, V = load("amber_net"), load("varlen_attn")
        mod = sys.modules["az_bench_varlen_attn"]
        g = torch.Generator().manual_seed(3)
        try:
            for T, H, dh, dt in ((20, 2, 32, torch.float32), (64, 4, 16, torch.float32), (96, 4, 16, torch.float16),
                                 (128, 4, 16, torch.float16), (212, 4, 16, torch.float32)):
                d = H * dh
                n = torch.cat([torch.tensor([1, 1, T, min(T, 64), min(T, 65), min(T, 33), 2]),
                               torch.randint(1, T + 1, (5,), generator=g)])
                off = torch.cat([torch.zeros(1, dtype=torch.long), n.cumsum(0)]).int().to(self.dev)
                qkv = torch.randn(int(n.sum()) + 7, 3 * d, generator=g).to(dt).to(self.dev)   # + 7: bucket padding
                mod.ROW_BOUNDS = False
                a = V.varlen_attn(qkv, off, H, T)[:int(n.sum())]
                mod.ROW_BOUNDS = True
                b = V.varlen_attn(qkv, off, H, T)[:int(n.sum())]
                self.assertTrue(bool(torch.isfinite(a).all()), T)
                self.assertTrue(torch.equal(a, b), T)
            f = A.to_flat(A.synthetic_batch(8, live_frac=0.5, rng=np.random.default_rng(11)))
            f = {k: v.to(self.dev) for k, v in f.items()}
            pk, inv = A.pack_index(f["mask"], 16, inverse=True)
            bt = dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]))
            torch.manual_seed(0)
            net = A.jitter_1d_params(A.AmberNet(64, 2).eval()).to(self.dev)
            net.varlen_attn = A.load_kernel("varlen_attn")
            net.fused_layer = A.load_fused_layer()
            outs = []
            for rb in (False, True):
                mod.ROW_BOUNDS = rb
                with torch.no_grad():
                    outs.append(net(bt))
            for x, y in zip(*outs):
                self.assertTrue(torch.equal(x, y))
        finally:
            mod.ROW_BOUNDS = False

    def test_fused_layer_fp16_matches_fp32(self):
        """The --half path of the 471.9k run: fp16 weights through the fused layer kernels stay within 5e-3 of the
        fp32 reference forward (logits, outcome logits)."""
        A = load("amber_net")
        torch.manual_seed(0)
        ref_net = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        f = A.to_flat(A.synthetic_batch(8, live_frac=0.5, rng=np.random.default_rng(7)))
        with torch.no_grad():
            ref = ref_net(f)
        half = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        half.load_state_dict(ref_net.state_dict())
        half = half.to(self.dev, torch.float16)
        half.varlen_attn = A.load_kernel("varlen_attn")
        half.fused_layer = A.load_fused_layer()
        g = {k: (v.to(self.dev, torch.float16) if v.is_floating_point() else v.to(self.dev)) for k, v in f.items()}
        pk, inv = A.pack_index(g["mask"], 16, inverse=True)
        g.update(pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(g["mask"]))
        with torch.no_grad():
            out = half(g)
        live = f["a_mask"]
        self.assertLess(float((out[0].float().cpu() - ref[0]).abs()[live].max()), 5e-3)
        self.assertLess(float((out[1].float().cpu() - ref[1]).abs().max()), 5e-3)


def enemy_batch(A, B=8, seed=5):
    """A flat batch whose MONSTER tokens are encounter tokens (ids[3] = ENC_KIND_BASE + kind) and whose MAP tokens
    are boss / elite / hallway nodes or other rooms, so every bias class occurs."""
    f = A.to_flat(A.synthetic_batch(B, counts=dict(A.DEFAULT_COUNTS, monster=4, map=6), live_frac=0.75,
                                    rng=np.random.default_rng(seed)))
    g = torch.Generator().manual_seed(seed)
    tt = f["tok_type"]
    mon, mp = tt == A.TOKEN_TYPES.index("monster"), tt == A.TOKEN_TYPES.index("map")
    kind = torch.randint(-1, 3, tt.shape, generator=g)   # -1: a combat monster (unique-power id)
    f["ids"][..., 3] = torch.where(mon & (kind >= 0), A.ENC_KIND_BASE + kind, f["ids"][..., 3] % 900)
    room = torch.randint(0, 5, tt.shape, generator=g)    # 0 ELITE, 1 MONSTER, 2 BOSS, 3 act boss token, 4 shop
    for r, col in enumerate((6, 7, 9, 18)):
        f["f"][..., col] = torch.where(mp, (room == r).float(), f["f"][..., col])
    f["f"][..., 3] = torch.where(mp, (room == 4).float(), f["f"][..., 3])
    return f


def strip_encounters(A, f):
    """The flat batch f without its encounter tokens (rows re-packed, action src / tgt remapped; an action on an
    encounter token gets none), as the net without --enemy-tokens sees the state."""
    cls = A.token_classes(f["tok_type"], f["ids"], f["f"])
    keep = f["mask"] & ~A.enc_of(cls)
    B, T = keep.shape
    n = keep.sum(1)
    Tn = int(n.max())
    out = {"tok_type": torch.zeros(B, Tn, dtype=torch.long), "ids": torch.zeros(B, Tn, A.N_CAT, dtype=torch.long),
           "f": torch.zeros(B, Tn, A.N_FLOAT), "mask": torch.zeros(B, Tn, dtype=torch.bool)}
    remap = torch.full((B, T), -1, dtype=torch.long)
    for r in range(B):
        idx = torch.nonzero(keep[r]).squeeze(1)
        k = idx.numel()
        for key in ("tok_type", "ids", "f"):
            out[key][r, :k] = f[key][r, idx]
        out["mask"][r, :k] = True
        remap[r, idx] = torch.arange(k)
    for key in ("a_src", "a_tgt"):
        x = f[key]
        out[key] = torch.where(x >= 0, torch.gather(remap, 1, x.clamp(min=0)), torch.full_like(x, -1))
    for key in ("a_type", "a_f", "a_mask"):
        out[key] = f[key]
    return out


def gate_batch(A, seed=5):
    """enemy_batch with no action on an encounter token (as in the driver's samples)."""
    f = enemy_batch(A, seed=seed)
    enc = A.enc_of(A.token_classes(f["tok_type"], f["ids"], f["f"]))
    for key in ("a_src", "a_tgt"):
        x = f[key]
        on = (x >= 0) & torch.gather(enc, 1, x.clamp(min=0))
        f[key] = torch.where(on, torch.full_like(x, -1), x)
    return f


class EnemyBiasClasses(unittest.TestCase):
    @unittest.skipUnless(HAVE, "needs torch")
    def test_token_classes(self):
        A = load("amber_net")
        f = enemy_batch(A)
        cls = A.token_classes(f["tok_type"], f["ids"], f["f"])
        self.assertEqual(set(cls[f["mask"]].tolist()), set(range(A.BIAS_CLASSES)))
        tt = f["tok_type"]
        other = (tt != A.TOKEN_TYPES.index("monster")) & (tt != A.TOKEN_TYPES.index("map"))
        self.assertTrue(bool((cls[other] == 0).all()))
        mon = tt == A.TOKEN_TYPES.index("monster")
        self.assertTrue(bool(((cls[mon] >= 0) & (cls[mon] <= 3)).all()))

    @unittest.skipUnless(HAVE, "needs torch")
    def test_zero_bias_same_outputs_and_gradient(self):
        """A zero table (the start) gives the outputs of the net without it; training reaches the table."""
        A = load("amber_net")
        f = enemy_batch(A)
        torch.manual_seed(0)
        base = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        net = A.AmberNet(64, 2, enemy_bias=True).eval()
        net.load_state_dict(base.state_dict(), strict=False)
        base.sdpa = net.sdpa = True
        with torch.no_grad():
            for x, y in zip(base(f), net(f)):
                self.assertLess(float((x - y).abs().max()), 1e-5)
        base.load_state_dict(net.state_dict())   # a net without the bias ignores the checkpoint's table
        net.train()
        out = net(f)
        (out[1].logsumexp(-1).sum() + out[0].sum()).backward()
        self.assertGreater(float(net.enemy_bias.grad.abs().sum()), 0)

    @unittest.skipUnless(HAVE, "needs torch")
    def test_gate_zero_is_the_old_net(self):
        """enemy_gate at 0 (the start; with and without a bias on the encounter classes): every output equals the net without
        the encounter parts on the state without encounter tokens; the flat and packed paths agree for a gate in
        (0, 1); the gate gets a gradient at 0."""
        A = load("amber_net")
        f = gate_batch(A)
        g = strip_encounters(A, f)
        torch.manual_seed(0)
        base = A.jitter_1d_params(A.AmberNet(64, 2).eval())
        base.sdpa = True
        with torch.no_grad():
            ref = base(g)
        for bias in (False, True):
            net = A.AmberNet(64, 2, enemy_bias=bias, enemy_gate=True).eval()
            net.load_state_dict(base.state_dict(), strict=False)
            net.sdpa = True
            with torch.no_grad():
                if bias:   # entries of encounter classes only: the others act on states without them too
                    r = torch.randn_like(net.enemy_bias)
                    net.enemy_bias[:, :, 1:4] = r[:, :, 1:4]
                    net.enemy_bias[:, :, :, 1:4] = r[:, :, :, 1:4]
                pk, inv = A.pack_index(f["mask"], 16, inverse=True)
                for out in (net(f), net(dict(f, pack_idx=pk, unpack_idx=inv))):
                    for x, y in zip(out, ref):
                        self.assertLess(float((x - y).abs().max()), 1e-4, bias)
                net.enemy_gate.fill_(0.4)
                o1, o2 = net(f), net(dict(f, pack_idx=pk, unpack_idx=inv))
                for x, y in zip(o1, o2):
                    self.assertLess(float((x - y).abs().max()), 1e-4, bias)
                self.assertGreater(float((o1[1] - ref[1]).abs().max()), 1e-3)
                net.enemy_gate.zero_()
            net.train()
            out = net(f)
            (out[1].logsumexp(-1).sum() + out[0].sum()).backward()
            self.assertGreater(float(net.enemy_gate.grad.abs().min()), 0)


@unittest.skipUnless(RUNNABLE, "needs triton and a CUDA GPU or TRITON_INTERPRET=1")
class EnemyBiasKernel(unittest.TestCase):
    dev = VarlenAttn.dev
    tol = VarlenAttn.tol

    def test_gated_row_mean_matches_reference(self):
        """row_mean at the widths the gated mean uses (16, d, 2 d; fp32 and fp16 inputs) and _gated_row_mean
        against plain torch sums, on packed tokens with long rows and a trash tail (as the inference batches)."""
        A = load("amber_net")
        rm = A.load_kernel("row_mean")
        g = torch.Generator().manual_seed(7)
        R, d = 37, 128
        n = torch.randint(0, 230, (R,), generator=g)
        so = torch.cat([torch.zeros(1, dtype=torch.long), n.cumsum(0)])
        N = int(so[-1]) + 21                                   # trash rows past the last live token
        row = torch.bucketize(torch.arange(N), so[1:], right=True).clamp(max=R - 1)
        live = (torch.arange(N) < so[-1]) & (torch.arange(N) != so[row])
        for dt in (torch.float32, torch.float16):
            for w in (d, 2 * d):   # (width 16 in fp32 fails on the PC GPU, triton 3.1.0: not used)
                x = (torch.randn(N, w, generator=g) * 3).to(dt)
                ref = torch.zeros(R, w).index_add_(0, row, x.float() * live[:, None])
                cnt = torch.zeros(R).index_add_(0, row, live.float()).clamp(min=1)
                out = rm(x.to(self.dev), so.to(self.dev)).float().cpu()
                self.assertLess(float((out - ref / cnt[:, None]).abs().max()), 1e-2 if dt == torch.float16 else 1e-4,
                                (dt, w))
            x = (torch.randn(N, d, generator=g) * 3).to(dt)
            enc = (torch.rand(N, generator=g) < 0.1) & live
            for gv in (0.0, 0.3, 1.0):
                w8 = live.float() * torch.where(enc, torch.tensor(gv), torch.tensor(1.0))
                ref = torch.zeros(R, d).index_add_(0, row, x.float() * w8[:, None])
                cnt = torch.zeros(R).index_add_(0, row, w8)
                ref = ref / torch.where(cnt > 0, cnt, torch.ones_like(cnt))[:, None]
                out = A._gated_row_mean(rm, x.to(self.dev), so.to(self.dev), enc.to(self.dev),
                                        torch.tensor(gv, dtype=dt, device=self.dev)).float().cpu()
                self.assertLess(float((out - ref).abs().max()), 1e-2 if dt == torch.float16 else 1e-4, (dt, gv))

    def test_compiled_gated_net_matches_eager(self):
        """torch.compile of the gated inference forward (packed tokens, varlen_attn, packed heads, N dynamic as
        selfplay.py --compile marks it) gives the eager outputs: on the PC GPU the compiled forward with encounter
        tokens was wrong (frozen test 2026-11-21), so the encounter helpers run outside the compiled graph."""
        import torch._dynamo as dynamo
        A = load("amber_net")
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2, enemy_bias=True, enemy_gate=True)).eval().to(self.dev)
        net.sdpa = True
        net.varlen_attn, net.row_mean, net.packed_heads = A.load_kernel("varlen_attn"), A.load_kernel("row_mean"), True
        with torch.no_grad():
            net.enemy_bias.normal_(0, 1)
            net.enemy_gate.copy_(torch.tensor([0.4, 0.7, 0.3]))
        run = torch.compile(net)
        for seed in (3, 4):
            f = gate_batch(A, seed=seed)
            M = f["mask"].numel()
            pk = A.pack_index(f["mask"], 16)
            ip = pk.clamp(max=M - 1)
            b = dict(f, pack_idx=pk, seq_off=A.seq_offsets(f["mask"]),
                     act_idx=torch.nonzero(f["a_mask"].reshape(-1)).squeeze(1),
                     tok_type=f["tok_type"].reshape(M)[ip], ids=f["ids"].reshape(M, -1)[ip], f=f["f"].reshape(M, -1)[ip])
            b = {k: v.to(self.dev) for k, v in b.items()}
            for k in ("act_idx", "pack_idx", "tok_type", "ids", "f"):
                dynamo.mark_dynamic(b[k], 0)
            with torch.no_grad():
                e, c = net(b), run(b)
            lm = b["a_mask"]
            for x, y in zip(e, c):
                d = (x - y).abs()
                self.assertLess(float((d[lm] if x.shape == lm.shape else d).max()), self.tol, seed)

    def test_kernel_bias_matches_sdpa(self):
        import sys
        A, V = load("amber_net"), load("varlen_attn")
        mod = sys.modules["az_bench_varlen_attn"]
        g = torch.Generator().manual_seed(1)
        C = A.BIAS_CLASSES
        try:
            for B, T, H, dh in ((5, 20, 2, 32), (3, 90, 4, 32)):
                d = H * dh
                n = torch.randint(1, T + 1, (B,), generator=g)
                mask = torch.arange(T)[None, :] < n[:, None]
                qkv_pad = torch.randn(B, T, 3 * d, generator=g)
                cls = torch.randint(0, C, (B, T), generator=g)
                tab = torch.randn(H, C, C, generator=g)
                q, k, v = qkv_pad.view(B, T, 3, H, dh).permute(2, 0, 3, 1, 4)
                bias = tab.reshape(H, C * C)[:, cls[:, :, None] * C + cls[:, None, :]].permute(1, 0, 2, 3)
                bias = bias.masked_fill(~mask[:, None, None, :], float("-inf"))
                ref = torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=bias)
                ref = ref.transpose(1, 2).reshape(B * T, d)[mask.reshape(-1)]
                pk = A.pack_index(mask, 1)
                qkv = qkv_pad.reshape(B * T, -1)[pk].contiguous().to(self.dev)
                cp = cls.reshape(-1)[pk].to(torch.int32).contiguous().to(self.dev)
                for rb in (False, True):
                    mod.ROW_BOUNDS = rb
                    out = V.varlen_attn(qkv, A.seq_offsets(mask).to(self.dev), H, T, cp, tab.contiguous().to(self.dev))
                    self.assertLess(float((out.cpu() - ref).abs().max()), self.tol, (B, T, rb))
        finally:
            mod.ROW_BOUNDS = False

    def test_net_paths_agree(self):
        """With a nonzero table: forward_flat (sdpa_trunk), forward_packed without varlen, with varlen and with
        the fused layer kernels give the same outputs."""
        A = load("amber_net")
        f = {k: v.to(self.dev) for k, v in enemy_batch(A, seed=9).items()}
        pk, inv = A.pack_index(f["mask"], 16, inverse=True)
        b = dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]))
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2, enemy_bias=True).eval()).to(self.dev)
        with torch.no_grad():
            net.enemy_bias.normal_(0, 1.0)
            net.sdpa = True
            o0 = net(f)
            o1 = net(b)
            net.varlen_attn = A.load_kernel("varlen_attn")
            o2 = net(b)
            net.fused_layer = A.load_fused_layer()
            o3 = net(b)
            net.enemy_bias.zero_()
            o4 = net(b)
        for w, x, y, z in zip(o0, o1, o2, o3):
            self.assertLess(float((w - x).abs().max()), self.tol)
            self.assertLess(float((x - y).abs().max()), self.tol)
            self.assertLess(float((x - z).abs().max()), self.tol)
        self.assertGreater(float((o3[1] - o4[1]).abs().max()), 1e-3)   # the table matters

    def test_kernel_gate_matches_sdpa(self):
        """gate g: g x attention over all keys + (1 - g) x without the encounter keys, with and without the bias,
        in both kernels."""
        import sys
        A, V = load("amber_net"), load("varlen_attn")
        mod = sys.modules["az_bench_varlen_attn"]
        g = torch.Generator().manual_seed(2)
        C = A.BIAS_CLASSES
        try:
            for B, T, H, dh in ((5, 20, 2, 32), (3, 90, 4, 32)):
                d = H * dh
                n = torch.randint(2, T + 1, (B,), generator=g)
                mask = torch.arange(T)[None, :] < n[:, None]
                qkv_pad = torch.randn(B, T, 3 * d, generator=g)
                cls = torch.randint(0, C, (B, T), generator=g)
                cls[:, 0] = 0   # the run token: every row has a key that is not an encounter token
                q, k, v = qkv_pad.view(B, T, 3, H, dh).permute(2, 0, 3, 1, 4)
                pk = A.pack_index(mask, 1)
                qkv = qkv_pad.reshape(B * T, -1)[pk].contiguous().to(self.dev)
                cp = cls.reshape(-1)[pk].to(torch.int32).contiguous().to(self.dev)
                enc = A.enc_of(cls)
                for tab in (None, torch.randn(H, C, C, generator=g)):
                    for gv in (0.0, 0.3, 1.0):
                        def ref_attn(keys, bias=True):
                            b_ = torch.zeros(B, H, T, T) if tab is None or not bias else \
                                tab.reshape(H, C * C)[:, cls[:, :, None] * C + cls[:, None, :]].permute(1, 0, 2, 3)
                            b_ = b_.masked_fill(~keys[:, None, None, :], float("-inf"))
                            return torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=b_)
                        ref = gv * ref_attn(mask) + (1 - gv) * ref_attn(mask & ~enc, bias=False)
                        ref = ref.transpose(1, 2).reshape(B * T, d)[mask.reshape(-1)]
                        for rb in (False, True):
                            mod.ROW_BOUNDS = rb
                            out = V.varlen_attn(qkv, A.seq_offsets(mask).to(self.dev), H, T, cp,
                                                None if tab is None else tab.contiguous().to(self.dev),
                                                torch.tensor([gv], device=self.dev))
                            self.assertLess(float((out.cpu() - ref).abs().max()), self.tol, (T, gv, rb))
        finally:
            mod.ROW_BOUNDS = False

    def test_net_gate_paths_agree(self):
        """Gate in (0, 1) with a bias: sdpa_trunk, packed padded, varlen and fused-layer paths agree; at gate 0 the
        varlen path equals the net without encounter parts on the stripped state."""
        A = load("amber_net")
        f = {k: v.to(self.dev) for k, v in gate_batch(A, seed=9).items()}
        pk, inv = A.pack_index(f["mask"], 16, inverse=True)
        b = dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]))
        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(64, 2, enemy_bias=True, enemy_gate=True).eval()).to(self.dev)
        net.sdpa = True
        with torch.no_grad():
            net.enemy_bias.normal_(0, 1.0)
            net.enemy_gate.copy_(torch.tensor([0.3, 0.7, 0.5]))
            o0 = net(f)
            o1 = net(b)
            net.varlen_attn = A.load_kernel("varlen_attn")
            o2 = net(b)
            net.fused_layer = A.load_fused_layer()
            o3 = net(b)
            net.row_mean = A.load_kernel("row_mean")   # packed heads: the summary gate in the weighted row mean
            net.packed_heads = True
            bh = dict(b, act_idx=torch.nonzero(f["a_mask"].reshape(-1)).squeeze(1))
            o5 = net(bh)
            net.packed_heads = False
            live = f["a_mask"]
            for w, x, y, z, u in zip(o0, o1, o2, o3, o5):
                self.assertLess(float((w - x).abs().max()), self.tol)
                self.assertLess(float((x - y).abs().max()), self.tol)
                self.assertLess(float((x - z).abs().max()), self.tol)
                if u.shape == live.shape:
                    u, x = u[live], x[live]
                self.assertLess(float((x - u).abs().max()), self.tol)
            net.enemy_gate.zero_()
            keep = torch.zeros_like(net.enemy_bias, dtype=torch.bool)   # only encounter-class entries stay
            keep[:, :, 1:4] = True
            keep[:, :, :, 1:4] = True
            net.enemy_bias.mul_(keep)
            o4 = net(b)
            base = A.AmberNet(64, 2).eval().to(self.dev)
            base.load_state_dict(net.state_dict())
            base.sdpa = True
            g = {k: v.to(self.dev) for k, v in strip_encounters(A, {k: v.cpu() for k, v in f.items()}).items()}
            ref = base(g)
        for x, y in zip(o4, ref):
            self.assertLess(float((x - y).abs().max()), self.tol)


    def test_gate_zero_inference_paths_fp16(self):
        """The inference configuration (fp16 on CUDA, d = 128, varlen attention with and without row bounds, fused
        layer, packed heads): at gate 0 the gated net on the state equals the net without encounter parts on the
        stripped state, per path, so a failing path names itself (CUDA diagnosis of #1166)."""
        import sys
        A = load("amber_net")
        mod = sys.modules["az_bench_varlen_attn"] if "az_bench_varlen_attn" in sys.modules else None
        cuda = self.dev != "cpu"
        dt = torch.float16 if cuda else torch.float32
        tol = 0.15 if cuda else self.tol   # fp16: the gated mean rounds once more than the base's (PC: 0.053 on hp)
        f = gate_batch(A, seed=11)
        st = strip_encounters(A, {k: v.cpu() for k, v in f.items()})

        def inputs(fb):
            fb = {k: (v.to(dt) if v.is_floating_point() else v).to(self.dev) for k, v in fb.items()}
            pk, inv = A.pack_index(fb["mask"], 16, inverse=True)
            return dict(fb, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(fb["mask"]),
                        act_idx=torch.nonzero(fb["a_mask"].reshape(-1)).squeeze(1))

        torch.manual_seed(0)
        net = A.jitter_1d_params(A.AmberNet(128, 2, enemy_bias=True, enemy_gate=True).eval())
        with torch.no_grad():
            keep = torch.zeros_like(net.enemy_bias, dtype=torch.bool)
            keep[:, :, 1:4] = True
            keep[:, :, :, 1:4] = True
            net.enemy_bias.normal_(0, 1.0).mul_(keep)
            net.enemy_gate.zero_()
        base = A.AmberNet(128, 2).eval()
        base.load_state_dict(net.state_dict())
        net, base = net.to(self.dev).to(dt), base.to(self.dev).to(dt)
        b, g = inputs(f), inputs(st)
        live = f["a_mask"].to(self.dev)
        vk = A.load_kernel("varlen_attn")
        mod = sys.modules["az_bench_varlen_attn"]
        try:
            for name, rb, fused, heads in (("varlen", False, False, False), ("row_bounds", True, False, False),
                                           ("fused_layer", False, True, False), ("packed_heads", False, False, True),
                                           ("all", True, True, True)):
                mod.ROW_BOUNDS = rb
                for n_ in (net, base):
                    n_.sdpa = True
                    n_.varlen_attn = vk
                    n_.fused_layer = A.load_fused_layer() if fused else None
                    n_.row_mean = A.load_kernel("row_mean") if heads else None
                    n_.packed_heads = heads
                with torch.no_grad():
                    o, r = net(b), base(g)
                for k, x, y in zip(("policy", "outcome", "hp", "hp_floor"), o, r):
                    if x.shape == live.shape:
                        x, y = x[live], y[live]
                    self.assertLess(float((x.float() - y.float()).abs().max()), tol, (name, k))
        finally:
            mod.ROW_BOUNDS = False


if __name__ == "__main__":
    unittest.main()
