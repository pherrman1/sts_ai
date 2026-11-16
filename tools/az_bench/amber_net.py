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

import torch
import torch.nn as nn

TOKEN_TYPES = ("run", "player", "status", "monster", "card", "relic", "potion", "option", "map")
N_CAT, N_FLOAT, N_ACT_FEAT = 4, 64, 8
ID_VOCAB = 1024        # our choice: one shared space for cards, relics, enemies, statuses, potions, options
ACTION_TYPES = 16      # our choice
OUTCOME_CLASSES = 57   # our choice: win + death on floor 1..56
HP_CLASSES = 256       # page: current-floor HP as a class, capped at 255

# Sizes chosen to land on the page's three parameter counts (d, layers); heads = d // 32.
SIZES = {"0.44M": (64, 6), "1.2M": (128, 4), "5.4M": (256, 5)}


def mlp(i, h, o):
    return nn.Sequential(nn.Linear(i, h), nn.GELU(), nn.Linear(h, o))


class AmberNet(nn.Module):
    def __init__(self, d=96, layers=3, heads=None):
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
        self.hp_floor = mlp(d, d, 1)

    def forward(self, b):
        """b: per token type t in TOKEN_TYPES, b[t + "_ids"] [B, n_t, 4] long, b[t + "_f"] [B, n_t, 64] float,
        b[t + "_mask"] [B, n_t] bool (the run segment has n = 1 and is always live); b["a_type"] [B, A] long,
        b["a_src"], b["a_tgt"] [B, A] long token index into the concatenated segments (-1 = none),
        b["a_f"] [B, A, 8] float, b["a_mask"] [B, A] bool. Returns (policy logits [B, A], outcome logits,
        HP-class logits, per-floor HP)."""
        toks, masks = [], []
        for i, t in enumerate(TOKEN_TYPES):
            ids = b[t + "_ids"]
            x = self.type_emb.weight[i] + self.ids(ids).sum(2) + self.proj[t](b[t + "_f"])
            toks.append(x)
            masks.append(b[t + "_mask"])
        x = self.in_norm(torch.cat(toks, 1))
        mask = torch.cat(masks, 1)
        h = self.out_norm(self.trunk(x, src_key_padding_mask=~mask))
        live = mask[:, 1:, None].to(h.dtype)
        rest = (h[:, 1:] * live).sum(1) / live.sum(1).clamp(min=1)
        c = h[:, 0] + self.summary_mlp(rest)
        d = h.shape[-1]

        def pick(idx, none):
            g = torch.gather(h, 1, idx.clamp(min=0)[..., None].expand(-1, -1, d))
            return torch.where((idx >= 0)[..., None], g, none.to(g.dtype))

        e = (self.a_type(b["a_type"]) + self.w_s(pick(b["a_src"], self.a_none[0]))
             + self.w_t(pick(b["a_tgt"], self.a_none[1])) + self.w_f(b["a_f"]) + self.w_c(c)[:, None])
        logits = self.pol(e).squeeze(-1).masked_fill(~b["a_mask"], -1e4)
        return logits, self.outcome(c), self.hp(c), self.hp_floor(c).squeeze(-1)


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
    card0, ncard = offs["card"], max(counts["card"], 1)
    mon0, nmon = offs["monster"], max(counts["monster"], 1)
    b["a_src"] = torch.from_numpy(card0 + rng.integers(0, ncard, (B, actions)))
    b["a_tgt"] = torch.from_numpy(np.where(rng.random((B, actions)) < 0.5, mon0 + rng.integers(0, nmon, (B, actions)),
                                           -1))
    b["a_f"] = torch.from_numpy(rng.normal(0, 1, (B, actions, N_ACT_FEAT)).astype(np.float32))
    b["a_mask"] = torch.ones(B, actions, dtype=torch.bool)
    return b


def live_tokens(b):
    live = sum(b[t + "_mask"].sum(1) for t in TOKEN_TYPES).float().mean()
    padded = sum(b[t + "_mask"].shape[1] for t in TOKEN_TYPES)
    return float(live), int(padded)
