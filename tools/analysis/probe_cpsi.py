#!/usr/bin/env python3
"""Encounter probes for strategic decisions: evaluate the no-peek combat
outcome model C_psi (train_combat_cpsi.py) on a fixed probe set plus the
ACTUAL upcoming encounters (nextFight0, nextEliteId, bossId) of every
strategicgen2 decision, producing per-decision probe vectors.

Probe vector per slot (9 slots x 6 values = 54):
  slots 0..5   fixed probes: TWO_LOUSE(3), GREMLIN_NOB(15), LAGAVULIN(16),
               THREE_SENTRIES(17), SLIME_BOSS(18), THE_GUARDIAN(19)
  slots 6..8   actual: nextFight0, nextEliteId, bossId (0/INVALID -> zeros)
  values: [P(death), P(win), hp_frac q50, hp_frac q05, turns, max potion prob]

Inputs per decision come from the strategicgen2 rich state block (same raw
columns as richRow): ascension, curHp, maxHp, d0..d370 (deck counts -> deck
bag), r0..r127 (relic counts), pot0..pot43, and the encounter ids from
bossId/nextEliteId/nextFight0..2. The 8 relic counters of the C_psi scalar
block are NOT in the rich row and are set to 0 (documented approximation).

Usage: python3 probe_cpsi.py <tierb.csv> <cpsi.pt> <out.npy> [device]
Writes a float16 npy of shape (nrows, 54) aligned to the CSV rows.
"""
import os, sys

import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_tierb.csv"
PT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/v_combat_cpsi.pt"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/strategic_tierb_probes.npy"
DEVICE = sys.argv[4] if len(sys.argv) > 4 else ("cuda" if torch.cuda.is_available() else "cpu")
print(f"device: {DEVICE}", flush=True)

NCARD, NRELIC, NPOTION, NENCOUNTER = 371, 128, 44, 128
NQUANTILE = 11
ENTITY_DIM, HIDDEN_DIM, NUM_HEADS, NUM_LAYERS = 128, 256, 4, 2
SCALARS = ["ascension", "curHp", "maxHp", "happyFlowerCtr", "incenseBurnerCtr",
           "inkBottleCtr", "inserterCtr", "nunchakuCtr", "penNibCtr",
           "sundialCtr", "panacheCtr"]
FIXED_PROBES = [3, 15, 16, 17, 18, 19]      # TWO_LOUSE..THE_GUARDIAN
ACTUAL_SLOTS = ["nextFight0", "nextEliteId", "bossId"]
NSLOT = len(FIXED_PROBES) + len(ACTUAL_SLOTS)   # 9
NV = 6
NPROBE = NSLOT * NV                            # 54


class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden_dim, num_heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, hidden_dim), nn.GELU(),
                                 nn.Linear(hidden_dim, dim))
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        a, _ = self.attn(x, x, x)
        x = self.ln1(x + a)
        return self.ln2(x + self.ffn(x))


class CPSINet(nn.Module):
    def __init__(self, dim=ENTITY_DIM, hidden_dim=HIDDEN_DIM,
                 num_heads=NUM_HEADS, num_layers=NUM_LAYERS):
        super().__init__()
        self.card_embed = nn.Parameter(torch.randn(NCARD, dim) * .02)
        self.relic_embed = nn.Parameter(torch.randn(NRELIC, 64) * .02)
        self.relic_proj = nn.Linear(64, dim) if 64 != dim else nn.Identity()
        self.potion_embed = nn.Parameter(torch.randn(NPOTION, 32) * .02)
        self.potion_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.enc_embed = nn.Embedding(NENCOUNTER, 32)
        self.enc_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.scalar_encoder = nn.Sequential(nn.Linear(len(SCALARS), dim), nn.ReLU())
        self.layers = nn.ModuleList([TransformerLayer(dim, hidden_dim, num_heads)
                                     for _ in range(num_layers)])
        self.pool_attn = nn.Linear(dim, 1)
        self.death_head = nn.Linear(dim, 1)
        self.win_head = nn.Linear(dim, 1)
        self.hp_head = nn.Linear(dim, 1)
        self.quantile_head = nn.Linear(dim, NQUANTILE)
        self.potion_head = nn.Linear(dim, NPOTION)
        self.turns_head = nn.Linear(dim, 1)

    def forward(self, s, d, r, p, e):
        tokens = [self.scalar_encoder(s).unsqueeze(1),
                  torch.einsum("bc,ce->be", d, self.card_embed).unsqueeze(1),
                  self.relic_proj(torch.einsum("br,re->be", r, self.relic_embed)).unsqueeze(1),
                  self.potion_proj(torch.einsum("bp,pe->be", p, self.potion_embed)).unsqueeze(1),
                  self.enc_proj(self.enc_embed(e.long())).unsqueeze(1)]
        x = torch.cat(tokens, 1)
        for layer in self.layers:
            x = layer(x)
        attn = self.pool_attn(x).squeeze(-1)
        pooled = (torch.softmax(attn, -1).unsqueeze(-1) * x).sum(1)
        return {"death": self.death_head(pooled).squeeze(-1),
                "win": self.win_head(pooled).squeeze(-1),
                "hp": self.hp_head(pooled).squeeze(-1),
                "quantiles": self.quantile_head(pooled),
                "potion_prob": self.potion_head(pooled),
                "turns": self.turns_head(pooled).squeeze(-1)}


ckpt = torch.load(PT, map_location="cpu", weights_only=False)
model = CPSINet().to(DEVICE)
model.load_state_dict(ckpt["state_dict"])
model.eval()
scalar_mean = torch.from_numpy(ckpt["scalar_mean"].astype(np.float32)).to(DEVICE)
scalar_inv = torch.from_numpy(ckpt["scalar_inv"].astype(np.float32)).to(DEVICE)
print(f"loaded {PT}", flush=True)

need = {"seed", "decIdx", "ascension", "curHp", "maxHp",
        "bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2"}
need |= {f"d{i}" for i in range(NCARD)}
need |= {f"r{i}" for i in range(NRELIC)}
need |= {f"pot{i}" for i in range(NPOTION)}

nrows = 0
probe_rows = []


def run_inference(sc, deck, rel, pot, enc):
    """sc (B,11) raw scalars, deck (B,371), rel (B,128), pot (B,44), enc (B,)
    -> probe matrix (B, NV). Scalars are z-scored with the trainer's saved
    stats (train_combat_cpsi.py), matching its training-time forward."""
    sc = (sc - scalar_mean) * scalar_inv
    out = model(sc, deck, rel, pot, enc)
    q = out["quantiles"]                        # raw quantile head (trainer's
                                                # pinball loss uses raw outputs)
    turns = torch.expm1(out["turns"])           # log1p scale
    potion = torch.sigmoid(out["potion_prob"])
    return torch.stack([torch.sigmoid(out["death"]), torch.sigmoid(out["win"]),
                        q[:, NQUANTILE // 2], q[:, 0], turns,
                        potion.max(1).values], 1).detach()


BATCH = 8192
for chunk in pd.read_csv(CSV, usecols=sorted(need), chunksize=100000):
    n = len(chunk)
    enc_slots = np.zeros((n, NSLOT), np.int64)
    enc_slots[:, :6] = FIXED_PROBES
    for i, c in enumerate(ACTUAL_SLOTS):
        enc_slots[:, 6 + i] = np.clip(chunk[c].to_numpy(np.int64), 0, NENCOUNTER - 1)
    sc = np.zeros((n, 11), np.float32)
    sc[:, 0] = chunk["ascension"].to_numpy(np.float32)
    sc[:, 1] = chunk["curHp"].to_numpy(np.float32)
    sc[:, 2] = chunk["maxHp"].to_numpy(np.float32)
    deck = chunk[[f"d{i}" for i in range(NCARD)]].to_numpy(np.float32)
    rel = chunk[[f"r{i}" for i in range(NRELIC)]].to_numpy(np.float32)
    pot = chunk[[f"pot{i}" for i in range(NPOTION)]].to_numpy(np.float32)
    pmat = np.zeros((n, NPROBE), np.float32)
    # per-slot passes keep memory bounded (no n*NSLOT expansion)
    for s in range(NSLOT):
        enc = enc_slots[:, s]
        idx = np.flatnonzero(enc > 0)
        for lo in range(0, len(idx), BATCH):
            hi = min(lo + BATCH, len(idx))
            ids = idx[lo:hi]
            with torch.no_grad():
                r = run_inference(
                    torch.from_numpy(sc[ids]).to(DEVICE),
                    torch.from_numpy(deck[ids]).to(DEVICE),
                    torch.from_numpy(rel[ids]).to(DEVICE),
                    torch.from_numpy(pot[ids]).to(DEVICE),
                    torch.from_numpy(enc[ids]).to(DEVICE))
            pmat[ids, s * NV:(s + 1) * NV] = r.cpu().numpy()
    probe_rows.append(pmat)
    nrows += n
    print(f"processed {nrows:,} rows", flush=True)

probe = np.concatenate(probe_rows, 0).astype(np.float16)
np.save(OUT, probe)
print(f"wrote {OUT}: {probe.shape} float16", flush=True)
