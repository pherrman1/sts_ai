#!/usr/bin/env python3
"""Shared V4 token-state net architecture for the OOC strategic model.

Used by `train_strategic_tok.py` (training) and `export_strategic_tok.py`
(native export + parity). Contract: docs/knowledge-base/architecture/ooc-strategic-v4.md.
`forward` takes a NORMALIZED 50-glob block; the caller applies the checkpoint's
mean/inv and the [-8,8] clamp exactly like the native C++ entry points.
"""
import math

import torch
from torch import nn

NCARD, NREL, NPOT = 372, 181, 48
MAXD, MAXR, MAXP = 96, 64, 8
NGLOB = 50


class Net(nn.Module):
    """V4 token-state net: 50 globals + counted deck/relic/potion tokens with a
    1-layer single-head deck attention, fusion MLP, and the V3 head contract
    (policy, per-screen value, Q). Rung 1..4 zeroes inactive groups (see contract)."""

    def __init__(self, rung=4, nprobes=0):
        super().__init__()
        self.rung = rung
        self.nprobes = nprobes
        self.f = nn.Sequential(nn.Linear(106 + nprobes * 6, 256), nn.LayerNorm(256, eps=1e-5),
                               nn.GELU(approximate="tanh"), nn.Dropout(0.2),
                               nn.Linear(256, 128), nn.GELU(approximate="tanh"))
        self.E_card = nn.Embedding(NCARD, 32)
        self.E_up = nn.Embedding(2, 8)
        self.deckTok = nn.Sequential(nn.Linear(41, 32), nn.GELU(approximate="tanh"))
        self.deckQkv = nn.Linear(32, 96)
        self.deckProj = nn.Linear(32, 32)
        self.deckLn = nn.LayerNorm(32, eps=1e-5)
        self.E_rel = nn.Embedding(NREL, 16)
        self.relTok = nn.Sequential(nn.Linear(17, 16), nn.GELU(approximate="tanh"))
        self.E_pot = nn.Embedding(NPOT, 8)
        self.potTok = nn.Sequential(nn.Linear(9, 8), nn.GELU(approximate="tanh"))
        self.a_bits = nn.Sequential(nn.Linear(32, 32), nn.GELU(approximate="tanh"),
                                    nn.Dropout(0.2), nn.Linear(32, 16))
        self.a_cat = nn.Sequential(nn.Linear(32, 32), nn.GELU(approximate="tanh"),
                                   nn.Linear(32, 16))
        self.cats = nn.ModuleList([nn.Embedding(512, 4) for _ in range(6)])
        self.atype = nn.Embedding(16, 8)
        self.screen = nn.Embedding(16, 8)
        self.ent = nn.Sequential(nn.Linear(37, 32), nn.GELU(approximate="tanh"),
                                 nn.Linear(32, 16))
        self.pol = nn.Sequential(nn.Linear(184, 96), nn.GELU(approximate="tanh"),
                                 nn.Linear(96, 1))
        self.q = nn.Sequential(nn.Linear(184, 96), nn.GELU(approximate="tanh"),
                               nn.Linear(96, 1))
        self.vals = nn.ModuleList(
            [nn.Sequential(nn.Linear(128, 64), nn.GELU(approximate="tanh"),
                           nn.Linear(64, 1)) for _ in range(8)])

    def deck_encode(self, ids, ups, cfs):
        # ids (B,T) long, -1 = padding; attention over valid tokens only.
        B, T = ids.shape
        qmask = ids >= 0
        emb = torch.cat([self.E_card(ids.clamp(0, NCARD - 1)),
                         self.E_up(ups.clamp(0, 1)), cfs.unsqueeze(-1)], -1)  # (B,T,41)
        tok = self.deckTok(emb)                                              # (B,T,32)
        qkv = self.deckQkv(tok)
        q, k, v = qkv[..., :32], qkv[..., 32:64], qkv[..., 64:]
        sc = 1.0 / math.sqrt(32.0)
        scores = torch.bmm(q, k.transpose(1, 2)) * sc                          # C++ op order: dot*invSqrt
        masked = scores.masked_fill(~qmask.unsqueeze(1), float("-inf"))      # invalid keys
        smax = masked.amax(-1, keepdim=True)
        smax = torch.where(qmask.unsqueeze(-1), smax,
                           torch.zeros((), device=ids.device))               # invalid q rows -> -inf/0
        w = torch.exp(masked - smax)                                         # invalid rows -> 0
        w = w / w.sum(-1, keepdim=True).clamp_min(1e-30)                     # row-normalize like C++
        attn = torch.bmm(w, v)                                               # (B,T,32)
        out = self.deckLn(tok + self.deckProj(attn))
        n = qmask.sum(1).clamp_min(1).unsqueeze(1)
        return (out * qmask.unsqueeze(-1)).sum(1) / n                        # mean over valid

    def forward(self, x, dk_id, dk_up, dk_cf, rl_id, rl_df, pt_id, pt_cf,
                bits, cat, atype, screen, ent_type, ent_id, gold_ge, probes=None):
        z_deck = self.deck_encode(dk_id, dk_up, dk_cf) if self.rung >= 2 else None
        z_rel = z_pot = None
        if self.rung >= 3:
            rmask = rl_id >= 0
            remb = torch.cat([self.E_rel(rl_id.clamp(0, NREL - 1)), rl_df.unsqueeze(-1)], -1)
            rtok = self.relTok(remb)
            z_rel = (rtok * rmask.unsqueeze(-1).float()).sum(1) / rmask.sum(1).clamp_min(1).unsqueeze(1)
            pmask = pt_id >= 0
            pemb = torch.cat([self.E_pot(pt_id.clamp(0, NPOT - 1)), pt_cf.unsqueeze(-1)], -1)
            ptok = self.potTok(pemb)
            z_pot = (ptok * pmask.unsqueeze(-1).float()).sum(1) / pmask.sum(1).clamp_min(1).unsqueeze(1)
        zd = z_deck if z_deck is not None else torch.zeros(x.shape[0], 32, device=x.device)
        zr = z_rel if z_rel is not None else torch.zeros(x.shape[0], 16, device=x.device)
        zp = z_pot if z_pot is not None else torch.zeros(x.shape[0], 8, device=x.device)
        if self.nprobes > 0 and probes is not None:
            s = self.f(torch.cat([x, probes, zd, zr, zp], 1))                    # (B,128)
        else:
            s = self.f(torch.cat([x, zd, zr, zp], 1))                          # (B,128)

        b = self.a_bits(bits)                                                # (B,16)
        cat_in = torch.cat([self.cats[i](cat[:, i]) for i in range(6)] + [self.atype(atype)], 1)
        a = self.a_cat(cat_in)                                               # (B,16)
        ev = torch.zeros(x.shape[0], 32, device=x.device)
        m = ent_type == 1
        if m.any():
            ev[m] = self.E_card(ent_id[m].clamp(0, NCARD - 1))
        m = ent_type == 2
        if m.any():
            ev[m] = torch.cat([self.E_rel(ent_id[m].clamp(0, NREL - 1)),
                               torch.zeros(m.sum(), 16, device=x.device)], 1)
        m = ent_type == 3
        if m.any():
            ev[m] = torch.cat([self.E_pot(ent_id[m].clamp(0, NPOT - 1)),
                               torch.zeros(m.sum(), 24, device=x.device)], 1)
        eo = torch.eye(4, device=x.device)[ent_type]                         # [none,card,relic,potion]
        e = self.ent(torch.cat([ev, eo, gold_ge.unsqueeze(1)], 1))           # (B,16)
        if self.rung < 4:
            e = e * 0.0

        z = torch.cat([s, b, a, self.screen(screen), e], 1)                  # (B,184)
        logit = self.pol(z).squeeze(1)
        q = self.q(z).squeeze(1)
        v = torch.zeros(x.shape[0], device=x.device)
        for h in range(8):
            mm = (screen == h + 1)
            if mm.any():
                v[mm] = self.vals[h](s[mm]).squeeze(1)
        return logit, v, q
