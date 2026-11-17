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
def _ffn_kernel(X, OUT, LNW, LNB, W1, B1, W2, B2, N, eps,
                D: tl.constexpr, HID: tl.constexpr, BM: tl.constexpr, BH: tl.constexpr):
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
    out = torch.empty_like(x)
    _ffn_kernel[(triton.cdiv(N, bm),)](x, out, lnw, lnb, w1, b1, w2, b2, N, eps, D=D, HID=w1.shape[0], BM=bm, BH=bh)
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
