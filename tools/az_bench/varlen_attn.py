"""Variable-length self-attention on packed tokens for the stage 0 throughput bench (AmberNet.forward_packed).

The packed axis holds each row's live tokens contiguously (pack_index lists live slots in row-major order), so row r
owns packed rows seq_off[r] .. seq_off[r + 1]. One program per (row, head, block of BM queries) runs a
FlashAttention-style loop over that row's keys in blocks of BN with an online fp32 softmax and writes the output
back in the packed layout. Nothing is padded: no unpack gather, no [B, T] copy of q / k / v, no masked keys.

Input qkv [N, 3 d] as nn.MultiheadAttention's in_proj produces it (q | k | v, head h at columns h * dh .. of each).
Output [N, d] in the layout out_proj expects. Packed rows past seq_off[-1] (bucket padding) are not written.
Same math as scaled_dot_product_attention with a key padding mask up to float rounding (tests/test_varlen_attn.py,
TRITON_INTERPRET=1 on a CPU).
"""

import os

import torch
import triton
import triton.language as tl


@triton.jit
def _attn_kernel(QKV, O, OFF, scale, D: tl.constexpr, DH: tl.constexpr, BM: tl.constexpr, BN: tl.constexpr,
                 MAXLEN: tl.constexpr):
    r = tl.program_id(0)
    h = tl.program_id(1)
    qb = tl.program_id(2)
    start = tl.load(OFF + r)
    n = tl.load(OFF + r + 1) - start
    offs_m = qb * BM + tl.arange(0, BM)
    offs_d = tl.arange(0, DH)
    qmask = offs_m < n
    q = tl.load(QKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
    m_i = tl.full([BM], float("-inf"), tl.float32)
    l_i = tl.zeros([BM], tl.float32)
    acc = tl.zeros([BM, DH], tl.float32)
    for k0 in range(0, MAXLEN, BN):   # static bound (the batch's token bucket); keys past n are masked
        offs_n = k0 + tl.arange(0, BN)
        kmask = offs_n < n
        k = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + D + h * DH + offs_d[:, None], mask=kmask[None, :],
                    other=0.0)
        s = tl.dot(q, k) * scale
        s = tl.where(kmask[None, :], s, float("-inf"))
        m_new = tl.maximum(tl.maximum(m_i, tl.max(s, 1)), -1e30)   # finite even for a block with no live key
        p = tl.exp(s - m_new[:, None])
        alpha = tl.exp(m_i - m_new)
        l_i = l_i * alpha + tl.sum(p, 1)
        v = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :], mask=kmask[:, None],
                    other=0.0)
        acc = acc * alpha[:, None] + tl.dot(p.to(v.dtype), v)
        m_i = m_new
    acc = acc / l_i[:, None]
    tl.store(O + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], acc.to(O.dtype.element_ty),
             mask=qmask[:, None])


@torch.library.custom_op("azbench::varlen_attn", mutates_args=())
def _varlen_attn_op(qkv: torch.Tensor, seq_off: torch.Tensor, heads: int, max_len: int) -> torch.Tensor:
    N, D3 = qkv.shape
    D = D3 // 3
    out = qkv.new_empty(N, D)   # bucket-padding rows past seq_off[-1] stay unwritten; nothing reads them
    R = seq_off.shape[0] - 1
    BM = BN = 32 if max_len <= 32 else int(os.environ.get("AZ_ATTN_BLOCK", "64"))
    _attn_kernel[(R, heads, triton.cdiv(max_len, BM))](qkv, out, seq_off, (D // heads) ** -0.5, D=D, DH=D // heads,
                                                       BM=BM, BN=BN, MAXLEN=triton.cdiv(max_len, BN) * BN,
                                                       num_warps=int(os.environ.get("AZ_ATTN_WARPS", "4")))
    return out


@_varlen_attn_op.register_fake
def _(qkv, seq_off, heads, max_len):
    return qkv.new_empty(qkv.shape[0], qkv.shape[1] // 3)


def varlen_attn(qkv, seq_off, heads, max_len):
    """qkv [N, 3 d] contiguous, seq_off [R + 1] int32 / int64 row starts in the packed axis, max_len >= the longest
    row. Returns the attention output [N, d]."""
    return _varlen_attn_op(qkv, seq_off, heads, max_len)
