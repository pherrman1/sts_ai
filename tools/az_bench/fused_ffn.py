"""A fused Triton kernel for one transformer encoder layer's feed-forward half, for the stage 0 throughput bench:

    out = x + linear2(gelu(linear1(layer_norm(x))))

on packed tokens x [N, d] (AmberNet.forward_packed). One program handles BM tokens: it loads their rows, does the
LayerNorm in registers, and walks the hidden dimension in chunks of BH, so the [N, 4d] hidden activation never
reaches memory (inductor writes it twice and reads it twice: GEMM, GELU, GEMM). Accumulation is fp32; GEMM inputs are
fp16 like cuBLAS's (fp32 inputs run as TF32 on the GPU). Same math as the PyTorch layer up to float rounding (tests/test_fused_ffn.py, run with
TRITON_INTERPRET=1 on a CPU).
"""

import os

import torch
import triton
import triton.language as tl


@triton.jit
def _ffn_kernel(X, OUT, LNW, LNB, W1, B1, W2, B2, N, eps, O, WO, BO,
                D: tl.constexpr, HID: tl.constexpr, BM: tl.constexpr, BH: tl.constexpr, HAS_ATT: tl.constexpr):
    pid = tl.program_id(0)
    rows = pid * BM + tl.arange(0, BM)
    rmask = rows < N
    cols = tl.arange(0, D)
    x = tl.load(X + rows[:, None] * D + cols[None, :], mask=rmask[:, None], other=0.0).to(tl.float32)
    if HAS_ATT:   # x += out_proj(o): the attention half's output projection and residual
        o = tl.load(O + rows[:, None] * D + cols[None, :], mask=rmask[:, None], other=0.0)
        wo = tl.load(WO + cols[None, :] * D + cols[:, None])           # [D, D] = WO^T
        x = x + tl.dot(o, wo) + tl.load(BO + cols).to(tl.float32)[None, :]
    mean = tl.sum(x, 1) / D
    xc = x - mean[:, None]
    var = tl.sum(xc * xc, 1) / D
    lnw = tl.load(LNW + cols).to(tl.float32)
    lnb = tl.load(LNB + cols).to(tl.float32)
    y = (xc * (1.0 / tl.sqrt(var + eps))[:, None] * lnw[None, :] + lnb[None, :]).to(W1.dtype.element_ty)
    acc = tl.zeros([BM, D], dtype=tl.float32)
    for h0 in range(0, HID, BH):
        hc = h0 + tl.arange(0, BH)
        w1 = tl.load(W1 + hc[None, :] * D + cols[:, None])              # [D, BH] = W1[hc, :]^T (W1 is [HID, D])
        h = tl.dot(y, w1) + tl.load(B1 + hc).to(tl.float32)[None, :]
        g = 0.5 * h * (1.0 + tl.math.erf(h * 0.7071067811865476))        # exact GELU
        w2 = tl.load(W2 + cols[None, :] * HID + hc[:, None])            # [BH, D] = W2[:, hc]^T (W2 is [D, HID])
        acc += tl.dot(g.to(W2.dtype.element_ty), w2)
    out = x + acc + tl.load(B2 + cols).to(tl.float32)[None, :]
    tl.store(OUT + rows[:, None] * D + cols[None, :], out.to(OUT.dtype.element_ty), mask=rmask[:, None])


@torch.library.custom_op("azbench::fused_ffn", mutates_args=())
def _fused_ffn_op(x: torch.Tensor, lnw: torch.Tensor, lnb: torch.Tensor, w1: torch.Tensor, b1: torch.Tensor,
                  w2: torch.Tensor, b2: torch.Tensor, eps: float, bm: int, bh: int) -> torch.Tensor:
    N, D = x.shape
    assert D & (D - 1) == 0 and w1.shape[0] % bh == 0, "fused_ffn: d a power of two, 4 d a multiple of bh"
    out = torch.empty_like(x)
    _ffn_kernel[(triton.cdiv(N, bm),)](x, out, lnw, lnb, w1, b1, w2, b2, N, eps, x, w1, b1, D=D, HID=w1.shape[0],
                                       BM=bm, BH=bh, HAS_ATT=False)
    return out


@_fused_ffn_op.register_fake
def _(x, lnw, lnb, w1, b1, w2, b2, eps, bm, bh):
    return torch.empty_like(x)


def fused_ffn(x, layer, bm=None, bh=64):
    """x [N, d] contiguous (fp16 / bf16 with the layer's weights in the same dtype); layer an
    nn.TransformerEncoderLayer (norm2, linear1, linear2, exact GELU). Returns x + FFN(norm2(x)). Registered as a
    custom op so torch.compile keeps one graph around it (a bare Triton call broke the graph into eager pieces)."""
    bm = bm or int(os.environ.get("AZ_FUSED_FFN_BM", "64"))
    return _fused_ffn_op(x, layer.norm2.weight, layer.norm2.bias, layer.linear1.weight, layer.linear1.bias,
                         layer.linear2.weight, layer.linear2.bias, float(layer.norm2.eps), bm, bh)


@torch.library.custom_op("azbench::fused_out_ffn", mutates_args=())
def _fused_out_ffn_op(x: torch.Tensor, o: torch.Tensor, wo: torch.Tensor, bo: torch.Tensor, lnw: torch.Tensor,
                      lnb: torch.Tensor, w1: torch.Tensor, b1: torch.Tensor, w2: torch.Tensor, b2: torch.Tensor,
                      eps: float, bm: int, bh: int) -> torch.Tensor:
    N, D = x.shape
    assert D & (D - 1) == 0 and w1.shape[0] % bh == 0, "fused_out_ffn: d a power of two, 4 d a multiple of bh"
    out = torch.empty_like(x)
    _ffn_kernel[(triton.cdiv(N, bm),)](x, out, lnw, lnb, w1, b1, w2, b2, N, eps, o, wo, bo, D=D, HID=w1.shape[0],
                                       BM=bm, BH=bh, HAS_ATT=True)
    return out


@_fused_out_ffn_op.register_fake
def _(x, o, wo, bo, lnw, lnb, w1, b1, w2, b2, eps, bm, bh):
    return torch.empty_like(x)


def fused_out_ffn(x, o, layer, bm=None, bh=64):
    """The rest of a pre-norm encoder layer after attention, in one kernel: x1 = x + out_proj(o), returns
    x1 + FFN(norm2(x1)). x, o [N, d] contiguous in the layer's dtype; d <= 128 (out_proj's weight is one tile)."""
    bm = bm or int(os.environ.get("AZ_FUSED_FFN_BM", "64"))
    a = layer.self_attn.out_proj
    return _fused_out_ffn_op(x, o, a.weight, a.bias, layer.norm2.weight, layer.norm2.bias, layer.linear1.weight,
                             layer.linear1.bias, layer.linear2.weight, layer.linear2.bias, float(layer.norm2.eps), bm,
                             bh)


@triton.jit
def _ln_linear_kernel(X, OUT, LNW, LNB, W, B, N, eps, D: tl.constexpr, NOUT: tl.constexpr, BM: tl.constexpr,
                      BO: tl.constexpr):
    pid = tl.program_id(0)
    rows = pid * BM + tl.arange(0, BM)
    rmask = rows < N
    cols = tl.arange(0, D)
    x = tl.load(X + rows[:, None] * D + cols[None, :], mask=rmask[:, None], other=0.0).to(tl.float32)
    mean = tl.sum(x, 1) / D
    xc = x - mean[:, None]
    var = tl.sum(xc * xc, 1) / D
    lnw = tl.load(LNW + cols).to(tl.float32)
    lnb = tl.load(LNB + cols).to(tl.float32)
    y = (xc * (1.0 / tl.sqrt(var + eps))[:, None] * lnw[None, :] + lnb[None, :]).to(W.dtype.element_ty)
    for c0 in range(0, NOUT, BO):
        oc = c0 + tl.arange(0, BO)
        omask = oc < NOUT
        w = tl.load(W + oc[None, :] * D + cols[:, None], mask=omask[None, :], other=0.0)   # [D, BO] = W[oc, :]^T
        r = tl.dot(y, w) + tl.load(B + oc, mask=omask, other=0.0).to(tl.float32)[None, :]
        tl.store(OUT + rows[:, None] * NOUT + oc[None, :], r.to(OUT.dtype.element_ty),
                 mask=rmask[:, None] & omask[None, :])


@torch.library.custom_op("azbench::ln_linear", mutates_args=())
def _ln_linear_op(x: torch.Tensor, lnw: torch.Tensor, lnb: torch.Tensor, w: torch.Tensor, b: torch.Tensor, eps: float,
                  bm: int) -> torch.Tensor:
    N, D = x.shape
    out = x.new_empty(N, w.shape[0])
    _ln_linear_kernel[(triton.cdiv(N, bm),)](x, out, lnw, lnb, w, b, N, eps, D=D, NOUT=w.shape[0], BM=bm, BO=64)
    return out


@_ln_linear_op.register_fake
def _(x, lnw, lnb, w, b, eps, bm):
    return x.new_empty(x.shape[0], w.shape[0])


def ln_qkv(x, layer, bm=None):
    """norm1 + the attention's QKV projection in one kernel: x [N, d] -> qkv [N, 3 d] (in_proj layout)."""
    bm = bm or int(os.environ.get("AZ_FUSED_FFN_BM", "64"))
    a = layer.self_attn
    return _ln_linear_op(x, layer.norm1.weight, layer.norm1.bias, a.in_proj_weight, a.in_proj_bias,
                         float(layer.norm1.eps), bm)
