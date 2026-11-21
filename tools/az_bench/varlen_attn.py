"""Variable-length self-attention on packed tokens for the stage 0 throughput bench (AmberNet.forward_packed).

The packed axis holds each row's live tokens contiguously (pack_index lists live slots in row-major order), so row r
owns packed rows seq_off[r] .. seq_off[r + 1]. One program per (row, head, block of BM queries) runs a
FlashAttention-style loop over that row's keys in blocks of BN with an online fp32 softmax and writes the output
back in the packed layout. Nothing is padded: no unpack gather, no [B, T] copy of q / k / v, no masked keys.

Input qkv [N, 3 d] as nn.MultiheadAttention's in_proj produces it (q | k | v, head h at columns h * dh .. of each).
Output [N, d] in the layout out_proj expects. Packed rows past seq_off[-1] (bucket padding) are not written.
Same math as scaled_dot_product_attention with a key padding mask up to float rounding (tests/test_varlen_attn.py,
TRITON_INTERPRET=1 on a CPU).

Row bounds (2026-11-20, ROW_BOUNDS, default off): the default kernel runs every program's key loop to the batch's
token bucket (a static bound), for every row. A batch's bucket follows its longest row, so a 30-token row in a
96-token batch does four block pairs per head where it has keys and queries for one, and so does each padding row
of the row bucket. With ROW_BOUNDS the key loop ends at the row's own length and a query block past it does
nothing. The blocks left out are exactly those with no live key (they leave the running maximum, the sum and the
accumulator unchanged) or no live query (they store nothing): same output values.

Attention bias (2026-11-21, AmberNet enemy_bias, selfplay.py --enemy-map-bias): optional CLS [N] int32 token classes
and TAB [H, C, C] fp32; the score of query i and key j in head h gets TAB[h, CLS[i], CLS[j]] added after the scaling
(as an additive attn_mask of scaled_dot_product_attention).

Encounter gate (2026-11-21, AmberNet enemy_gate, selfplay.py --enemy-tokens): optional G [1] fp32 (needs CLS): the
output is g x attention over all keys (with the bias) + (1 - g) x attention without the encounter-token keys
(CLS 1..3) and without the bias. One pass:
the second softmax keeps its own running maximum, sum and accumulator (one more exp and P V product per block;
a shared maximum would leave its weights tiny, below fp16's normal range, when an encounter key scores highest).
"""

import os
from typing import Optional

import torch
import triton
import triton.language as tl


@triton.jit
def _attn_kernel(QKV, O, OFF, CLS, TAB, G, scale, D: tl.constexpr, DH: tl.constexpr, BM: tl.constexpr,
                 BN: tl.constexpr,
                 MAXLEN: tl.constexpr, HAS_BIAS: tl.constexpr, C: tl.constexpr,
                 HAS_GATE: tl.constexpr):
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
    ln = tl.zeros([BM], tl.float32)
    accn = tl.zeros([BM, DH], tl.float32)
    mn = tl.full([BM], float("-inf"), tl.float32)
    if HAS_BIAS:
        cq = tl.load(CLS + start + offs_m, mask=qmask, other=0)
    for k0 in range(0, MAXLEN, BN):   # static bound (the batch's token bucket); keys past n are masked
        offs_n = k0 + tl.arange(0, BN)
        kmask = offs_n < n
        k = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + D + h * DH + offs_d[:, None], mask=kmask[None, :],
                    other=0.0)
        s = tl.dot(q, k) * scale
        s0 = s   # without the class bias (the gate's second softmax)
        if HAS_BIAS or HAS_GATE:
            ck = tl.load(CLS + start + offs_n, mask=kmask, other=0)
        if HAS_BIAS:
            s += tl.load(TAB + h * C * C + cq[:, None] * C + ck[None, :])
        s = tl.where(kmask[None, :], s, float("-inf"))
        m_new = tl.maximum(tl.maximum(m_i, tl.max(s, 1)), -1e30)   # finite even for a block with no live key
        p = tl.exp(s - m_new[:, None])
        alpha = tl.exp(m_i - m_new)
        l_i = l_i * alpha + tl.sum(p, 1)
        v = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :], mask=kmask[:, None],
                    other=0.0)
        acc = acc * alpha[:, None] + tl.dot(p.to(v.dtype), v)
        if HAS_GATE:   # the softmax without the encounter keys, with its own running maximum
            sn = tl.where(((ck >= 1) & (ck <= 3))[None, :] | ~kmask[None, :], float("-inf"), s0)
            mn_new = tl.maximum(tl.maximum(mn, tl.max(sn, 1)), -1e30)
            pn = tl.exp(sn - mn_new[:, None])
            alphan = tl.exp(mn - mn_new)
            ln = ln * alphan + tl.sum(pn, 1)
            accn = accn * alphan[:, None] + tl.dot(pn.to(v.dtype), v)
            mn = mn_new
        m_i = m_new
    acc = acc / l_i[:, None]
    if HAS_GATE:
        g = tl.load(G)
        acc = g * acc + (1.0 - g) * (accn / ln[:, None])
    tl.store(O + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], acc.to(O.dtype.element_ty),
             mask=qmask[:, None])


@triton.jit
def _attn_kernel_rows(QKV, O, OFF, CLS, TAB, G, RF, scale, D: tl.constexpr, DH: tl.constexpr, BM: tl.constexpr,
                      BN: tl.constexpr, HAS_BIAS: tl.constexpr, C: tl.constexpr,
                      HAS_GATE: tl.constexpr, SEL: tl.constexpr):
    """_attn_kernel with the row's own bounds: the key loop ends at the row's length n (the blocks past it hold no
    live key), and a query block past n has an empty loop and stores nothing. SEL 1 / 2: only the
    rows with RF[r] == 0 / != 0 (RF: the row holds encounter tokens); the others get n = 0 (empty loops, no store)."""
    r = tl.program_id(0)
    h = tl.program_id(1)
    qb = tl.program_id(2)
    start = tl.load(OFF + r)
    n = tl.load(OFF + r + 1) - start
    if SEL != 0:
        rf = tl.load(RF + r)
        if SEL == 1:
            n = tl.where(rf == 0, n, 0)
        else:
            n = tl.where(rf != 0, n, 0)
    offs_m = qb * BM + tl.arange(0, BM)
    offs_d = tl.arange(0, DH)
    qmask = offs_m < n
    q = tl.load(QKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
    m_i = tl.full([BM], float("-inf"), tl.float32)
    l_i = tl.zeros([BM], tl.float32)
    acc = tl.zeros([BM, DH], tl.float32)
    ln = tl.zeros([BM], tl.float32)
    accn = tl.zeros([BM, DH], tl.float32)
    mn = tl.full([BM], float("-inf"), tl.float32)
    if HAS_BIAS:
        cq = tl.load(CLS + start + offs_m, mask=qmask, other=0)
    hi = n
    if qb * BM >= n:   # no live query in this block
        hi = 0
    for k0 in range(0, hi, BN):
        offs_n = k0 + tl.arange(0, BN)
        kmask = offs_n < n
        k = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + D + h * DH + offs_d[:, None], mask=kmask[None, :],
                    other=0.0)
        s = tl.dot(q, k) * scale
        s0 = s   # without the class bias (the gate's second softmax)
        if HAS_BIAS or HAS_GATE:
            ck = tl.load(CLS + start + offs_n, mask=kmask, other=0)
        if HAS_BIAS:
            s += tl.load(TAB + h * C * C + cq[:, None] * C + ck[None, :])
        s = tl.where(kmask[None, :], s, float("-inf"))
        m_new = tl.maximum(tl.maximum(m_i, tl.max(s, 1)), -1e30)
        p = tl.exp(s - m_new[:, None])
        alpha = tl.exp(m_i - m_new)
        l_i = l_i * alpha + tl.sum(p, 1)
        v = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :], mask=kmask[:, None],
                    other=0.0)
        acc = acc * alpha[:, None] + tl.dot(p.to(v.dtype), v)
        if HAS_GATE:   # the softmax without the encounter keys, with its own running maximum
            sn = tl.where(((ck >= 1) & (ck <= 3))[None, :] | ~kmask[None, :], float("-inf"), s0)
            mn_new = tl.maximum(tl.maximum(mn, tl.max(sn, 1)), -1e30)
            pn = tl.exp(sn - mn_new[:, None])
            alphan = tl.exp(mn - mn_new)
            ln = ln * alphan + tl.sum(pn, 1)
            accn = accn * alphan[:, None] + tl.dot(pn.to(v.dtype), v)
            mn = mn_new
        m_i = m_new
    acc = acc / l_i[:, None]
    if HAS_GATE:
        g = tl.load(G)
        acc = g * acc + (1.0 - g) * (accn / ln[:, None])
    tl.store(O + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], acc.to(O.dtype.element_ty),
             mask=qmask[:, None])


ROW_BOUNDS = False   # True: _attn_kernel_rows (selfplay.py --attn-row-bounds); same output values


@torch.library.custom_op("azbench::varlen_attn", mutates_args=())
def _varlen_attn_op(qkv: torch.Tensor, seq_off: torch.Tensor, heads: int, max_len: int,
                    cls: Optional[torch.Tensor] = None, tab: Optional[torch.Tensor] = None,
                    gate: Optional[torch.Tensor] = None, split_enc: bool = False) -> torch.Tensor:
    qkv, seq_off = qkv.contiguous(), seq_off.contiguous()   # the kernels index raw pointers (no-op if contiguous)
    cls = None if cls is None else cls.contiguous()
    tab = None if tab is None else tab.contiguous()
    gate = None if gate is None else gate.contiguous()
    N, D3 = qkv.shape
    D = D3 // 3
    out = qkv.new_empty(N, D)   # bucket-padding rows past seq_off[-1] stay unwritten; nothing reads them
    R = seq_off.shape[0] - 1
    BM = BN = 32 if max_len <= 32 else int(os.environ.get("AZ_ATTN_BLOCK", "64"))
    has_bias = tab is not None
    has_gate = gate is not None
    C = tab.shape[-1] if has_bias else 1
    if cls is None:   # unused pointers (HAS_BIAS / HAS_GATE are constexprs)
        cls = seq_off
    if tab is None:
        tab = qkv
    if gate is None:
        gate = qkv
    if ROW_BOUNDS:
        grid = (R, heads, triton.cdiv(max_len, BM))
        nw = int(os.environ.get("AZ_ATTN_WARPS", "4"))
        if split_enc and (has_bias or has_gate) and os.environ.get("AZ_ATTN_SPLIT_ENC", "1") != "0":
            # rows without encounter tokens (most: all combat rows) get the plain kernel, without the bias loads and
            # the gate's second softmax; the others the full one. Same values when the table has entries only for
            # pairs with an encounter class (split_enc: the caller says so, AmberNet._tab): on a row without encounter
            # tokens the bias is then 0 and both softmaxes of the gate are the same. AZ_ATTN_SPLIT_ENC=0: one
            # full launch for all rows.
            enc = ((cls >= 1) & (cls <= 3)).long()
            c = torch.cat([enc.new_zeros(1), enc.cumsum(0)])
            so = seq_off.long()
            rf = ((c[so[1:]] - c[so[:-1]]) > 0).to(torch.int32)
            _attn_kernel_rows[grid](qkv, out, seq_off, cls, tab, gate, rf, (D // heads) ** -0.5, D=D, DH=D // heads,
                                    BM=BM, BN=BN, HAS_BIAS=False, C=C, HAS_GATE=False, SEL=1, num_warps=nw)
            _attn_kernel_rows[grid](qkv, out, seq_off, cls, tab, gate, rf, (D // heads) ** -0.5, D=D, DH=D // heads,
                                    BM=BM, BN=BN, HAS_BIAS=has_bias, C=C, HAS_GATE=has_gate, SEL=2, num_warps=nw)
            return out
        _attn_kernel_rows[grid](qkv, out, seq_off, cls, tab, gate, seq_off, (D // heads) ** -0.5,
                                D=D, DH=D // heads, BM=BM, BN=BN,
                                HAS_BIAS=has_bias, C=C, HAS_GATE=has_gate, SEL=0, num_warps=nw)
        return out
    _attn_kernel[(R, heads, triton.cdiv(max_len, BM))](qkv, out, seq_off, cls, tab, gate, (D // heads) ** -0.5, D=D,
                                                       DH=D // heads, BM=BM, BN=BN,
                                                       MAXLEN=triton.cdiv(max_len, BN) * BN, HAS_BIAS=has_bias, C=C,
                                                       HAS_GATE=has_gate,
                                                       num_warps=int(os.environ.get("AZ_ATTN_WARPS", "4")))
    return out


@_varlen_attn_op.register_fake
def _(qkv, seq_off, heads, max_len, cls=None, tab=None, gate=None, split_enc=False):
    return qkv.new_empty(qkv.shape[0], qkv.shape[1] // 3)


def varlen_attn(qkv, seq_off, heads, max_len, cls=None, tab=None, gate=None, split_enc=False):
    """qkv [N, 3 d] contiguous, seq_off [R + 1] int32 / int64 row starts in the packed axis, max_len >= the longest
    row. Optional attention bias: cls [N] int32 token classes, tab [heads, C, C] fp32 contiguous. Returns the
    attention output [N, d]. Optional encounter gate: gate [1] fp32 (needs cls; tab may be None). split_enc: tab
    is 0 on every pair without an encounter class (1..3), so with ROW_BOUNDS the rows without encounter tokens run
    the plain kernel (same values, less work)."""
    if (tab is not None or gate is not None) and cls is None:
        raise ValueError("varlen_attn: tab / gate need cls")
    return _varlen_attn_op(qkv, seq_off, heads, max_len, cls, tab, gate, split_enc)
