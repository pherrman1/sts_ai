#!/usr/bin/env python3
"""CombatPVNet parity harness + shared native-model loader.

Rebuilds the PyTorch model exactly from the exported native .txt (the same
token stream the C++ loader reads) and either:

  - writes a parity CSV for the C++ `pvnetparity` mode in apps/one_combat.cpp
    (default, run as a script), or
  - serves the rebuilt model to other scripts (eval_combat_pvnet.py) via
    load_native_model().

Parity CSV per-row layout (after 1766 state feats + 14 action feats):
  global embedding (entity_dim), policy logit, win prob, death prob,
  HP quantiles (nquantile, clamped >=0 as in C++), potion probs (sigmoid),
  turns (clamped >=0 as in C++).

Usage: python3 combat_pvnet_parity.py <model.txt> <fair_v.csv> <fair_p.csv>
       <out.csv> [n_value_rows] [n_policy_rows]
"""
import numpy as np
import pandas as pd
import torch
from torch import nn


# ── Native file parsing ─────────────────────────────────────────────────────
def parse_model(path):
    with open(path) as f:
        toks = f.read().split()
    assert toks[0] in ("combat_pvnet_v1", "combat_utility_v1"), \
        f"not a combat_pvnet_v1 / combat_utility_v1 file: {toks[0]}"
    is_util = toks[0] == "combat_utility_v1"
    i = 1
    def value():
        nonlocal i
        v = toks[i]; i += 1
        return v
    def tensor(name, n):
        nonlocal i
        assert toks[i] == name, f"expected {name} at token {i}, got {toks[i]}"
        i += 1
        a = np.array([float(toks[i + j]) for j in range(n)], np.float32)
        i += n
        return a
    hdr = {}
    names = ("entity_dim", "hidden_dim", "num_heads", "num_layers",
             "nbins" if is_util else "nquantile", "win_bonus")
    for name in names:
        assert toks[i] == name, f"expected header {name} at token {i}, got {toks[i]}"
        i += 1
        hdr[name] = float(value())
    D, H, HDS, L, NQ = (int(hdr[n]) for n in
                        ("entity_dim", "hidden_dim", "num_heads",
                         "num_layers", "nbins" if is_util else "nquantile"))
    assert value() == "nscalar"
    ns = int(value())
    scalar_sel = np.array([int(value()) for _ in range(ns)], np.int32)
    tensors = {}
    for name, n in [
            ("scalar_mean", 64), ("scalar_inv", 64),
            ("mon_cont_mean", 7), ("mon_cont_inv", 7),
            ("scalar_weight", D * 64), ("scalar_bias", D),
            ("card_embed", 371 * D), ("zone_pos", 4 * D), ("type_embed", 6 * D),
            ("global_token", D), ("relic_embed", 128 * 64),
            ("potion_embed", 44 * 32), ("encounter_embed", 128 * 32),
            ("mon_id_embed", 256 * 64), ("mon_intent_embed", 32 * 16),
            ("mon_enc_weight", 87 * D), ("mon_enc_bias", D)]:
        tensors[name] = tensor(name, n)
    for name, n, proj in [("relic_proj", D * 64, D != 64),
                          ("potion_proj", D * 32, D != 32),
                          ("enc_proj", D * 32, D != 32)]:
        if toks[i].startswith(name + "_weight"):
            tensors[name + "_weight"] = tensor(name + "_weight", n)
            tensors[name + "_bias"] = tensor(name + "_bias", D)
        elif proj:
            raise AssertionError(f"missing {name} projection for entity_dim {D}")
    for l in range(L):
        p = f"layer_{l}_"
        for name, n in [(p + "qkv_weight", 3 * D * D), (p + "qkv_bias", 3 * D),
                        (p + "proj_weight", D * D), (p + "proj_bias", D),
                        (p + "ln1_weight", D), (p + "ln1_bias", D),
                        (p + "ln2_weight", D), (p + "ln2_bias", D),
                        (p + "ffn0_weight", H * D), (p + "ffn0_bias", H),
                        (p + "ffn2_weight", D * H), (p + "ffn2_bias", D)]:
            tensors[name] = tensor(name, n)
    if is_util:
        tensors["util_weight"] = tensor("util_weight", NQ * D)
        tensors["util_bias"] = tensor("util_bias", NQ)
    else:
        for name, n in [("policy_act_enc_0_weight", 64 * 14),
                        ("policy_act_enc_0_bias", 64),
                        ("policy_act_enc_2_weight", D * 64),
                        ("policy_act_enc_2_bias", D),
                        ("policy_scorer_0_weight", D * 3 * D),
                        ("policy_scorer_0_bias", D),
                        ("policy_scorer_2_weight", D), ("policy_scorer_2_bias", 1),
                        ("win_weight", D), ("win_bias", 1),
                        ("death_weight", D), ("death_bias", 1),
                        ("quantile_weight", NQ * D), ("quantile_bias", NQ),
                        ("potion_weight", 44 * D), ("potion_bias", 44),
                        ("turns_weight", D), ("turns_bias", 1)]:
            tensors[name] = tensor(name, n)
    assert i == len(toks), f"unparsed tokens remain: {i}/{len(toks)}"
    return D, H, HDS, L, NQ, scalar_sel, tensors, is_util


# ── CSV column layout (mirrors train_combat_pvnet.py) ───────────────────────
def column_groups(canonical):
    """Return (zones, relic_cols, potion_cols, mon_cols, scalar_cols) for a
    canonical column list, asserting the 1766-feature layout."""
    assert len(canonical) == 1766, f"Expected 1766 canonical, got {len(canonical)}"
    zones = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
    relic_cols = [f"r{i}" for i in range(128)]
    potion_cols = [f"pot{i}" for i in range(44)]
    mon_cols = [[f"m{i}{s}" for s in ("Id", "Hp", "Block", "Str", "Intent",
                                      "Atk", "Vuln", "Weak", "Poison")]
                for i in range(5)]
    mon_flat = [c for row in mon_cols for c in row]
    entity_set = set(relic_cols + potion_cols + mon_flat + ["encounter"] +
                     [c for z in zones for c in z])
    scalar_cols = [c for c in canonical if c not in entity_set]
    assert len(scalar_cols) == 64
    return zones, relic_cols, potion_cols, mon_cols, scalar_cols


# ── Model structure (mirrors train_combat_pvnet.py) ─────────────────────────
class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden, heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, hidden), nn.GELU(),
                                 nn.Linear(hidden, dim))
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        a, _ = self.attn(x, x, x)
        x = self.ln1(x + a)
        return self.ln2(x + self.ffn(x))


class SharedEncoder(nn.Module):
    def __init__(self, dim, hidden, heads, layers):
        super().__init__()
        self.dim = dim
        self.card_embed = nn.Parameter(torch.randn(371, dim) * 0.02)
        self.relic_embed = nn.Parameter(torch.randn(128, 64) * 0.02)
        self.relic_proj = nn.Linear(64, dim) if 64 != dim else nn.Identity()
        self.potion_embed = nn.Parameter(torch.randn(44, 32) * 0.02)
        self.potion_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.enc_embed = nn.Embedding(128, 32)
        self.enc_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.mon_id = nn.Embedding(256, 64)
        self.mon_intent = nn.Embedding(32, 16)
        self.zone_pos = nn.Parameter(torch.randn(4, dim) * 0.02)
        self.type_embed = nn.Parameter(torch.randn(6, dim) * 0.02)
        self.global_token = nn.Parameter(torch.randn(1, 1, dim) * 0.02)
        self.scalar_enc = nn.Sequential(nn.Linear(64, dim), nn.ReLU())
        self.mon_enc = nn.Sequential(nn.Linear(7 + 64 + 16, dim), nn.ReLU())
        self.layers = nn.ModuleList([TransformerLayer(dim, hidden, heads)
                                     for _ in range(layers)])
        self.register_buffer("scalar_mean", torch.zeros(64))
        self.register_buffer("scalar_inv", torch.ones(64))
        self.register_buffer("mon_mean", torch.zeros(7))
        self.register_buffer("mon_inv", torch.ones(7))

    def forward(self, scalar, cards, relics, potions, encounter, mids, intents,
                mcont, mmask):
        D = self.dim
        B = scalar.shape[0]
        tokens = []
        s = (scalar - self.scalar_mean) * self.scalar_inv
        tokens.append((self.scalar_enc(s) + self.type_embed[0]).unsqueeze(1))
        for z in range(4):
            t = torch.einsum("bc,ce->be", cards[:, z, :].float(),
                             self.card_embed)
            tokens.append((t + self.zone_pos[z] + self.type_embed[1])
                          .unsqueeze(1))
        t = torch.einsum("br,re->be", relics.float(), self.relic_embed)
        if 64 != D: t = self.relic_proj(t)
        tokens.append((t + self.type_embed[2]).unsqueeze(1))
        t = torch.einsum("bp,pe->be", potions.float(), self.potion_embed)
        if 32 != D: t = self.potion_proj(t)
        tokens.append((t + self.type_embed[3]).unsqueeze(1))
        t = self.enc_embed(encounter.long())
        if 32 != D: t = self.enc_proj(t)
        tokens.append((t + self.type_embed[4]).unsqueeze(1))
        for s in range(5):
            alive = mmask[:, s]
            if not alive.any():
                tokens.append(torch.zeros(B, 1, D))
                continue
            me = self.mon_id(mids[:, s].long().clamp(0, 255))
            ie = self.mon_intent(intents[:, s].long().clamp(0, 31))
            mc = (mcont[:, s, :] - self.mon_mean) * self.mon_inv
            t = self.mon_enc(torch.cat([me, ie, mc], dim=-1)) + self.type_embed[5]
            tokens.append((t * alive.float().unsqueeze(-1)).unsqueeze(1))
        x = torch.cat([self.global_token.expand(B, -1, -1)] + tokens, dim=1)
        for layer in self.layers:
            x = layer(x)
        return x[:, 0, :]


class PolicyHead(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.act_enc = nn.Sequential(nn.Linear(14, 64), nn.ReLU(),
                                     nn.Linear(64, dim), nn.ReLU())
        self.scorer = nn.Sequential(nn.Linear(3 * dim, dim), nn.ReLU(),
                                    nn.Linear(dim, 1))

    def forward(self, z_global, action_feats):
        ea = self.act_enc(action_feats)
        ctx = torch.cat([z_global, ea, z_global * ea], dim=-1)
        return self.scorer(ctx).squeeze(-1)


class PolicyValueNet(nn.Module):
    def __init__(self, dim=128, hidden=256, heads=4, layers=2, nq=11):
        super().__init__()
        self.encoder = SharedEncoder(dim, hidden, heads, layers)
        self.policy = PolicyHead(dim)
        self.win = nn.Linear(dim, 1)
        self.death = nn.Linear(dim, 1)
        self.quantile = nn.Linear(dim, nq)
        self.potion = nn.Linear(dim, 44)
        self.turns = nn.Linear(dim, 1)


class UtilityNet(nn.Module):
    """Value-only: shared encoder + single utility-distribution head (nbins)."""

    def __init__(self, dim=128, hidden=256, heads=4, layers=2, nbins=51):
        super().__init__()
        self.encoder = SharedEncoder(dim, hidden, heads, layers)
        self.util = nn.Linear(dim, nbins)


RENAME = {
    "scalar_weight": "encoder.scalar_enc.0.weight",
    "scalar_bias": "encoder.scalar_enc.0.bias",
    "mon_enc_weight": "encoder.mon_enc.0.weight",
    "mon_enc_bias": "encoder.mon_enc.0.bias",
    "zone_pos": "encoder.zone_pos",
    "type_embed": "encoder.type_embed",
    "global_token": "encoder.global_token",
    "card_embed": "encoder.card_embed",
    "relic_embed": "encoder.relic_embed",
    "potion_embed": "encoder.potion_embed",
    "encounter_embed": "encoder.enc_embed.weight",
    "mon_id_embed": "encoder.mon_id.weight",
    "mon_intent_embed": "encoder.mon_intent.weight",
    "relic_proj_weight": "encoder.relic_proj.weight",
    "relic_proj_bias": "encoder.relic_proj.bias",
    "potion_proj_weight": "encoder.potion_proj.weight",
    "potion_proj_bias": "encoder.potion_proj.bias",
    "enc_proj_weight": "encoder.enc_proj.weight",
    "enc_proj_bias": "encoder.enc_proj.bias",
    "policy_act_enc_0_weight": "policy.act_enc.0.weight",
    "policy_act_enc_0_bias": "policy.act_enc.0.bias",
    "policy_act_enc_2_weight": "policy.act_enc.2.weight",
    "policy_act_enc_2_bias": "policy.act_enc.2.bias",
    "policy_scorer_0_weight": "policy.scorer.0.weight",
    "policy_scorer_0_bias": "policy.scorer.0.bias",
    "policy_scorer_2_weight": "policy.scorer.2.weight",
    "policy_scorer_2_bias": "policy.scorer.2.bias",
    "win_weight": "win.weight", "win_bias": "win.bias",
    "death_weight": "death.weight", "death_bias": "death.bias",
    "quantile_weight": "quantile.weight", "quantile_bias": "quantile.bias",
    "potion_weight": "potion.weight", "potion_bias": "potion.bias",
    "turns_weight": "turns.weight", "turns_bias": "turns.bias",
    "util_weight": "util.weight", "util_bias": "util.bias",
}


def load_native_model(path):
    """Rebuild the PyTorch model exactly as the C++ loader sees the .txt.

    Returns (model, D, H, HDS, L, NQ, scalar_sel); for a combat_utility_v1
    file the model has a single `util` head and NQ = nbins."""
    D, H, HDS, L, NQ, scalar_sel, T, is_util = parse_model(path)
    model = (UtilityNet(D, H, HDS, L, NQ) if is_util
             else PolicyValueNet(D, H, HDS, L, NQ))
    model.eval()
    sd = model.state_dict()
    sd["encoder.scalar_mean"] = torch.from_numpy(T["scalar_mean"])
    sd["encoder.scalar_inv"] = torch.from_numpy(T["scalar_inv"])
    sd["encoder.mon_mean"] = torch.from_numpy(T["mon_cont_mean"])
    sd["encoder.mon_inv"] = torch.from_numpy(T["mon_cont_inv"])
    for k, t in T.items():
        if k in ("scalar_mean", "scalar_inv", "mon_cont_mean", "mon_cont_inv"):
            continue
        key = None
        if k.startswith("layer_"):
            l, rest = k[len("layer_"):].split("_", 1)
            rest = {"qkv_weight": "attn.in_proj_weight",
                    "qkv_bias": "attn.in_proj_bias",
                    "proj_weight": "attn.out_proj.weight",
                    "proj_bias": "attn.out_proj.bias",
                    "ln1_weight": "ln1.weight", "ln1_bias": "ln1.bias",
                    "ln2_weight": "ln2.weight", "ln2_bias": "ln2.bias",
                    "ffn0_weight": "ffn.0.weight", "ffn0_bias": "ffn.0.bias",
                    "ffn2_weight": "ffn.2.weight", "ffn2_bias": "ffn.2.bias"}[rest]
            key = f"encoder.layers.{l}.{rest}"
        else:
            key = RENAME.get(k)
        if key is None or key not in sd:
            raise KeyError(f"no slot for {k}")
        sd[key] = torch.from_numpy(t).reshape(sd[key].shape)
    model.load_state_dict(sd)
    return model, D, H, HDS, L, NQ, scalar_sel


# ── State extraction / prediction (mirrors train_combat_pvnet.py) ───────────
def extract_state(df, zones, relic_cols, potion_cols, mon_cols, scalar_cols):
    n = len(df)
    scalar = df[scalar_cols].to_numpy(np.float32)
    cards = np.stack([df[z].to_numpy(np.uint8) for z in zones], axis=1)
    relics = df[relic_cols].to_numpy(np.uint8)
    potions = df[potion_cols].to_numpy(np.uint8)
    encounter = np.clip(df["encounter"].to_numpy(np.int64), 0, 127).astype(np.uint8)
    mids = np.empty((n, 5), np.int16)
    intents = np.empty((n, 5), np.uint8)
    mcont = np.empty((n, 5, 7), np.float32)
    mmask = np.empty((n, 5), np.bool_)
    for i, cols in enumerate(mon_cols):
        mids[:, i] = np.clip(df[cols[0]].to_numpy(np.int64), 0, 255)
        hp = df[cols[1]].to_numpy(np.float32)
        intents[:, i] = np.clip(df[cols[4]].to_numpy(np.int64), 0, 31)
        mcont[:, i] = df[[cols[j] for j in (1, 2, 3, 5, 6, 7, 8)]].to_numpy(np.float32)
        mmask[:, i] = hp > 0
    return scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask


def encode_states(model, df, groups):
    """Encode a DataFrame of states -> (B, D) global embeddings (numpy)."""
    zones, relic_cols, potion_cols, mon_cols, scalar_cols = groups
    scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = \
        extract_state(df, zones, relic_cols, potion_cols, mon_cols, scalar_cols)
    with torch.no_grad():
        z = model.encoder(torch.from_numpy(scalar), torch.from_numpy(cards),
                          torch.from_numpy(relics), torch.from_numpy(potions),
                          torch.from_numpy(enc), torch.from_numpy(mids),
                          torch.from_numpy(intents), torch.from_numpy(mcont),
                          torch.from_numpy(mmask))
        return z.numpy()


def evaluate_heads(model, z, act):
    """Value heads + policy logits for global embeddings z and action rows act.
    Post-processing mirrors CombatPVNet.cpp (clamps/sigmoids)."""
    with torch.no_grad():
        zt = torch.from_numpy(z)
        logit = model.policy(zt, torch.from_numpy(act)).numpy()
        win = torch.sigmoid(model.win(zt).squeeze(-1)).numpy()
        death = torch.sigmoid(model.death(zt).squeeze(-1)).numpy()
        q = torch.clamp(model.quantile(zt), min=0).numpy()
        pot = torch.sigmoid(model.potion(zt)).numpy()
        turns = torch.clamp(model.turns(zt).squeeze(-1), min=0).numpy()
        return logit, win, death, q, pot, turns


# ── Parity CSV generation (script entry point) ──────────────────────────────
def main():
    import sys
    MODEL = sys.argv[1] if len(sys.argv) > 1 else "build/v_combat_pvnet.txt"
    VAL_CSV = sys.argv[2] if len(sys.argv) > 2 else "build/fair_v.csv"
    POL_CSV = sys.argv[3] if len(sys.argv) > 3 else "build/fair_p.csv"
    OUT = sys.argv[4] if len(sys.argv) > 4 else "build/pvnet_parity.csv"
    N_VAL = int(sys.argv[5]) if len(sys.argv) > 5 else 128
    N_POL = int(sys.argv[6]) if len(sys.argv) > 6 else 128
    torch.set_num_threads(4)

    val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
    canonical = [c for c in val_header if c not in ("seed", "fightIdx", "won", "endHp")]
    groups = column_groups(canonical)

    pol_header = list(pd.read_csv(POL_CSV, nrows=0).columns)
    POL_META = ("seed", "fightIdx", "decIdx", "visit", "total")
    action_names = [c for c in pol_header if c not in canonical and c not in POL_META]
    # §3.5: fairgen policy rows carry extra subset-content action features; the
    # PVNet action encoder reads the first 14.
    assert len(action_names) >= 14, f"Expected >=14 action feats, got {len(action_names)}"
    action_names = action_names[:14]

    model, D, H, HDS, L, NQ, scalar_sel = load_native_model(MODEL)
    print(f"[model] d={D} h={H} heads={HDS} layers={L} nq={NQ} params:",
          sum(p.numel() for p in model.parameters()))
    sel = np.array([canonical.index(c) for c in groups[4]], np.int32)
    assert (sel == scalar_sel).all(), "scalar selector mismatch vs CSV order"

    print(f"[parity] reading {N_VAL} value rows from {VAL_CSV}")
    vdf = pd.read_csv(VAL_CSV, usecols=canonical, nrows=N_VAL)
    z_v = encode_states(model, vdf, groups)
    a_v = np.full((N_VAL, 14), -1.0, np.float32)
    a_v[:, 2] = 1.0  # END_TURN dummy action
    pol, win, death, q, pot, turns = evaluate_heads(model, z_v, a_v)

    print(f"[parity] reading {N_POL} policy rows from {POL_CSV}")
    pdf = pd.read_csv(POL_CSV, usecols=canonical + action_names, nrows=N_POL)
    z_p = encode_states(model, pdf[canonical], groups)
    a_p = pdf[action_names].to_numpy(np.float32)
    pol_p, win_p, death_p, q_p, pot_p, turns_p = evaluate_heads(model, z_p, a_p)

    states = np.vstack([vdf[canonical].to_numpy(np.float32),
                        pdf[canonical].to_numpy(np.float32)])
    actions = np.vstack([a_v, a_p])
    globals_ = np.vstack([z_v, z_p])
    pols = np.concatenate([pol, pol_p])
    wins = np.concatenate([win, win_p])
    deaths = np.concatenate([death, death_p])
    qs = np.vstack([q, q_p])
    pots = np.vstack([pot, pot_p])
    turnss = np.concatenate([turns, turns_p])

    n = len(states)
    hdr = (",".join(f"f{i}" for i in range(1766)) + ","
           + ",".join(f"a{i}" for i in range(14)) + ","
           + ",".join(f"g{i}" for i in range(D)) + ",pol,win,death,"
           + ",".join(f"q{i}" for i in range(NQ)) + ","
           + ",".join(f"pot{i}" for i in range(44)) + ",turns")
    with open(OUT, "w") as f:
        f.write(hdr + "\n")
        for i in range(n):
            row = np.concatenate([states[i], actions[i], globals_[i],
                                  [pols[i], wins[i], deaths[i]],
                                  qs[i], pots[i], [turnss[i]]])
            f.write(",".join(f"{x:.8g}" for x in row) + "\n")
    print(f"[parity] wrote {OUT}: {n} rows x {1 + 1766 + 14 + D + 3 + NQ + 44} cols")


if __name__ == "__main__":
    main()
