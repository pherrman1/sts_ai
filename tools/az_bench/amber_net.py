"""A token transformer shaped after Amber Eye's network (https://8e9f.github.io/amber_eye/, read 2026-11-16), for
the stage 0 throughput bench. Only what the page states is copied; the rest is marked as our choice.

From the page:
  - one transformer evaluates every game state; the state is a set of tokens of types run metrics, player metrics,
    player status effects, monster, card, relic, potion, option, map;
  - each token has up to 4 categorical ids and up to 64 floats; its input is the type embedding + its categorical
    embeddings + a type-specific projection of its floats, LayerNormed; unique cards, relics, enemies, event choices
    share one embedding space;
  - about 40 tokens per state on average, mostly cards and relics;
  - the policy is computed over a list of legal actions: e_a = emb(k_a) + W_s h_{s_a} + W_t h_{t_a} + W_f f_a + W_c c,
    k_a the action type, s_a / t_a its source / target token ("none" embedding when absent), f_a up to 8 features,
    c the state summary; an MLP projects e_a to a logit;
  - the summary is the run token plus the mean of the other tokens through a shared summary MLP; each head is a
    two-layer MLP on the summary;
  - sizes ~0.44M, ~1.2M, ~5.4M parameters.

Our choices (not on the page): width, depth, heads (d // 32), FFN = 4 d, pre-norm, GELU, the id vocabulary (1024),
the value heads' output sizes (outcome: win + death floor 1..56; HP class 0..255; per-floor HP scalar), and that the
inputs arrive as one padded segment per token type (an encoder emits tokens grouped by type, so the per-type float
projection is one Linear per segment).
"""

import os

import torch
import torch.nn as nn

TOKEN_TYPES = ("run", "player", "status", "monster", "card", "relic", "potion", "option", "map")
N_CAT, N_FLOAT, N_ACT_FEAT = 4, 64, 8
ID_VOCAB = 1024        # our choice: one shared space for cards, relics, enemies, statuses, potions, options
ACTION_TYPES = 16      # our choice
OUTCOME_CLASSES = 57   # our choice: win + death on floor 1..56
HP_CLASSES = 256       # page: current-floor HP as a class, capped at 255

# Encounter tokens (RunDriver enemy_tokens, search::amberAppendEncounterTokens; not from Amber Eye): MONSTER tokens
# with ids[3] = ENC_KIND_BASE + kind (0 boss, 1 elite, 2 hallway). Must equal kAmberEncounterKindBase (C++
# static_assert in AmberGameEncoder.cpp).
ENC_KIND_BASE = 1018
# Attention-bias token classes (AmberNet(enemy_bias=True)): 0 other, 1..3 encounter token boss / elite / hallway,
# 4..6 MAP node boss / elite / hallway fight.
BIAS_CLASSES = 7


def token_classes(tt, ids, f):
    """Attention-bias class per token from tok_type [...], ids [..., 4], f [..., 64] (BIAS_CLASSES). MAP floats
    3 + Room (AmberGameEncoder.cpp): 6 = ELITE, 7 = MONSTER, 9 = BOSS; 18 = the act boss token after row 14."""
    mon = tt == TOKEN_TYPES.index("monster")
    mp = tt == TOKEN_TYPES.index("map")
    kind = ids[..., 3] - ENC_KIND_BASE
    cls = torch.where(mon & (kind >= 0) & (kind < 3), 1 + kind, torch.zeros_like(kind))
    cls = torch.where(mp & (f[..., 7] > 0.5), torch.full_like(cls, 6), cls)
    cls = torch.where(mp & (f[..., 6] > 0.5), torch.full_like(cls, 5), cls)
    cls = torch.where(mp & ((f[..., 9] > 0.5) | (f[..., 18] > 0.5)), torch.full_like(cls, 4), cls)
    return cls


# AZ_ENEMY_NO_COMPILE=1: the encounter-token helpers below run outside torch.compile graphs (graph breaks; #1164's
# defensive fix, ~3x slower compiled inference on the PC). Default: compiled with the rest of the forward; the op
# inputs are made contiguous inside the custom ops, and the gated row mean uses the row_mean op (no bucketize /
# index_add with the dynamic token count).
def _compile_guard(fn):
    return torch.compiler.disable(fn) if os.environ.get("AZ_ENEMY_NO_COMPILE") == "1" else fn


@_compile_guard
def _gated_row_mean(row_mean, x, so, enc, g):
    """The row mean of _heads_packed with the encounter tokens weighted by the summary gate g, from row_mean (the
    plain mean of each row's tokens after the first) on x * other and on x * enc, and exact encounter counts, in fp32:
    (S_other + g S_enc) / (n_other + g n_enc) = (m_other + g m_enc) / ((1 - f_enc) + g f_enc), the per-row counts
    cancel."""
    N, d = x.shape
    e = enc.float()[:, None]
    xf = x.float()
    # two row_mean calls at width d in x's dtype (the configuration the packed heads use without the flags; masking
    # by 0 / 1 is exact): row_mean in fp32 at widths 16 / 2 d was wrong on the PC GPU (sm_86, triton 3.1.0)
    m = torch.cat([row_mean((xf * (1.0 - e)).to(x.dtype).contiguous(), so),
                   row_mean((xf * e).to(x.dtype).contiguous(), so)], 1).float()
    # f_enc from exact counts (prefix sums of the indicator over each row's tokens after the first)
    c = torch.cat([enc.new_zeros(1, dtype=torch.long), enc.long().cumsum(0)])
    hi = so[1:]
    lo = torch.minimum(so[:-1] + 1, hi)
    f = ((c[hi] - c[lo]).float() / (hi - lo).clamp(min=1).float())[:, None]
    g = g.float()
    den = (1.0 - f) + g * f
    return ((m[:, :d] + g * m[:, d:]) / torch.where(den > 0, den, torch.ones_like(den))).to(x.dtype)


@_compile_guard
def _packed_classes(tt_p, ids_p, f_p):
    """token_classes on packed tokens and as int32 (varlen_attn's cls)."""
    cls = token_classes(tt_p, ids_p, f_p)
    return cls, cls.to(torch.int32).contiguous()


@_compile_guard
def _enemy_vattn(kernel, qkv, seq_off, heads, max_len, cls_i, tab, gate):
    """varlen_attn with the encounter inputs (the op makes its inputs contiguous)."""
    return kernel(qkv, seq_off, heads, max_len, cls_i, None if tab is None else tab.float(),
                  None if gate is None else gate.float().reshape(1), True)   # split_enc: _tab is encounter-only


def enc_of(cls):
    """Encounter tokens (classes 1..3) of token_classes output."""
    return (cls >= 1) & (cls <= 3)


def strip_encounters(b):
    """A flat batch (forward_flat layout: tok_type [B, T], ids, f, mask, actions) without its encounter tokens, as
    the net without --enemy-tokens sees the states: each row's other tokens keep their order and move up, T shrinks
    to the longest row (rounded up to 8), action src / tgt are remapped (an action on an encounter token gets none).
    Keys other than the token and action ones are copied."""
    cls = token_classes(b["tok_type"], b["ids"], b["f"])
    keep = b["mask"] & ~enc_of(cls)
    B = keep.shape[0]
    pos = keep.long().cumsum(1) - 1
    Tn = max(8, -(-int(keep.sum(1).max()) // 8) * 8)
    r, c = torch.nonzero(keep, as_tuple=True)
    p = pos[r, c]
    out = dict(b)
    for k, tail in (("tok_type", ()), ("ids", (b["ids"].shape[-1],)), ("f", (b["f"].shape[-1],))):
        x = b[k].new_zeros(B, Tn, *tail)
        x[r, p] = b[k][r, c]
        out[k] = x
    m = torch.zeros(B, Tn, dtype=torch.bool, device=keep.device)
    m[r, p] = True
    out["mask"] = m
    remap = torch.where(keep, pos, torch.full_like(pos, -1))
    for k in ("a_src", "a_tgt"):
        x = b[k]
        out[k] = torch.where(x >= 0, torch.gather(remap, 1, x.clamp(min=0)), torch.full_like(x, -1))
    for k in ("pack_idx", "unpack_idx", "seq_off"):
        out.pop(k, None)
    return out

# Sizes chosen to land on the page's three parameter counts (d, layers); heads = d // 32.
SIZES = {"0.44M": (64, 6), "1.2M": (128, 4), "5.4M": (256, 5)}


def mlp(i, h, o):
    return nn.Sequential(nn.Linear(i, h), nn.GELU(), nn.Linear(h, o))


def load_kernel(name):
    """A Triton kernel module of tools/az_bench (fused_ffn, varlen_attn; imports triton) -> its function of the same
    name. Set it as AmberNet.<name> outside the traced forward."""
    import importlib.util
    import os
    import sys
    key = "az_bench_" + name
    mod = sys.modules.get(key)
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            key, os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[key] = mod
    return getattr(mod, name)


def load_fused_ffn():
    return load_kernel("fused_ffn")


def load_fused_layer():
    load_kernel("fused_ffn")
    import sys
    m = sys.modules["az_bench_fused_ffn"]
    return (m.ln_qkv, m.fused_out_ffn)


class AmberNet(nn.Module):
    def __init__(self, d=96, layers=3, heads=None, hp_floors=1, soft_policy=False, aux_slots=0, enemy_bias=False,
                 enemy_gate=False):
        super().__init__()
        heads = heads or max(1, d // 32)
        self.type_emb = nn.Embedding(len(TOKEN_TYPES), d)
        self.ids = nn.Embedding(ID_VOCAB, d, padding_idx=0)
        self.proj = nn.ModuleDict({t: nn.Linear(N_FLOAT, d) for t in TOKEN_TYPES})
        self.in_norm = nn.LayerNorm(d)
        enc = nn.TransformerEncoderLayer(d, heads, 4 * d, dropout=0.0, activation="gelu", batch_first=True,
                                         norm_first=True)
        self.trunk = nn.TransformerEncoder(enc, layers, enable_nested_tensor=False)
        self.out_norm = nn.LayerNorm(d)
        self.summary_mlp = mlp(d, d, d)
        self.a_type = nn.Embedding(ACTION_TYPES, d)
        self.a_none = nn.Parameter(torch.zeros(2, d))     # "none" source / target
        self.w_s = nn.Linear(d, d, bias=False)
        self.w_t = nn.Linear(d, d, bias=False)
        self.w_f = nn.Linear(N_ACT_FEAT, d, bias=False)
        self.w_c = nn.Linear(d, d)
        self.pol = mlp(d, d, 1)
        self.outcome = mlp(d, d, OUTCOME_CLASSES)
        self.hp = mlp(d, d, HP_CLASSES)
        # Per-floor HP head: 1 scalar by default (unused); hp_floors = 56 for the self-play utility "amber" (E[HP at
        # the end of floor f] / 255, f = 1..56; tools/az_bench/selfplay.py --utility amber).
        self.hp_floor = mlp(d, d, hp_floors)
        # Soft policy head (Amber Eye "Labels", adapted from KataGo; tools/az_bench/selfplay.py --w-soft-policy): a
        # second action MLP on the same e_a, trained on the flattened policy target p^(1/4). Training only: it is
        # computed (as a 5th output) only in training mode, so inference and eval calls are unchanged.
        self.pol_soft = mlp(d, d, 1) if soft_policy else None
        # Fight-outcome auxiliary head (tools/az_bench/selfplay.py --aux-fights; not from Amber Eye): per slot (boss,
        # elites 1..3, hallway) two logits, P(death in the fight) and the HP fraction left after it, on the summary.
        # Training only: computed in training mode into self.aux_out [B, 2 * aux_slots] (the outputs stay the same
        # tuple). Defined last, so the other parameters keep their order (optimizer state of a checkpoint without it).
        self.aux_fight = mlp(d, d, 2 * aux_slots) if aux_slots else None
        self.aux_out = None
        # Attention bias between encounter tokens and map nodes (tools/az_bench/selfplay.py --enemy-map-bias; not
        # from Amber Eye, after an STS2 author's design): per layer and head a learned table over the token classes
        # (token_classes), added to the attention scores of query class i and key class j. Zero at the start, so a
        # net without it computes the same outputs. Defined after the aux head (parameter order of older checkpoints).
        self.enemy_bias = nn.Parameter(torch.zeros(layers, heads, BIAS_CLASSES, BIAS_CLASSES)) if enemy_bias else None
        # Soft entry of the encounter tokens (selfplay.py --enemy-tokens, 2026-11-21; the owner's choice after the
        # first live test, where the new tokens shifted every out-of-combat output of the resumed net): per layer a
        # gate g in [0, 1] (parameter clamped with a straight-through gradient, 0 at the start) mixes the attention with the encounter tokens as keys
        # (weight g) and without them (1 - g), and a last gate weights them in the summary mean. At g = 0 every
        # other token computes what the net computes on the state without encounter tokens (up to float rounding).
        self.enemy_gate = nn.Parameter(torch.zeros(layers + 1)) if enemy_gate else None

    def load_state_dict(self, state_dict, strict=True, **kw):
        """A checkpoint's weights; a net without the aux head ignores the checkpoint's aux_fight weights, so tools
        that build the net without it load checkpoints of --aux-fights runs."""
        if self.aux_fight is None:
            state_dict = {k: v for k, v in state_dict.items() if not k.startswith("aux_fight.")}
        if self.enemy_bias is None:
            state_dict = {k: v for k, v in state_dict.items() if k != "enemy_bias"}
        if self.enemy_gate is None:
            state_dict = {k: v for k, v in state_dict.items() if k != "enemy_gate"}
        return super().load_state_dict(state_dict, strict=strict, **kw)

    def forward(self, b):
        if "tok_type" in b:
            return self.forward_flat(b)
        return self.forward_segments(b)

    @property
    def enemy_on(self):
        return self.enemy_bias is not None or self.enemy_gate is not None

    def _gate(self, i):
        """Gate i, its value clamped to [0, 1] with the gradient passed straight through (a plain clamp has no
        gradient at 0, where the gate starts)."""
        p = self.enemy_gate[i]
        return p + (p.clamp(0.0, 1.0) - p).detach()

    def _heads(self, h, mask, b, enc=None):
        live = mask[:, 1:, None].to(h.dtype)
        if enc is not None and self.enemy_gate is not None:   # encounter tokens count with the summary gate
            w = live * torch.where(enc[:, 1:, None], self._gate(-1).to(h.dtype), torch.ones_like(live))
            n = w.sum(1)
            rest = (h[:, 1:] * w).sum(1) / torch.where(n > 0, n, torch.ones_like(n))
        else:
            rest = (h[:, 1:] * live).sum(1) / live.sum(1).clamp(min=1)
        c = h[:, 0] + self.summary_mlp(rest)
        d = h.shape[-1]

        def pick(idx, none):
            g = torch.gather(h, 1, idx.clamp(min=0)[..., None].expand(-1, -1, d))
            return torch.where((idx >= 0)[..., None], g, none.to(g.dtype))

        e = (self.a_type(b["a_type"]) + self.w_s(pick(b["a_src"], self.a_none[0]))
             + self.w_t(pick(b["a_tgt"], self.a_none[1])) + self.w_f(b["a_f"]) + self.w_c(c)[:, None])
        logits = self.pol(e).squeeze(-1).masked_fill(~b["a_mask"], -1e4)
        out = (logits, self.outcome(c), self.hp(c), self.hp_floor(c).squeeze(-1))
        self.aux_out = self.aux_fight(c) if self.aux_fight is not None and self.training else None
        if self.pol_soft is not None and self.training:
            out = out + (self.pol_soft(e).squeeze(-1).masked_fill(~b["a_mask"], -1e4),)
        return out

    def _heads_packed(self, x, b, enc=None):
        """_heads on the packed tokens x [N, d] (after out_norm) and on the live actions only, without the padded
        [B, T, d] token layout and the [B, A] action layout. Needs each row's live tokens in its slots 0 .. n - 1
        (the driver's layout: packed token seq_off[r] + i is row r's slot i), b["seq_off"] [B + 1], and
        b["act_idx"] [NA] long: the live slots of the flattened [B * A] action axis, padded with the value B * A
        (a trash slot). The row summary comes from row_mean (the mean of the row's tokens after the first), and the
        action embedding, its two token picks and the policy MLP run on the NA listed actions; the policy logits
        are scattered back into [B, A] (-1e4 elsewhere, as masked_fill writes). Rows of length 0 in seq_off (padding
        rows) get unspecified outputs. Same math as _heads per row and action, up to float rounding (the mean is
        accumulated in fp32, the matrix products run on other shapes); tests/test_packed_heads.py."""
        so = b["seq_off"].long()
        N, d = x.shape
        if enc is not None and self.enemy_gate is not None:
            mean = _gated_row_mean(self.row_mean, x, so, enc, self._gate(-1))
        else:
            mean = self.row_mean(x, b["seq_off"])
        c = x[so[:-1].clamp(max=N - 1)] + self.summary_mlp(mean)
        B, A = b["a_mask"].shape
        MA = B * A
        ai = b["act_idx"]
        ac = ai.clamp(max=MA - 1)             # trash entries read some slot; their logits go to the trash slot
        row = torch.div(ac, A, rounding_mode="floor")
        base = so[row]

        def pick(idx, none):
            g = x[(base + idx.clamp(min=0)).clamp(max=N - 1)]
            return torch.where((idx >= 0)[:, None], g, none.to(g.dtype))

        e = (self.a_type(b["a_type"].reshape(MA)[ac]) + self.w_s(pick(b["a_src"].reshape(MA)[ac], self.a_none[0]))
             + self.w_t(pick(b["a_tgt"].reshape(MA)[ac], self.a_none[1])) + self.w_f(b["a_f"].reshape(MA, -1)[ac])
             + self.w_c(c)[row])
        lp = self.pol(e).squeeze(-1)
        full = lp.new_full((MA + 1,), -1e4)
        full[ai] = lp
        return (full[:MA].view(B, A), self.outcome(c), self.hp(c), self.hp_floor(c).squeeze(-1))

    def forward_flat(self, b):
        """Flat layout (az_driver nextBatchFlat): one token axis per row, the run token first, the other tokens in
        TOKEN_TYPES order, then padding. b["tok_type"] [B, T] long (index into TOKEN_TYPES), b["ids"] [B, T, 4]
        long, b["f"] [B, T, 64] float, b["mask"] [B, T] bool; actions as in forward_segments, with src / tgt
        indexing this token axis. Same math as forward_segments on the same live tokens: the per-type float
        projection is computed for all types and the token's own type is picked."""
        if "pack_idx" in b:
            return self.forward_packed(b)
        tt = b["tok_type"]
        d = self.type_emb.weight.shape[1]
        W = torch.stack([self.proj[t].weight for t in TOKEN_TYPES])          # [K, d, 64]
        bias = torch.stack([self.proj[t].bias for t in TOKEN_TYPES])         # [K, d]
        K = W.shape[0]
        P = torch.nn.functional.linear(b["f"], W.reshape(K * d, -1), bias.reshape(-1))
        P = P.view(*tt.shape, K, d)
        proj = torch.gather(P, 2, tt[..., None, None].expand(-1, -1, 1, d)).squeeze(2)
        x = self.in_norm(self.type_emb(tt) + self.ids(b["ids"]).sum(2) + proj)
        mask = b["mask"]
        if self.enemy_on and not self.sdpa:
            raise ValueError("enemy_bias / enemy_gate need sdpa = True")
        cls = token_classes(tt, b["ids"], b["f"]) if self.enemy_on else None
        h = self.out_norm(self.sdpa_trunk(x, mask, cls) if self.sdpa else self.trunk(x, src_key_padding_mask=~mask))
        return self._heads(h, mask, b, None if cls is None else enc_of(cls))

    sdpa = False   # True: run the trunk through sdpa_trunk (same weights and math, fused attention kernel)
    fused_layer = None   # load_fused_layer(): with varlen_attn, each layer as norm1+QKV / attention / out+FFN kernels
    varlen_attn = None   # load_kernel("varlen_attn"): with b["seq_off"], attention on the packed tokens (no padding)
    fused_ffn = None   # load_fused_ffn(): forward_packed runs each layer's LayerNorm + FFN + residual as one Triton kernel
    row_mean = None   # load_kernel("row_mean"): with packed_heads, the row summary on the packed tokens
    packed_heads = False   # True (inference, with row_mean, b["seq_off"], b["act_idx"]): _heads_packed
    attn_math = False   # True: sdpa_trunk / forward_packed attend with plain matmuls + softmax (fp32) instead of SDPA

    def _attend(self, q, k, v, keep):
        if not self.attn_math:
            return torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=keep)
        s = (q @ k.transpose(-1, -2)).float() * q.shape[-1] ** -0.5
        p = torch.softmax(s.masked_fill(~keep, float("-inf")), -1)
        return p.to(v.dtype) @ v

    def _tab(self, li):
        """Layer li's bias table, only its entries with an encounter class (query or key) used: the other pairs get
        no bias, so states without encounter tokens attend as without the flag."""
        C = self.enemy_bias.shape[-1]
        e = torch.zeros(C, dtype=torch.bool, device=self.enemy_bias.device)
        e[1:4] = True
        return self.enemy_bias[li] * (e[:, None] | e[None, :]).to(self.enemy_bias.dtype)

    @staticmethod
    def _enemy_split(cls, mask):
        """(rows with encounter tokens, the other rows, the others' longest length) for _attend_enemy."""
        has = enc_of(cls).any(1)
        rows = torch.nonzero(has).squeeze(1)
        non = torch.nonzero(~has).squeeze(1)
        Tn = max(1, int(mask[non].sum(1).max())) if non.numel() else 1
        return rows, non, Tn

    def _attend_enemy(self, q, k, v, keep, li, cls, rows):
        """Attention of layer li with the encounter-token parts (cls [B, T] token classes, rows: the rows that hold
        encounter tokens; rows = _enemy_split(...)). Rows without them attend as without the flag (one pass, on their own
        longest length). Rows with them: g x attention
        with the encounter keys and the class bias + (1 - g) x attention without the encounter keys (enemy_gate;
        without a gate: the first part only). The bias goes in as extra q / k columns: q' = [q / sqrt(dh),
        TAB[h, cls_q, :]], k' = [k, onehot(cls_k)], so q'.k' = q.k / sqrt(dh) + TAB[h, cls_q, cls_k] and
        scaled_dot_product_attention keeps its fused kernels (a float mask [B, H, T, T] would not: the first live
        test's trainer ran about 30x slower with it)."""
        F = torch.nn.functional
        dh = q.shape[-1]

        def sdpa(q_, k_, v_, m, scale=None):
            if not self.attn_math:
                return F.scaled_dot_product_attention(q_, k_, v_, attn_mask=m, scale=scale)
            s = (q_ @ k_.transpose(-1, -2)).float() * (q_.shape[-1] ** -0.5 if scale is None else scale)
            return torch.softmax(s.masked_fill(~m, float("-inf")), -1).to(v_.dtype) @ v_

        rows, non, Tn = rows
        if rows.numel() == 0:
            return sdpa(q, k, v, keep)
        T = q.shape[2]
        # rows without encounter tokens: one pass over their own longest length Tn (the batch's T is set by the
        # rows with encounter tokens; padded attention costs T^2 per row)
        o = None
        if non.numel():
            on = sdpa(q[non][:, :, :Tn], k[non][:, :, :Tn], v[non][:, :, :Tn], keep[non][..., :Tn])
            o = q.new_zeros(q.shape).index_copy(0, non, F.pad(on, (0, 0, 0, T - Tn)))
        else:
            o = q.new_zeros(q.shape)
        qs, ks, vs, ms, cs = q[rows], k[rows], v[rows], keep[rows], cls[rows]
        gated = self.enemy_gate is not None
        if self.enemy_bias is not None:
            tab = self._tab(li).to(q.dtype)                              # [H, C, C]
            C = tab.shape[-1]
            H = q.shape[1]
            pad = (-(dh + C)) % 8
            oh = F.one_hot(cs, C).to(q.dtype)                            # [R, T, C]
            # [R, H, T, C]: the row of the query's class, as a matmul (an index gather's backward accumulates with
            # index_put: ~1 ms per layer on the PC)
            qx = torch.einsum("rtc,hcd->rhtd", oh, tab)
            kx = oh[:, None].expand(-1, H, -1, -1)
            z = qs.new_zeros(*qs.shape[:-1], pad)
            qa = torch.cat([qs * dh ** -0.5, qx, z], -1)
            ka = torch.cat([ks, kx, z], -1)
            va = torch.cat([vs, vs.new_zeros(*vs.shape[:-1], C + pad)], -1)
            if gated:
                # both parts in one call: the second has no bias columns (zeros) and no encounter keys
                qn = torch.cat([qs * dh ** -0.5, qs.new_zeros(*qs.shape[:-1], C + pad)], -1)
                R = qs.shape[0]
                ob = sdpa(torch.cat([qa, qn]), torch.cat([ka, ka]), torch.cat([va, va]),
                          torch.cat([ms, ms & ~enc_of(cs)[:, None, None, :]]),
                          1.0)[..., :dh]
                g = self._gate(li).to(o.dtype)
                oa = g * ob[:R] + (1 - g) * ob[R:]
            else:
                oa = sdpa(qa, ka, va, ms, 1.0)[..., :dh]
        else:
            oa = sdpa(qs, ks, vs, ms)
            if gated:
                g = self._gate(li).to(o.dtype)
                oa = g * oa + (1 - g) * sdpa(qs, ks, vs, ms & ~enc_of(cs)[:, None, None, :])
        return o.index_copy(0, rows, oa.to(o.dtype))

    def sdpa_trunk(self, x, mask, cls=None):
        """self.trunk's math (pre-norm encoder layers, key padding mask, exact GELU) written with one QKV matmul and
        F.scaled_dot_product_attention per layer instead of nn.MultiheadAttention, so the attention runs as one
        fused kernel. Equal to self.trunk up to float rounding (tests/test_amber_net_flat.py). cls [B, T]
        (enemy_bias): the token classes of the attention bias."""
        F = torch.nn.functional
        B, T, d = x.shape
        keep = mask[:, None, None, :]                      # [B, 1, 1, T], True = attend
        rows = None if cls is None else self._enemy_split(cls, mask)
        for li, layer in enumerate(self.trunk.layers):
            a = layer.self_attn
            H = a.num_heads
            y = layer.norm1(x)
            qkv = F.linear(y, a.in_proj_weight, a.in_proj_bias).view(B, T, 3, H, d // H).permute(2, 0, 3, 1, 4)
            o = (self._attend(qkv[0], qkv[1], qkv[2], keep) if cls is None
                 else self._attend_enemy(qkv[0], qkv[1], qkv[2], keep, li, cls, rows))
            x = x + a.out_proj(o.transpose(1, 2).reshape(B, T, d))
            x = x + layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))
        return x

    def forward_packed(self, b):
        """forward_flat with the per-token work (input embedding, LayerNorms, QKV / output projections, FFN) done
        only on the live tokens. b["pack_idx"] [N] long lists the live slots of the flattened [B * T] token axis,
        padded up to a bucketed N with the value B * T (a trash slot); only attention runs on the padded [B, T]
        layout. Optional b["unpack_idx"] [B * T] long (pack_index(..., inverse=True)): for each slot its row in the
        packed axis, N for a dead slot; then packed -> padded is one gather instead of zero fill + scatter.
        Same math as forward_flat with sdpa = True on the live tokens (tests/test_amber_net_flat.py). tok_type / ids
        / f may instead come packed ([N], [N, 4], [N, 64], rows in pack_idx order; B, T are then mask's shape): the
        same values without the dead slots, so the same outputs."""
        F = torch.nn.functional
        tt, idx, mask = b["tok_type"], b["pack_idx"], b["mask"]
        B, T = mask.shape
        M = B * T
        d = self.type_emb.weight.shape[1]
        ip = idx.clamp(max=M - 1)                 # trash entries read some token; their results go to the trash slot
        if tt.dim() == 1:
            # Tokens already packed (RunDriver.next_flat(packed_tokens=True)): tok_type [N], ids [N, 4], f [N, 64]
            # are the live tokens in pack_idx order (entries past the live ones are trash), i.e. exactly the rows
            # the gathers below would pick from the [B, T] layout.
            tt_p, f_p, ids_p = tt, b["f"], b["ids"]
        else:
            tt_p, f_p, ids_p = tt.reshape(M)[ip], b["f"].reshape(M, -1)[ip], b["ids"].reshape(M, -1)[ip]
        W = torch.stack([self.proj[t].weight for t in TOKEN_TYPES])
        bias = torch.stack([self.proj[t].bias for t in TOKEN_TYPES])
        K = W.shape[0]
        P = F.linear(f_p, W.reshape(K * d, -1), bias.reshape(-1)).view(-1, K, d)
        proj = torch.gather(P, 1, tt_p[:, None, None].expand(-1, 1, d)).squeeze(1)
        x = self.in_norm(self.type_emb(tt_p) + self.ids(ids_p).sum(1) + proj)
        keep = mask[:, None, None, :]
        inv = b.get("unpack_idx")

        def unpack(v):   # packed [N, c] -> padded [M, c], dead slots 0
            if inv is not None:     # one gather from v plus a zero row
                return torch.cat([v, v.new_zeros(1, v.shape[1])])[inv]
            full = v.new_zeros(M + 1, v.shape[1])
            full[idx] = v
            return full[:M]

        varlen = self.varlen_attn is not None and "seq_off" in b
        cls_p = cls_pad = cls_i = None
        if self.enemy_on:
            if varlen:
                cls_p, cls_i = _packed_classes(tt_p, ids_p, f_p)
            else:
                cls_p = token_classes(tt_p, ids_p, f_p)
                cls_pad = unpack(cls_p[:, None]).view(B, T)
                rows = self._enemy_split(cls_pad, mask)

        def vattn(qkv, li):
            if cls_i is None:
                return self.varlen_attn(qkv, b["seq_off"], H, T)
            tab = None if self.enemy_bias is None else self._tab(li)
            gate = None if self.enemy_gate is None else self._gate(li)
            return _enemy_vattn(self.varlen_attn, qkv, b["seq_off"], H, T, cls_i, tab, gate)

        for li, layer in enumerate(self.trunk.layers):
            a = layer.self_attn
            H = a.num_heads
            if self.fused_layer is not None and varlen:
                # whole layer in three kernels: norm1 + QKV, varlen attention, out_proj + residual + norm2 + FFN
                ln_qkv, out_ffn = self.fused_layer
                x = x.contiguous()
                o = vattn(ln_qkv(x, layer), li)
                x = out_ffn(x, o, layer)
                continue
            qkv_p = F.linear(layer.norm1(x), a.in_proj_weight, a.in_proj_bias)
            if varlen:
                x = x + a.out_proj(vattn(qkv_p.contiguous(), li))
            else:
                qkv = unpack(qkv_p).view(B, T, 3, H, d // H).permute(2, 0, 3, 1, 4)
                o = (self._attend(qkv[0], qkv[1], qkv[2], keep) if cls_pad is None
                     else self._attend_enemy(qkv[0], qkv[1], qkv[2], keep, li, cls_pad, rows))
                x = x + a.out_proj(o.transpose(1, 2).reshape(M, d)[ip])
            if self.fused_ffn is not None:
                x = self.fused_ffn(x.contiguous(), layer)
            else:
                x = x + layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))
        if (self.packed_heads and self.row_mean is not None and "seq_off" in b and "act_idx" in b
                and not (self.pol_soft is not None and self.training)):
            return self._heads_packed(self.out_norm(x).contiguous(), b, None if cls_p is None else enc_of(cls_p))
        return self._heads(unpack(self.out_norm(x)).view(B, T, d), mask, b,
                           None if cls_p is None else enc_of(unpack(cls_p[:, None]).view(B, T)))

    def forward_segments(self, b):
        """b: per token type t in TOKEN_TYPES, b[t + "_ids"] [B, n_t, 4] long, b[t + "_f"] [B, n_t, 64] float,
        b[t + "_mask"] [B, n_t] bool (the run segment has n = 1 and is always live); b["a_type"] [B, A] long,
        b["a_src"], b["a_tgt"] [B, A] long token index into the concatenated segments (-1 = none),
        b["a_f"] [B, A, 8] float, b["a_mask"] [B, A] bool. Returns (policy logits [B, A], outcome logits,
        HP-class logits, per-floor HP)."""
        if self.enemy_on:
            raise ValueError("enemy_bias / enemy_gate: forward_segments is not supported (use the flat layout with sdpa)")
        toks, masks = [], []
        for i, t in enumerate(TOKEN_TYPES):
            ids = b[t + "_ids"]
            x = self.type_emb.weight[i] + self.ids(ids).sum(2) + self.proj[t](b[t + "_f"])
            toks.append(x)
            masks.append(b[t + "_mask"])
        x = self.in_norm(torch.cat(toks, 1))
        mask = torch.cat(masks, 1)
        h = self.out_norm(self.trunk(x, src_key_padding_mask=~mask))
        return self._heads(h, mask, b)


# Synthetic token counts per type, ~40 in all (the page's average; mostly cards and relics): a mid-run combat.
DEFAULT_COUNTS = {"run": 1, "player": 1, "status": 4, "monster": 2, "card": 22, "relic": 8, "potion": 2,
                  "option": 0, "map": 0}


def synthetic_batch(B, counts=None, actions=10, rng=None, live_frac=1.0):
    """A batch with `counts[t]` slots per token type, a share `live_frac` of each non-run segment live (1.0 = no
    padding), and `actions` legal actions per row whose source / target point at card / monster tokens."""
    import numpy as np
    counts = dict(DEFAULT_COUNTS if counts is None else counts)
    counts["run"] = 1
    rng = rng or np.random.default_rng(0)
    b, off, offs = {}, 0, {}
    for t in TOKEN_TYPES:
        n = counts.get(t, 0)
        offs[t] = off
        n_slot = max(n, 1)   # an empty segment keeps one masked slot so every tensor has a length
        b[t + "_ids"] = torch.from_numpy(rng.integers(1, ID_VOCAB, (B, n_slot, N_CAT)))
        b[t + "_f"] = torch.from_numpy(rng.normal(0, 1, (B, n_slot, N_FLOAT)).astype(np.float32))
        m = torch.zeros(B, n_slot, dtype=torch.bool)
        if n:
            k = n if t == "run" else max(1, round(n * live_frac))
            m[:, :k] = True
        b[t + "_mask"] = m
        off += n_slot
    b["a_type"] = torch.from_numpy(rng.integers(0, ACTION_TYPES, (B, actions)))
    live = lambda t: max(1, round(counts[t] * live_frac)) if counts[t] else 1   # noqa: E731
    card0, ncard = offs["card"], live("card")       # sources / targets point at live tokens
    mon0, nmon = offs["monster"], live("monster")
    b["a_src"] = torch.from_numpy(card0 + rng.integers(0, ncard, (B, actions)))
    b["a_tgt"] = torch.from_numpy(np.where(rng.random((B, actions)) < 0.5, mon0 + rng.integers(0, nmon, (B, actions)),
                                           -1))
    b["a_f"] = torch.from_numpy(rng.normal(0, 1, (B, actions, N_ACT_FEAT)).astype(np.float32))
    b["a_mask"] = torch.ones(B, actions, dtype=torch.bool)
    return b


def pack_index(mask, step=1, inverse=False):
    """pack_idx for forward_packed: the live slots of mask [B, T] in row-major order, padded with B * T up to a
    multiple of `step`. inverse=True also returns unpack_idx: per slot its packed row, npad for a dead slot."""
    m = mask.reshape(-1)
    idx = torch.nonzero(m).squeeze(1)
    n = idx.numel()
    npad = -(-n // step) * step
    pk = torch.cat([idx, idx.new_full((npad - n,), m.numel())])
    if not inverse:
        return pk
    inv = torch.full((m.numel(),), npad, dtype=torch.long, device=m.device)
    inv[idx] = torch.arange(n, device=m.device)
    return pk, inv


def jitter_1d_params(module, scale=0.3, seed=0):
    """Tests: add noise to every 1-D parameter (biases, LayerNorm weight / bias). Default init leaves attention biases
    at 0 and LayerNorms at (1, 0), so a kernel that drops a bias or swaps two LayerNorms would still match."""
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for p in module.parameters():
            if p.dim() == 1:
                p.add_(torch.randn(p.shape, generator=g).to(p) * scale)
    return module


def seq_offsets(mask):
    """seq_off for varlen attention: row r's live tokens are packed rows seq_off[r] .. seq_off[r + 1] (pack_index
    order), as int32 [B + 1]."""
    c = mask.sum(1).to(torch.int32)
    return torch.cat([c.new_zeros(1), torch.cumsum(c, 0, dtype=torch.int32)])


def live_tokens(b):
    live = sum(b[t + "_mask"].sum(1) for t in TOKEN_TYPES).float().mean()
    padded = sum(b[t + "_mask"].shape[1] for t in TOKEN_TYPES)
    return float(live), int(padded)


def to_flat(b):
    """The flat layout of a segmented batch (same live tokens, src / tgt remapped), padded to the longest row."""
    B = b["run_ids"].shape[0]
    rows = []
    T = 0
    for r in range(B):
        types, ids, fs, remap, pos, off = [], [], [], {}, 0, 0
        for k, t in enumerate(TOKEN_TYPES):
            m = b[t + "_mask"][r]
            for i in range(m.shape[0]):
                if m[i]:
                    remap[off + i] = pos
                    types.append(k)
                    ids.append(b[t + "_ids"][r, i])
                    fs.append(b[t + "_f"][r, i])
                    pos += 1
            off += m.shape[0]
        rows.append((types, ids, fs, remap))
        T = max(T, pos)
    out = {"tok_type": torch.zeros(B, T, dtype=torch.long), "ids": torch.zeros(B, T, N_CAT, dtype=torch.long),
           "f": torch.zeros(B, T, N_FLOAT), "mask": torch.zeros(B, T, dtype=torch.bool)}
    for r, (types, ids, fs, remap) in enumerate(rows):
        n = len(types)
        out["tok_type"][r, :n] = torch.tensor(types)
        out["ids"][r, :n] = torch.stack(ids)
        out["f"][r, :n] = torch.stack(fs)
        out["mask"][r, :n] = True
    for k in ("a_src", "a_tgt"):
        x = b[k].clone()
        for r, (_, _, _, remap) in enumerate(rows):
            for a in range(x.shape[1]):
                v = int(x[r, a])
                x[r, a] = remap[v] if v >= 0 else -1
        out[k] = x
    for k in ("a_type", "a_f", "a_mask"):
        out[k] = b[k]
    return out
