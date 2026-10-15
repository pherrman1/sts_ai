#!/usr/bin/env python3
"""Shared V4 token-state net architecture for the OOC strategic model.

Used by `train_strategic_tok.py` (training) and `export_strategic_tok.py`
(native export + parity). Contract: docs/knowledge-base/architecture/ooc-strategic-v4.md.
`forward` takes a NORMALIZED 42-glob block (36 raw scalars minus 8
hidden-information leaks + 6 derived thresholds); the caller applies the
checkpoint's mean/inv and the [-8,8] clamp exactly like the native C++ entry
points.
"""
import math

import torch
from torch import nn

NCARD, NREL, NPOT = 372, 181, 48
MAXD, MAXR, MAXP = 96, 64, 8
NGLOB = 42   # 36 legit raw scalars + 6 derived thresholds (8 leaks removed)
NRAW = 36


class Net(nn.Module):
    """V4 token-state net: 50 globals + counted deck/relic/potion tokens, fusion
    MLP, and the V3 head contract (policy, per-screen value, Q). Deck tokens go
    through a 1-layer single-head attention by default; with `transformer=True`
    through a 2-layer transformer at dim 32 (2 heads, FFN 64, LayerNorm eps
    1e-5, GELU tanh, residuals) over the valid tokens only, same masking /
    row-normalization / mean-pooling convention. Rung 1..4 zeroes inactive
    groups (see contract)."""

    def __init__(self, rung=4, nprobes=0, transformer=False, nquants=0, ncross=0):
        super().__init__()
        self.rung = rung
        self.nprobes = nprobes
        self.nquants = nquants
        self.ncross = ncross
        self.transformer = transformer
        self.f = nn.Sequential(nn.Linear(98 + nprobes * 6, 256), nn.LayerNorm(256, eps=1e-5),
                               nn.GELU(approximate="tanh"), nn.Dropout(0.2),
                               nn.Linear(256, 128), nn.GELU(approximate="tanh"))
        self.E_card = nn.Embedding(NCARD, 32)
        self.E_up = nn.Embedding(2, 8)
        self.deckTok = nn.Sequential(nn.Linear(41, 32), nn.GELU(approximate="tanh"))
        self.deckQkv = nn.Linear(32, 96)
        self.deckProj = nn.Linear(32, 32)
        self.deckLn = nn.LayerNorm(32, eps=1e-5)
        if transformer:
            self.deckTr = nn.ModuleList([
                nn.ModuleDict({
                    "qkv": nn.Linear(32, 96),
                    "proj": nn.Linear(32, 32),
                    "ln": nn.LayerNorm(32, eps=1e-5),
                    "ffn": nn.Sequential(nn.Linear(32, 64), nn.GELU(approximate="tanh"),
                                         nn.Linear(64, 32)),
                    "ffnln": nn.LayerNorm(32, eps=1e-5),
                }) for _ in range(2)
            ])
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
        self.ent = nn.Sequential(nn.Linear(37 + 32 * ncross, 32), nn.GELU(approximate="tanh"),
                                 nn.Linear(32, 16))
        self.pol = nn.Sequential(nn.Linear(184, 96), nn.GELU(approximate="tanh"),
                                 nn.Linear(96, 1))
        self.q = nn.Sequential(nn.Linear(184, 96), nn.GELU(approximate="tanh"),
                               nn.Linear(96, 1))
        self.vals = nn.ModuleList(
            [nn.Sequential(nn.Linear(128, 64), nn.GELU(approximate="tanh"),
                           nn.Linear(64, 1)) for _ in range(8)])
        self.quants = nn.ModuleList(
            [nn.Sequential(nn.Linear(128, 64), nn.GELU(approximate="tanh"),
                           nn.Linear(64, 11)) for _ in range(8)])
        self.qtau = nn.Parameter(torch.linspace(0.05, 0.95, 11), requires_grad=False)


    def _deck_attn(self, qkv, proj, ln, tok, qmask, device):
        # Masked self-attention (valid tokens only), same row-normalization
        # convention for 1 head (default) and 2 heads (transformer): scores
        # scaled by 1/sqrt(32), row max subtraction, exp, row-normalize.
        B, T, D = tok.shape
        x = qkv(tok)
        q, k, v = x[..., :32], x[..., 32:64], x[..., 64:]
        sc = 1.0 / math.sqrt(32.0)
        if self.transformer:
            q = q.view(B, T, 2, 16).transpose(1, 2)
            k = k.view(B, T, 2, 16).transpose(1, 2)
            v = v.view(B, T, 2, 16).transpose(1, 2)
            scores = torch.matmul(q, k.transpose(-1, -2)) * sc              # (B,2,T,T)
            masked = scores.masked_fill(~qmask.unsqueeze(1).unsqueeze(1), float("-inf"))
            smax = masked.amax(-1, keepdim=True)
            smax = torch.where(qmask.unsqueeze(1).unsqueeze(-1), smax,
                               torch.zeros((), device=device))
            w = torch.exp(masked - smax)
            w = w / w.sum(-1, keepdim=True).clamp_min(1e-30)
            attn = torch.matmul(w, v).transpose(1, 2).reshape(B, T, D)
        else:
            scores = torch.bmm(q, k.transpose(1, 2)) * sc                   # C++ op order: dot*invSqrt
            masked = scores.masked_fill(~qmask.unsqueeze(1), float("-inf"))  # invalid keys
            smax = masked.amax(-1, keepdim=True)
            smax = torch.where(qmask.unsqueeze(-1), smax,
                               torch.zeros((), device=device))              # invalid q rows -> 0
            w = torch.exp(masked - smax)                                     # invalid rows -> 0
            w = w / w.sum(-1, keepdim=True).clamp_min(1e-30)                 # row-normalize like C++
            attn = torch.bmm(w, v)                                           # (B,T,32)
        return ln(tok + proj(attn))                                          # residual + LayerNorm

    def deck_tokens(self, ids, ups, cfs):
        # ids (B,T) long, -1 = padding; counted-token embeddings (B,T,32).
        emb = torch.cat([self.E_card(ids.clamp(0, NCARD - 1)),
                         self.E_up(ups.clamp(0, 1)), cfs.unsqueeze(-1)], -1)  # (B,T,41)
        return self.deckTok(emb)

    def deck_encode(self, ids, ups, cfs):
        # ids (B,T) long, -1 = padding; attention over valid tokens only.
        B, T = ids.shape
        qmask = ids >= 0
        tok = self.deck_tokens(ids, ups, cfs)                                # (B,T,32)
        if self.transformer:
            for l in self.deckTr:
                tok = self._deck_attn(l["qkv"], l["proj"], l["ln"], tok, qmask, ids.device)
                tok = l["ffnln"](tok + l["ffn"](tok))                        # FFN + residual + LayerNorm
        else:
            tok = self._deck_attn(self.deckQkv, self.deckProj, self.deckLn,
                                  tok, qmask, ids.device)
        n = qmask.sum(1).clamp_min(1).unsqueeze(1)
        return (tok * qmask.unsqueeze(-1)).sum(1) / n                        # mean over valid

    def forward(self, x, dk_id, dk_up, dk_cf, rl_id, rl_df, pt_id, pt_cf,
                bits, cat, atype, screen, ent_type, ent_id, gold_ge, probes=None):
        dk_tok = self.deck_tokens(dk_id, dk_up, dk_cf) if (self.rung >= 2 and self.ncross > 0) else None
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
        if self.ncross > 0 and dk_tok is not None:
            # candidate-deck cross-attention: card candidates attend over the
            # counted deck tokens (single head, valid tokens only).
            m = (ent_type == 1)
            cv = torch.zeros(x.shape[0], 32, device=x.device)
            if m.any():
                q = ev[m].unsqueeze(1)                                       # (M,1,32)
                k = dk_tok[m]                                                # (M,T,32)
                kmask = (dk_id[m] >= 0)
                sc = torch.bmm(q, k.transpose(1, 2)) * (1.0 / math.sqrt(32.0))
                sc = sc.masked_fill(~kmask.unsqueeze(1), float("-inf"))
                smax = torch.where(kmask.unsqueeze(1), sc.amax(-1, keepdim=True),
                                   torch.zeros((), device=x.device))
                w = torch.exp(sc - smax)
                w = w / w.sum(-1, keepdim=True).clamp_min(1e-30)
                cv[m] = torch.bmm(w, k).squeeze(1)
            ent_in = torch.cat([ev, eo, gold_ge.unsqueeze(1), cv], 1)        # (B,69)
        else:
            ent_in = torch.cat([ev, eo, gold_ge.unsqueeze(1)], 1)            # (B,37)
        e = self.ent(ent_in)                                                 # (B,16)
        if self.rung < 4:
            e = e * 0.0

        z = torch.cat([s, b, a, self.screen(screen), e], 1)                  # (B,184)
        logit = self.pol(z).squeeze(1)
        q = self.q(z).squeeze(1)
        # All 8 per-screen heads on the full batch, then select by screen
        # (identical math to the old masked per-head writes; no index_put /
        # tiny masked GEMMs / host syncs).
        si = (screen - 1).clamp(0, 7)
        vv = torch.stack([self.vals[h](s) for h in range(8)], 1)             # (B,8,1)
        v = vv[torch.arange(x.shape[0], device=x.device), si].squeeze(1)
        qq = None
        if self.nquants > 0:
            qqv = torch.stack([self.quants[h](s) for h in range(8)], 1)      # (B,8,11)
            qq = qqv[torch.arange(x.shape[0], device=x.device), si]
        return logit, v, q, qq
