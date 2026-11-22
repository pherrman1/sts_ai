"""Differentiable varlen attention with a token-class bias table, for training (AmberNet enemy_train_kernel,
selfplay.py --enemy-train-kernel).

Same layout as varlen_attn.py: qkv [N, 3 d] packed tokens (row r's live tokens are packed rows seq_off[r] ..
seq_off[r + 1]), cls [N] int32 token classes, tab [H, C, C] fp32: the score of query i and key j in head h gets
tab[h, cls[i], cls[j]] added after the scaling. Without the padded [B, T] layout the rows attend over their own
length only (the padded trainer's attention costs the batch's longest row squared on every row).

rf [R] int32 (optional): rows with rf[r] == 0 have a zero bias (the caller says so: AmberNet._tab has entries only
for pairs with an encounter class) and run the plain kernels; rows_only (optional): only the rows with rf[r] != 0
are computed (the others get zero outputs and zero gradients) -- the gate's second part.

Forward: flash attention per (row, head, query block) with the row's own key bounds, saving the log-sum-exp.
Backward (flash attention 2): Delta = rowsum(dO * O); one kernel per (row, head, key block) for dK, dV and the
table gradient (per tile onehot(cls_q)^T dS onehot(cls_k), fp32, atomically added), one per (row, head, query block)
for dQ. fp32 accumulation; q / k / v and the P V, dS K products in the input dtype (fp16 / bf16).
Tests: tests/test_varlen_attn_train.py (TRITON_INTERPRET=1 on a CPU).
"""

import os

import torch
import triton
import triton.language as tl


@triton.jit
def _bias(TAB, h, cq, ck, C: tl.constexpr):
    # per class c: the query's table entry for key class c on the keys of that class (no [BM, BN] gather)
    b = tl.where((ck == 0)[None, :], tl.load(TAB + h * C * C + cq * C)[:, None], 0.0)
    for c in tl.static_range(1, C):
        b += tl.where((ck == c)[None, :], tl.load(TAB + h * C * C + cq * C + c)[:, None], 0.0)
    return b


@triton.jit
def _bias_t(TAB, h, cq, ck, C: tl.constexpr):
    # _bias transposed: [keys, queries]
    b = tl.where((ck == 0)[:, None], tl.load(TAB + h * C * C + cq * C)[None, :], 0.0)
    for c in tl.static_range(1, C):
        b += tl.where((ck == c)[:, None], tl.load(TAB + h * C * C + cq * C + c)[None, :], 0.0)
    return b


@triton.jit
def _row_bounds(OFF, RF, r, SEL: tl.constexpr):
    start = tl.load(OFF + r)
    n = tl.load(OFF + r + 1) - start
    if SEL != 0:
        rf = tl.load(RF + r)
        if SEL == 1:
            n = tl.where(rf == 0, n, 0)
        else:
            n = tl.where(rf != 0, n, 0)
    return start, n


@triton.jit
def _fwd(QKV, O, LSE, OFF, CLS, TAB, RF, scale, H: tl.constexpr, D: tl.constexpr, DH: tl.constexpr,
         BM: tl.constexpr, BN: tl.constexpr, HAS_BIAS: tl.constexpr, C: tl.constexpr, SEL: tl.constexpr,
         PREC: tl.constexpr):
    r = tl.program_id(0)
    h = tl.program_id(1)
    qb = tl.program_id(2)
    start, n = _row_bounds(OFF, RF, r, SEL)
    offs_m = qb * BM + tl.arange(0, BM)
    offs_d = tl.arange(0, DH)
    qmask = offs_m < n
    q = tl.load(QKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
    m_i = tl.full([BM], float("-inf"), tl.float32)
    l_i = tl.zeros([BM], tl.float32)
    acc = tl.zeros([BM, DH], tl.float32)
    if HAS_BIAS:
        cq = tl.load(CLS + start + offs_m, mask=qmask, other=0)
    hi = n
    if qb * BM >= n:
        hi = 0
    for k0 in range(0, hi, BN):
        offs_n = k0 + tl.arange(0, BN)
        kmask = offs_n < n
        k = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + D + h * DH + offs_d[:, None], mask=kmask[None, :],
                    other=0.0)
        s = tl.dot(q, k, input_precision=PREC).to(tl.float32) * scale
        if HAS_BIAS:
            ck = tl.load(CLS + start + offs_n, mask=kmask, other=0)
            s += _bias(TAB, h, cq, ck, C)
        s = tl.where(kmask[None, :], s, float("-inf"))
        m_new = tl.maximum(tl.maximum(m_i, tl.max(s, 1)), -1e30)
        p = tl.exp(s - m_new[:, None])
        alpha = tl.exp(m_i - m_new)
        l_i = l_i * alpha + tl.sum(p, 1)
        v = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :], mask=kmask[:, None],
                    other=0.0)
        acc = acc * alpha[:, None] + tl.dot(p.to(v.dtype), v, input_precision=PREC)
        m_i = m_new
    l_safe = tl.where(l_i > 0, l_i, 1.0)
    tl.store(O + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], (acc / l_safe[:, None]).to(O.dtype.element_ty),
             mask=qmask[:, None])
    tl.store(LSE + (start + offs_m) * H + h, m_i + tl.log(l_safe), mask=qmask)


@triton.jit
def _bwd_kv(QKV, DO, LSE, DELTA, DQKV, OFF, CLS, TAB, DTAB, RF, scale, H: tl.constexpr, D: tl.constexpr,
            DH: tl.constexpr, BM: tl.constexpr, BN: tl.constexpr, HAS_BIAS: tl.constexpr, NEED_DTAB: tl.constexpr,
            C: tl.constexpr, SEL: tl.constexpr,
         PREC: tl.constexpr):
    # everything in the transposed orientation ([keys, queries] tiles), operands loaded in the layout each product
    # needs, without tl.trans: 0d85b4d5 (tl.trans operands) gave wrong fp32 gradients on the PC GPU (triton 3.1.0)
    r = tl.program_id(0)
    h = tl.program_id(1)
    kb = tl.program_id(2)
    start, n = _row_bounds(OFF, RF, r, SEL)
    offs_n = kb * BN + tl.arange(0, BN)
    offs_d = tl.arange(0, DH)
    kmask = offs_n < n
    k = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + D + h * DH + offs_d[None, :], mask=kmask[:, None],
                other=0.0)                                                 # [BN, DH]
    v = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :], mask=kmask[:, None],
                other=0.0)                                                 # [BN, DH]
    dk = tl.zeros([BN, DH], tl.float32)
    dv = tl.zeros([BN, DH], tl.float32)
    if HAS_BIAS:
        ck = tl.load(CLS + start + offs_n, mask=kmask, other=0)
    if NEED_DTAB:
        offs_c = tl.arange(0, 16)
        ok16 = (offs_c[:, None] == ck[None, :]).to(tl.float32)            # [16, BN]
        dt = tl.zeros([16, 16], tl.float32)                                # [key class, query class]
    hi = n
    if kb * BN >= n:
        hi = 0
    for q0 in range(0, hi, BM):
        offs_m = q0 + tl.arange(0, BM)
        qmask = offs_m < n
        qT = tl.load(QKV + (start + offs_m)[None, :] * (3 * D) + h * DH + offs_d[:, None], mask=qmask[None, :],
                     other=0.0)                                            # [DH, BM]
        q = tl.load(QKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], mask=qmask[:, None],
                    other=0.0)                                             # [BM, DH]
        do = tl.load(DO + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
        doT = tl.load(DO + (start + offs_m)[None, :] * D + h * DH + offs_d[:, None], mask=qmask[None, :], other=0.0)
        lse = tl.load(LSE + (start + offs_m) * H + h, mask=qmask, other=0.0)
        delta = tl.load(DELTA + (start + offs_m) * H + h, mask=qmask, other=0.0)
        sT = tl.dot(k, qT, input_precision=PREC).to(tl.float32) * scale                         # [BN, BM]
        if HAS_BIAS:
            cq = tl.load(CLS + start + offs_m, mask=qmask, other=0)
            sT += _bias_t(TAB, h, cq, ck, C)
        pT = tl.where(kmask[:, None] & qmask[None, :], tl.exp(sT - lse[None, :]), 0.0)
        dv += tl.dot(pT.to(do.dtype), do, input_precision=PREC)
        dpT = tl.dot(v, doT, input_precision=PREC).to(tl.float32)                                # [BN, BM]
        dsT = pT * (dpT - delta[None, :])
        dk += tl.dot(dsT.to(q.dtype), q, input_precision=PREC)
        if NEED_DTAB:
            oq = (cq[:, None] == offs_c[None, :]).to(tl.float32)           # [BM, 16]
            dt += tl.dot(ok16, tl.dot(dsT, oq, input_precision="ieee"), input_precision="ieee")
    tl.store(DQKV + (start + offs_n)[:, None] * (3 * D) + D + h * DH + offs_d[None, :],
             (dk * scale).to(DQKV.dtype.element_ty), mask=kmask[:, None])
    tl.store(DQKV + (start + offs_n)[:, None] * (3 * D) + 2 * D + h * DH + offs_d[None, :],
             dv.to(DQKV.dtype.element_ty), mask=kmask[:, None])
    if NEED_DTAB:
        cm = offs_c < C
        # dt[key class, query class] -> DTAB[h, query class, key class]
        tl.atomic_add(DTAB + h * C * C + offs_c[None, :] * C + offs_c[:, None], dt, mask=cm[:, None] & cm[None, :])


@triton.jit
def _bwd_q(QKV, DO, LSE, DELTA, DQKV, OFF, CLS, TAB, RF, scale, H: tl.constexpr, D: tl.constexpr, DH: tl.constexpr,
           BM: tl.constexpr, BN: tl.constexpr, HAS_BIAS: tl.constexpr, C: tl.constexpr, SEL: tl.constexpr,
         PREC: tl.constexpr):
    # no tl.trans: K and V loaded transposed for the score products (see _bwd_kv)
    r = tl.program_id(0)
    h = tl.program_id(1)
    qb = tl.program_id(2)
    start, n = _row_bounds(OFF, RF, r, SEL)
    offs_m = qb * BM + tl.arange(0, BM)
    offs_d = tl.arange(0, DH)
    qmask = offs_m < n
    q = tl.load(QKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
    do = tl.load(DO + (start + offs_m)[:, None] * D + h * DH + offs_d[None, :], mask=qmask[:, None], other=0.0)
    lse = tl.load(LSE + (start + offs_m) * H + h, mask=qmask, other=0.0)
    delta = tl.load(DELTA + (start + offs_m) * H + h, mask=qmask, other=0.0)
    dq = tl.zeros([BM, DH], tl.float32)
    if HAS_BIAS:
        cq = tl.load(CLS + start + offs_m, mask=qmask, other=0)
    hi = n
    if qb * BM >= n:
        hi = 0
    for k0 in range(0, hi, BN):
        offs_n = k0 + tl.arange(0, BN)
        kmask = offs_n < n
        kT = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + D + h * DH + offs_d[:, None], mask=kmask[None, :],
                     other=0.0)                                            # [DH, BN]
        k = tl.load(QKV + (start + offs_n)[:, None] * (3 * D) + D + h * DH + offs_d[None, :], mask=kmask[:, None],
                    other=0.0)                                             # [BN, DH]
        vT = tl.load(QKV + (start + offs_n)[None, :] * (3 * D) + 2 * D + h * DH + offs_d[:, None], mask=kmask[None, :],
                     other=0.0)                                            # [DH, BN]
        s = tl.dot(q, kT, input_precision=PREC).to(tl.float32) * scale
        if HAS_BIAS:
            ck = tl.load(CLS + start + offs_n, mask=kmask, other=0)
            s += _bias(TAB, h, cq, ck, C)
        p = tl.where(qmask[:, None] & kmask[None, :], tl.exp(s - lse[:, None]), 0.0)
        dp = tl.dot(do, vT, input_precision=PREC).to(tl.float32)
        ds = p * (dp - delta[:, None])
        dq += tl.dot(ds.to(k.dtype), k, input_precision=PREC)
    tl.store(DQKV + (start + offs_m)[:, None] * (3 * D) + h * DH + offs_d[None, :], (dq * scale).to(DQKV.dtype.element_ty),
             mask=qmask[:, None])


def _prec(qkv):
    """tl.dot input precision: fp32 inputs run TF32 on the tensor cores (Triton's default, 10-bit mantissa = the
    fp16 noise level); AZ_TRAIN_ATTN_IEEE=1 runs them in full fp32 (the gate check's exact comparison). fp16 / bf16
    inputs are not affected."""
    return "ieee" if qkv.dtype == torch.float32 and os.environ.get("AZ_TRAIN_ATTN_IEEE") == "1" else "tf32"


def _blocks(max_len):
    b = 32 if max_len <= 32 else int(os.environ.get("AZ_TRAIN_ATTN_BLOCK", "64"))
    return b, b


def _launches(rf, rows_only, has_bias):
    """(SEL, HAS_BIAS) per launch: rf splits rows into plain (no bias) and biased ones."""
    if rows_only:
        return ((2, has_bias),)
    if rf is None:
        return ((0, has_bias),)
    if not has_bias:
        return ((0, False),)
    return ((1, False), (2, True))


class _VarlenAttnTrain(torch.autograd.Function):
    @staticmethod
    def forward(ctx, qkv, seq_off, heads, max_len, cls, tab, rf, rows_only):
        qkv = qkv.contiguous()
        N, D3 = qkv.shape
        D = D3 // 3
        R = seq_off.shape[0] - 1
        BM, BN = _blocks(max_len)
        has_bias = tab is not None
        C = tab.shape[-1] if has_bias else 1
        cls_ = cls if cls is not None else seq_off
        tab_ = tab.float().contiguous() if has_bias else qkv
        rf_ = rf if rf is not None else seq_off
        out = qkv.new_zeros(N, D)
        lse = torch.zeros(N, heads, dtype=torch.float32, device=qkv.device)
        scale = (D // heads) ** -0.5
        nw = int(os.environ.get("AZ_TRAIN_ATTN_WARPS", "4"))
        prec = _prec(qkv)
        for sel, hb in _launches(rf, rows_only, has_bias):
            _fwd[(R, heads, triton.cdiv(max_len, BM))](qkv, out, lse, seq_off, cls_, tab_, rf_, scale, H=heads, D=D,
                                                       DH=D // heads, BM=BM, BN=BN, HAS_BIAS=hb, C=C, SEL=sel,
                                                       PREC=prec, num_warps=nw)
        ctx.save_for_backward(qkv, out, lse, seq_off, cls_, tab_, rf_)
        ctx.meta = (heads, max_len, has_bias, C, rf is not None, rows_only)
        return out

    @staticmethod
    def backward(ctx, dout):
        qkv, out, lse, seq_off, cls_, tab_, rf_ = ctx.saved_tensors
        heads, max_len, has_bias, C, has_rf, rows_only = ctx.meta
        N, D3 = qkv.shape
        D = D3 // 3
        R = seq_off.shape[0] - 1
        BM, BN = _blocks(max_len)
        dout = dout.contiguous().to(qkv.dtype)
        delta = (dout.float() * out.float()).view(N, heads, D // heads).sum(-1).contiguous()
        dqkv = torch.zeros_like(qkv)
        need_dtab = has_bias and ctx.needs_input_grad[5]
        dtab = torch.zeros(heads, C, C, dtype=torch.float32, device=qkv.device) if need_dtab else qkv
        scale = (D // heads) ** -0.5
        nw = int(os.environ.get("AZ_TRAIN_ATTN_WARPS", "4"))
        prec = _prec(qkv)
        for sel, hb in _launches(rf_ if has_rf else None, rows_only, has_bias):
            _bwd_kv[(R, heads, triton.cdiv(max_len, BN))](qkv, dout, lse, delta, dqkv, seq_off, cls_, tab_, dtab, rf_,
                                                          scale, H=heads, D=D, DH=D // heads, BM=BM, BN=BN,
                                                          HAS_BIAS=hb, NEED_DTAB=need_dtab and hb, C=C, SEL=sel, PREC=prec,
                                                          num_warps=nw)
            _bwd_q[(R, heads, triton.cdiv(max_len, BM))](qkv, dout, lse, delta, dqkv, seq_off, cls_, tab_, rf_, scale,
                                                         H=heads, D=D, DH=D // heads, BM=BM, BN=BN, HAS_BIAS=hb, C=C,
                                                         SEL=sel, PREC=prec, num_warps=nw)
        return dqkv, None, None, None, None, (dtab if need_dtab else None), None, None


def varlen_attn_train(qkv, seq_off, heads, max_len, cls=None, tab=None, rf=None, rows_only=False):
    """Attention on packed tokens with gradients for qkv and tab (see the module docstring). qkv [N, 3 d] (fp16 /
    bf16 / fp32), seq_off [R + 1] int32, max_len >= the longest row, cls [N] int32, tab [H, C, C] (C <= 16), rf [R]
    int32. Tokens past seq_off[-1] (bucket padding) get zero outputs and gradients."""
    if tab is not None and cls is None:
        raise ValueError("varlen_attn_train: tab needs cls")
    if rows_only and rf is None:
        raise ValueError("varlen_attn_train: rows_only needs rf")
    return _VarlenAttnTrain.apply(qkv, seq_off, heads, max_len, cls, tab, rf, rows_only)


def row_flags(cls, seq_off):
    """rf for varlen_attn_train: 1 for the rows holding a token of class 1..3 (encounter tokens), int32 [R]."""
    enc = ((cls >= 1) & (cls <= 3)).long()
    c = torch.cat([enc.new_zeros(1), enc.cumsum(0)])
    so = seq_off.long()
    return ((c[so[1:]] - c[so[:-1]]) > 0).to(torch.int32)
