"""The whole AmberNet forward pass as one Triton kernel, for self-play inference (tools/az_bench/selfplay.py
--fused-net).

Amber Eye (https://8e9f.github.io/amber_eye/, read 2026-11-17) says of its GPU side only: "the model is small enough
that its weights in FP16 fit comfortably in my GPU's L2 cache, and it has high arithmetic intensity, so it was
relatively easy to get high compute utilization. The kernel achieved about 75% MFU in self-play after discounting
padded attention operations." This file follows that: one kernel computes the whole net (input embedding, every
encoder layer, final norm, summary, the policy over the legal actions and the value heads) for a batch; the FP16
weights (0.44M net: ~0.9 MB) stay in L2; the activations never leave registers; attention is padded within a tile.
The math is AmberNet.forward_packed's (same net, same weights); only the execution changes.

Layout: the packed live tokens of a batch (RunDriver.next_flat(packed_tokens=True): tok_type [N], ids [N, 4],
f [N, 64], row r's tokens at seq_off[r] .. seq_off[r + 1], the run token first). make_tiles groups consecutive rows
into tiles of at most TILE tokens and SM rows; one program handles one tile: its tokens are the rows of a
[TILE, d] register block, attention runs per head as a [TILE, TILE] matmul masked to pairs of the same row (the
padded attention Amber discounts), the FFN walks its hidden dimension in chunks (fused_ffn.py), the per-row summary
is a one-hot matmul on the tile, and the policy gathers source / target token states from a scratch buffer. A row
longer than TILE goes to a second launch with the larger tile BIG_TILE; a row longer than BIG_TILE (rare: card
stacks give ~26 tokens per state) runs through AmberNet.forward_packed on a sub-batch.

Differences to forward_packed in fp16 are float rounding only: the residual stream and all accumulations stay fp32
(forward_packed rounds the residual to fp16 after every op). Tests: tests/test_fused_net.py (TRITON_INTERPRET=1 on a
CPU, or a CUDA GPU).
"""

import os

import numpy as np
import torch
import triton
import triton.language as tl

# Defaults from offline sm_86 compiles with Triton 3.1 (ptxas -v): tile 64 / 8 warps / 1 stage spills least; a
# 256-token tile needs ~147 KB shared memory (sm_86: 99 KB), so rows above BIG_TILE run through the net's own
# forward_packed instead.
TILE = int(os.environ.get("AZ_FUSED_NET_TILE", "64"))       # tokens per tile (power of two)
BIG_TILE = int(os.environ.get("AZ_FUSED_NET_BIG_TILE", "128"))
SM_ROWS = int(os.environ.get("AZ_FUSED_NET_ROWS", "16"))     # rows per tile (power of two, >= 16 for tl.dot)
WARPS = int(os.environ.get("AZ_FUSED_NET_WARPS", "8"))
BIG_WARPS = int(os.environ.get("AZ_FUSED_NET_BIG_WARPS", "8"))
STAGES = int(os.environ.get("AZ_FUSED_NET_STAGES", "1"))
FFN_BH = int(os.environ.get("AZ_FUSED_NET_BH", "64"))
ACT_BLOCK = int(os.environ.get("AZ_FUSED_NET_BA", "32"))


def _p2(n, lo=16):
    return max(lo, 1 << (int(n) - 1).bit_length())


@triton.jit
def _ln(x, W, B, cols, eps, D: tl.constexpr):
    mean = tl.sum(x, 1) / D
    xc = x - mean[:, None]
    var = tl.sum(xc * xc, 1) / D
    w = tl.load(W + cols).to(tl.float32)
    b = tl.load(B + cols).to(tl.float32)
    return xc * (1.0 / tl.sqrt(var + eps))[:, None] * w[None, :] + b[None, :]


@triton.jit
def _gelu(h):
    return 0.5 * h * (1.0 + tl.math.erf(h * 0.7071067811865476))


@triton.jit
def _wt(W, rows_out, cols_in, IN: tl.constexpr):
    """[len(cols_in), len(rows_out)] = W[rows_out, cols_in]^T for a row-major weight W [OUT, IN]."""
    return tl.load(W + rows_out[None, :] * IN + cols_in[:, None])


@triton.jit
def _net_kernel(
        # inputs
        TT, IDS, FEAT, OFF, TS, TE, ATYPE, ASRC, ATGT, AF, AMASK,
        # weights
        TEMB, EMB, PW, PB, INW, INB,
        LN1W, LN1B, WQKV, BQKV, WO, BO, LN2W, LN2B, W1, B1, W2, B2,
        OUTW, OUTB, SW1, SB1, SW2, SB2,
        AEMB, NS, NT, WS, WT, WF, WC, BC, PW1, PB1, PW2, PB2,
        OW1, OB1, OW2, OB2, HW1, HB1, HW2, HB2, FW1, FB1, FW2, FB2,
        # outputs, scratch
        LOGITS, OUTC, HPC, HPF, HBUF, CBUF,
        A, eps, scale,
        D: tl.constexpr, H: tl.constexpr, DH: tl.constexpr, L: tl.constexpr, HID: tl.constexpr, BH: tl.constexpr,
        NTYPE: tl.constexpr, NF: tl.constexpr, NAF: tl.constexpr,
        NOUT: tl.constexpr, NOUTP: tl.constexpr, NHP: tl.constexpr, NHPF: tl.constexpr, NHPFP: tl.constexpr,
        T: tl.constexpr, SM: tl.constexpr, BA: tl.constexpr):
    pid = tl.program_id(0)
    r0 = tl.load(TS + pid)
    r1 = tl.load(TE + pid)
    t0 = tl.load(OFF + r0)
    t1 = tl.load(OFF + r1)
    cols = tl.arange(0, D)
    ti = tl.arange(0, T)
    tok = t0 + ti
    tmask = tok < t1
    srow = tl.arange(0, SM)
    # local row of each token: the number of row ends at or below it
    ends = tl.load(OFF + r0 + 1 + srow, mask=r0 + 1 + srow <= r1, other=2147483647)
    seg = tl.sum((tok[:, None] >= ends[None, :]).to(tl.int32), 1)
    rstart = tl.load(OFF + r0 + seg, mask=tmask, other=0)
    pos = tok - rstart                                                    # position in the row; 0 = run token

    # ---- input: type embedding + id embeddings + own-type float projection, LayerNorm ----
    tt = tl.load(TT + tok, mask=tmask, other=0).to(tl.int32)
    x = tl.load(TEMB + tt[:, None] * D + cols[None, :]).to(tl.float32)
    for c in tl.static_range(4):
        idv = tl.load(IDS + tok * 4 + c, mask=tmask, other=0).to(tl.int32)
        x += tl.load(EMB + idv[:, None] * D + cols[None, :]).to(tl.float32)
    fc = tl.arange(0, NF)
    fv = tl.load(FEAT + tok[:, None] * NF + fc[None, :], mask=tmask[:, None], other=0.0).to(PW.dtype.element_ty)
    for k in tl.static_range(NTYPE):
        is_k = (tt == k) & tmask
        if tl.sum(is_k.to(tl.int32), 0) > 0:
            p = tl.dot(fv, _wt(PW + k * D * NF, cols, fc, NF)) + tl.load(PB + k * D + cols).to(tl.float32)[None, :]
            x += tl.where(is_k[:, None], p, 0.0)
    x = _ln(x, INW, INB, cols, eps, D)

    # ---- encoder layers (pre-norm, exact GELU) ----
    dc = tl.arange(0, DH)
    for l in tl.static_range(L):   # a runtime loop here crashes Triton 3.1 (segfault in make_ttgir)
        y = _ln(x, LN1W + l * D, LN1B + l * D, cols, eps, D).to(WQKV.dtype.element_ty)
        wq = WQKV + l * 3 * D * D
        bq = BQKV + l * 3 * D
        att = tl.zeros([T, D], dtype=tl.float32)
        # (names inside this runtime loop are not reused from before it: Triton treats such a name as loop-carried)
        for hh in tl.static_range(H):
            ac = hh * DH + dc
            qh = tl.dot(y, _wt(wq, ac, cols, D)) + tl.load(bq + ac).to(tl.float32)[None, :]
            kh = tl.dot(y, _wt(wq, D + ac, cols, D)) + tl.load(bq + D + ac).to(tl.float32)[None, :]
            vh = tl.dot(y, _wt(wq, 2 * D + ac, cols, D)) + tl.load(bq + 2 * D + ac).to(tl.float32)[None, :]
            sc = tl.dot(qh.to(y.dtype), tl.trans(kh.to(y.dtype))) * scale
            sc = tl.where((seg[:, None] == seg[None, :]) & tmask[None, :], sc, -1e30)       # finite: a padding query row averages instead of producing NaN
            mx = tl.max(sc, 1)
            pa = tl.exp(sc - mx[:, None])
            pa = pa / tl.sum(pa, 1)[:, None]
            oh = tl.dot(pa.to(y.dtype), vh.to(y.dtype))
            att += tl.dot(oh.to(y.dtype), _wt(WO + l * D * D, cols, ac, D))       # WO[:, head cols]^T
        x = x + att + tl.load(BO + l * D + cols).to(tl.float32)[None, :]
        y = _ln(x, LN2W + l * D, LN2B + l * D, cols, eps, D).to(W1.dtype.element_ty)
        acc = tl.zeros([T, D], dtype=tl.float32)
        for h0 in range(0, HID, BH):
            fh = h0 + tl.arange(0, BH)
            gf = _gelu(tl.dot(y, _wt(W1 + l * HID * D, fh, cols, D))
                       + tl.load(B1 + l * HID + fh).to(tl.float32)[None, :])
            acc += tl.dot(gf.to(y.dtype), _wt(W2 + l * D * HID, cols, fh, HID))
        x = x + acc + tl.load(B2 + l * D + cols).to(tl.float32)[None, :]
    hw = _ln(x, OUTW, OUTB, cols, eps, D).to(WS.dtype.element_ty)        # [T, D] final token states
    # The final token states and W_c c + b_c go to scratch buffers so the policy can gather them by index (a one-hot
    # matmul on the tile kept [T, D] blocks live across the action loop and spilled registers).
    tl.store(HBUF + tok[:, None] * D + cols[None, :], hw, mask=tmask[:, None])

    # ---- summary: c = run token + summary_mlp(mean of the row's other tokens) ----
    memb = (seg[None, :] == srow[:, None]) & tmask[None, :]               # [SM, T]
    runm = memb & (pos == 0)[None, :]
    restm = memb & (pos > 0)[None, :]
    cnt = tl.maximum(tl.sum(restm.to(tl.float32), 1), 1.0)
    # one-hot sums in fp32 (a bool -> fp16 one-hot matmul crashes Triton 3.1 in make_llir)
    rest = tl.dot(restm.to(tl.float32), hw.to(tl.float32), input_precision="ieee") / cnt[:, None]
    runv = tl.dot(runm.to(tl.float32), hw.to(tl.float32), input_precision="ieee")
    g = _gelu(tl.dot(rest.to(hw.dtype), _wt(SW1, cols, cols, D)) + tl.load(SB1 + cols).to(tl.float32)[None, :])
    c = runv + tl.dot(g.to(hw.dtype), _wt(SW2, cols, cols, D)) + tl.load(SB2 + cols).to(tl.float32)[None, :]
    cw = c.to(hw.dtype)
    rows = r0 + srow
    rmask = rows < r1
    cc = tl.dot(cw, _wt(WC, cols, cols, D)) + tl.load(BC + cols).to(tl.float32)[None, :]   # [SM, D] W_c c + b_c
    tl.store(CBUF + rows[:, None] * D + cols[None, :], cc, mask=rmask[:, None])

    # ---- value heads (two-layer MLPs on c) ----
    g = _gelu(tl.dot(cw, _wt(OW1, cols, cols, D)) + tl.load(OB1 + cols).to(tl.float32)[None, :]).to(hw.dtype)
    oc = tl.arange(0, NOUTP)
    om = oc < NOUT
    w = tl.load(OW2 + oc[None, :] * D + cols[:, None], mask=om[None, :], other=0.0)
    out = tl.dot(g, w) + tl.load(OB2 + oc, mask=om, other=0.0).to(tl.float32)[None, :]
    tl.store(OUTC + rows[:, None] * NOUT + oc[None, :], out, mask=rmask[:, None] & om[None, :])
    g = _gelu(tl.dot(cw, _wt(HW1, cols, cols, D)) + tl.load(HB1 + cols).to(tl.float32)[None, :]).to(hw.dtype)
    hcl = tl.arange(0, NHP)
    out = tl.dot(g, _wt(HW2, hcl, cols, D)) + tl.load(HB2 + hcl).to(tl.float32)[None, :]
    tl.store(HPC + rows[:, None] * NHP + hcl[None, :], out, mask=rmask[:, None])
    g = _gelu(tl.dot(cw, _wt(FW1, cols, cols, D)) + tl.load(FB1 + cols).to(tl.float32)[None, :]).to(hw.dtype)
    fcl = tl.arange(0, NHPFP)
    fm = fcl < NHPF
    w = tl.load(FW2 + fcl[None, :] * D + cols[:, None], mask=fm[None, :], other=0.0)
    out = tl.dot(g, w) + tl.load(FB2 + fcl, mask=fm, other=0.0).to(tl.float32)[None, :]
    tl.store(HPF + rows[:, None] * NHPF + fcl[None, :], out, mask=rmask[:, None] & fm[None, :])
    tl.debug_barrier()   # HBUF / CBUF written by this program's threads -> visible to all of them

    # ---- policy: e_a = emb(k_a) + W_s h_src + W_t h_tgt + W_f f_a + W_c c + b_c; logit = pol MLP(e_a) ----
    wst = _wt(WS, cols, cols, D)
    wtt = _wt(WT, cols, cols, D)
    ns = tl.load(NS + cols).to(tl.float32)
    nt = tl.load(NT + cols).to(tl.float32)
    afc = tl.arange(0, 16)
    wf = tl.load(WF + cols[None, :] * NAF + afc[:, None], mask=afc[:, None] < NAF, other=0.0)
    pw1 = _wt(PW1, cols, cols, D)
    pb1 = tl.load(PB1 + cols).to(tl.float32)
    pw2 = tl.load(PW2 + cols).to(tl.float32)
    pb2 = tl.load(PB2).to(tl.float32)
    nact = (r1 - r0) * A
    for j0 in range(0, nact, BA):
        j = j0 + tl.arange(0, BA)
        jm = j < nact
        row = r0 + j // A
        ai = row * A + j % A
        at = tl.load(ATYPE + ai, mask=jm, other=0).to(tl.int32)
        src = tl.load(ASRC + ai, mask=jm, other=-1).to(tl.int32)
        tgt = tl.load(ATGT + ai, mask=jm, other=-1).to(tl.int32)
        am = tl.load(AMASK + ai, mask=jm, other=0) != 0
        base = tl.load(OFF + row, mask=jm, other=0)                         # the row's first packed token
        e = tl.load(AEMB + at[:, None] * D + cols[None, :]).to(tl.float32)
        e += tl.load(CBUF + row[:, None] * D + cols[None, :], mask=jm[:, None], other=0.0)
        hs = tl.load(HBUF + (base + src)[:, None] * D + cols[None, :], mask=(jm & (src >= 0))[:, None], other=0.0)
        e += tl.dot(hs, wst) + tl.where((src < 0)[:, None], ns[None, :], 0.0)
        ht = tl.load(HBUF + (base + tgt)[:, None] * D + cols[None, :], mask=(jm & (tgt >= 0))[:, None], other=0.0)
        e += tl.dot(ht, wtt) + tl.where((tgt < 0)[:, None], nt[None, :], 0.0)
        af = tl.load(AF + ai[:, None] * NAF + afc[None, :], mask=jm[:, None] & (afc[None, :] < NAF), other=0.0)
        e += tl.dot(af.to(wf.dtype), wf)
        gp = _gelu(tl.dot(e.to(pw1.dtype), pw1) + pb1[None, :])
        logit = tl.sum(gp * pw2[None, :], 1) + pb2
        logit = tl.where(am, logit, -1e4)
        tl.store(LOGITS + ai, logit, mask=jm)


def _weights(net, dtype):
    types = list(net.proj.keys())   # TOKEN_TYPES order: tok_type indexes it
    lay = net.trunk.layers
    eps = {float(net.in_norm.eps), float(net.out_norm.eps)}
    eps |= {float(x.norm1.eps) for x in lay} | {float(x.norm2.eps) for x in lay}
    assert len(eps) == 1, "fused_net: one LayerNorm eps"
    with torch.no_grad():
        st = lambda ts: torch.stack([t.detach() for t in ts]).contiguous()   # noqa: E731
        W = {
            "TEMB": net.type_emb.weight, "EMB": net.ids.weight,
            "PW": st([net.proj[t].weight for t in types]), "PB": st([net.proj[t].bias for t in types]),
            "INW": net.in_norm.weight, "INB": net.in_norm.bias,
            "LN1W": st([x.norm1.weight for x in lay]), "LN1B": st([x.norm1.bias for x in lay]),
            "WQKV": st([x.self_attn.in_proj_weight for x in lay]), "BQKV": st([x.self_attn.in_proj_bias for x in lay]),
            "WO": st([x.self_attn.out_proj.weight for x in lay]), "BO": st([x.self_attn.out_proj.bias for x in lay]),
            "LN2W": st([x.norm2.weight for x in lay]), "LN2B": st([x.norm2.bias for x in lay]),
            "W1": st([x.linear1.weight for x in lay]), "B1": st([x.linear1.bias for x in lay]),
            "W2": st([x.linear2.weight for x in lay]), "B2": st([x.linear2.bias for x in lay]),
            "OUTW": net.out_norm.weight, "OUTB": net.out_norm.bias,
            "SW1": net.summary_mlp[0].weight, "SB1": net.summary_mlp[0].bias,
            "SW2": net.summary_mlp[2].weight, "SB2": net.summary_mlp[2].bias,
            "AEMB": net.a_type.weight,
            "NS": net.w_s.weight.float() @ net.a_none[0].float(), "NT": net.w_t.weight.float() @ net.a_none[1].float(),
            "WS": net.w_s.weight, "WT": net.w_t.weight, "WF": net.w_f.weight, "WC": net.w_c.weight,
            "BC": net.w_c.bias,
            "PW1": net.pol[0].weight, "PB1": net.pol[0].bias, "PW2": net.pol[2].weight.reshape(-1),
            "PB2": net.pol[2].bias,
            "OW1": net.outcome[0].weight, "OB1": net.outcome[0].bias, "OW2": net.outcome[2].weight,
            "OB2": net.outcome[2].bias,
            "HW1": net.hp[0].weight, "HB1": net.hp[0].bias, "HW2": net.hp[2].weight, "HB2": net.hp[2].bias,
            "FW1": net.hp_floor[0].weight, "FB1": net.hp_floor[0].bias, "FW2": net.hp_floor[2].weight,
            "FB2": net.hp_floor[2].bias,
        }
        dtype = dtype or net.type_emb.weight.dtype
        W = {k: v.detach().to(dtype).contiguous() for k, v in W.items()}
    a0 = lay[0].self_attn
    meta = dict(eps=eps.pop(), D=net.type_emb.weight.shape[1], H=a0.num_heads, L=len(lay),
                HID=lay[0].linear1.weight.shape[0], NTYPE=len(types), NF=net.proj[types[0]].weight.shape[1],
                NAF=net.w_f.weight.shape[1], NOUT=net.outcome[2].weight.shape[0], NHP=net.hp[2].weight.shape[0],
                NHPF=net.hp_floor[2].weight.shape[0])
    return W, meta


ORDER = ("TEMB", "EMB", "PW", "PB", "INW", "INB", "LN1W", "LN1B", "WQKV", "BQKV", "WO", "BO", "LN2W", "LN2B", "W1",
         "B1", "W2", "B2", "OUTW", "OUTB", "SW1", "SB1", "SW2", "SB2", "AEMB", "NS", "NT", "WS", "WT", "WF", "WC",
         "BC", "PW1", "PB1", "PW2", "PB2", "OW1", "OB1", "OW2", "OB2", "HW1", "HB1", "HW2", "HB2", "FW1", "FB1",
         "FW2", "FB2")


class FusedNet:
    """Holds the kernel's weight copy of an AmberNet. refresh() after the net's weights change."""

    def __init__(self, net, dtype=None):
        self.net = net
        self.dtype = dtype
        self.refresh()

    def refresh(self):
        self.W, self.meta = _weights(self.net, self.dtype)
        m = self.meta
        D, H = m["D"], m["H"]
        assert D & (D - 1) == 0 and D % H == 0 and (D // H) >= 16 and (D // H) & (D // H - 1) == 0, \
            "fused_net: d a power of two, head dim a power of two >= 16"
        assert m["HID"] % FFN_BH == 0 and m["NF"] & (m["NF"] - 1) == 0 and m["NAF"] <= 16
        assert m["NHP"] & (m["NHP"] - 1) == 0 and m["NHP"] >= 16

    def __call__(self, b, tiles=None, rows=None):
        """b: forward_packed's packed inputs (tok_type [N], ids [N, 4], f [N, 64], seq_off [R + 1]; a_type / a_src /
        a_tgt / a_mask [R, A], a_f [R, A, 8]; any integer dtypes). tiles: make_tiles(...) on the host (computed here
        from seq_off when None; that is a device -> host copy). Returns (logits [R, A], outcome [R, 57], hp [R, 256],
        hp_floor [R, F] or [R] for F = 1), fp32; rows >= `rows` (default R) are not computed."""
        so = b["seq_off"]
        R = so.shape[0] - 1
        rows = R if rows is None else rows
        if tiles is None:
            tiles = make_tiles(so.cpu().numpy(), rows)
        A = b["a_type"].shape[1]
        dev = so.device
        m = self.meta
        out = (torch.empty(R, A, device=dev), torch.empty(R, m["NOUT"], device=dev),
               torch.empty(R, m["NHP"], device=dev), torch.empty(R, m["NHPF"], device=dev))
        hbuf = torch.empty(b["tok_type"].shape[0], m["D"], device=dev, dtype=self.W["WS"].dtype)
        cbuf = torch.empty(R, m["D"], device=dev)
        for (ts, te), t, warps in ((tiles["small"], tiles["tile"], WARPS), (tiles["big"], tiles["big_tile"], BIG_WARPS)):
            n = ts.shape[0]
            if not n:
                continue
            ts = torch.as_tensor(ts).to(dev, non_blocking=True)
            te = torch.as_tensor(te).to(dev, non_blocking=True)
            _net_kernel[(n,)](
                b["tok_type"], b["ids"], b["f"], so, ts, te, b["a_type"], b["a_src"], b["a_tgt"], b["a_f"],
                b["a_mask"], *[self.W[k] for k in ORDER], *out, hbuf, cbuf, A, m["eps"], (m["D"] // m["H"]) ** -0.5,
                D=m["D"], H=m["H"], DH=m["D"] // m["H"], L=m["L"], HID=m["HID"], BH=FFN_BH, NTYPE=m["NTYPE"],
                NF=m["NF"], NAF=m["NAF"], NOUT=m["NOUT"], NOUTP=_p2(m["NOUT"]), NHP=m["NHP"], NHPF=m["NHPF"],
                NHPFP=_p2(m["NHPF"]), T=t, SM=SM_ROWS, BA=ACT_BLOCK, num_warps=warps, num_stages=STAGES)
        if len(tiles["long"][0]):
            self._long_rows(b, tiles["long"], out)
        lg, oc, hp, hpf = out
        return lg, oc, hp, (hpf.squeeze(-1) if m["NHPF"] == 1 else hpf)


    def _long_rows(self, b, long, out):
        """Rows longer than BIG_TILE: the net's forward_packed on a sub-batch of just those rows (same math)."""
        rows, starts, counts = long
        self.long_rows += len(rows)
        dev = b["seq_off"].device
        ti = torch.from_numpy(np.concatenate([np.arange(s, s + n) for s, n in zip(starts, counts)])).to(dev)
        ri = torch.from_numpy(rows.astype(np.int64)).to(dev)
        mask = torch.from_numpy(np.arange(counts.max())[None, :] < counts[:, None]).to(dev)
        wd = self.net.type_emb.weight.dtype
        sub = {"tok_type": b["tok_type"][ti].long(), "ids": b["ids"][ti].long(), "f": b["f"][ti].to(wd),
               "mask": mask, "seq_off": torch.from_numpy(np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)).to(dev)}
        sub["pack_idx"] = torch.nonzero(mask.reshape(-1)).squeeze(1)
        for k in ("a_type", "a_src", "a_tgt"):
            sub[k] = b[k][ri].long()
        sub["a_f"] = b["a_f"][ri].to(wd)
        sub["a_mask"] = b["a_mask"][ri].bool()
        res = self.net(sub)
        for o, r in zip(out, res):
            o[ri] = r.float().reshape(len(rows), -1)

    long_rows = 0   # rows that went through _long_rows (all calls)


fused_net = FusedNet   # amber_net.load_kernel("fused_net")


def make_tiles(seq_off, rows, tile=None, big_tile=None, max_rows=None):
    """Host-side tiling: consecutive rows 0 .. rows - 1 grouped greedily into tiles of at most `tile` tokens and
    `max_rows` rows; a row with more than `tile` tokens is its own tile in the "big" launch, a row with more than
    big_tile tokens goes to "long" (FusedNet._long_rows). seq_off: int numpy [>= rows + 1]. Returns
    {"small": (starts, ends), "big": (starts, ends), "long": (rows, token starts, token counts)}, int32 / int64."""
    tile = tile or TILE
    big_tile = big_tile or BIG_TILE
    max_rows = max_rows or SM_ROWS
    so = np.asarray(seq_off[:rows + 1], dtype=np.int64)
    ss, se, bs, ls = [], [], [], []
    r = 0
    while r < rows:
        e = int(np.searchsorted(so, so[r] + tile, side="right")) - 1   # last row end within the tile
        e = min(e, r + max_rows, rows)
        if e <= r:          # row r alone is longer than a tile
            (bs if so[r + 1] - so[r] <= big_tile else ls).append(r)
            r += 1
            continue
        ss.append(r)
        se.append(e)
        r = e
    i32 = lambda v: np.asarray(v, dtype=np.int32)   # noqa: E731
    lr = np.asarray(ls, dtype=np.int64)
    return {"tile": tile, "big_tile": big_tile, "small": (i32(ss), i32(se)), "big": (i32(bs), i32(bs) + 1),
            "long": (lr, so[lr], so[lr + 1] - so[lr])}
