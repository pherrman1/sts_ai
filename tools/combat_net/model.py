"""Combat net for the combat plan stage 2 (2026-11-08): a transformer over the encoder's tokens with a policy head
over the root's legal actions, a categorical value head over the fight's end HP (with death as its own class) and
two auxiliary HP-loss heads. Inputs are the arrays of tensorize.py, batched by `collate`."""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

CARD_V, MON_V, MOVE_V, POT_V, STAT_V, ZONE_V = 512, 256, 256, 64, 128, 16
VALUE_BINS = 20   # class 0 = death, classes 1..VALUE_BINS = end HP / max HP in equal bins


def slog(x):
    return torch.sign(x) * torch.log1p(torch.abs(x))


def value_class(won, end_frac):
    b = torch.clamp((end_frac * VALUE_BINS).long(), 0, VALUE_BINS - 1) + 1
    return torch.where(won > 0, b, torch.zeros_like(b))


class Arrays:
    """Memory-mapped tensorize.py output."""

    def __init__(self, d):
        import json
        import os
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.a = {}
        for f in os.listdir(d):
            if f.endswith(".npy"):
                self.a[f[:-4]] = np.load(os.path.join(d, f), mmap_mode="r")
        self.n = self.meta["rows"]


def collate(A, idx):
    """Padded torch tensors for rows `idx` of Arrays A."""
    a = A.a
    idx = np.sort(np.asarray(idx))
    B = len(idx)
    out = {k: torch.from_numpy(np.asarray(a[k][idx]).astype(np.float32 if a[k].dtype.kind == "f" else np.int64))
           for k in ("glob", "relics", "sbits", "smap", "mcat", "mnum", "nmon", "potions", "queues", "nqueue",
                     "chosen", "multi", "won", "endFrac", "hpLoss1", "hpLoss2", "act", "elite_boss")}
    co, ao = a["card_off"], a["act_off"]
    nc = (co[idx + 1] - co[idx]).astype(np.int64)
    na = (ao[idx + 1] - ao[idx]).astype(np.int64)
    C, E = max(1, int(nc.max())), max(1, int(na.max()))
    cards = np.zeros((B, C, 9), np.int64)
    acts = np.zeros((B, E, a["actions"].shape[1]), np.int64)
    pol = np.zeros((B, E), np.float32)
    for i, r in enumerate(idx):
        cards[i, :nc[i]] = a["cards"][co[r]:co[r + 1]]
        acts[i, :na[i]] = a["actions"][ao[r]:ao[r + 1]]
        pol[i, :na[i]] = a["policy"][ao[r]:ao[r + 1]]
    out["cards"] = torch.from_numpy(cards)
    out["card_mask"] = torch.arange(C)[None, :] < torch.from_numpy(nc)[:, None]
    out["actions"] = torch.from_numpy(acts)
    out["act_mask"] = torch.arange(E)[None, :] < torch.from_numpy(na)[:, None]
    out["policy"] = torch.from_numpy(pol)
    return out


class CombatNet(nn.Module):
    def __init__(self, d=128, layers=4, heads=4, g_len=97, m_num=128, q_len=24, a_len=37, aux=True, value=True):
        super().__init__()
        self.aux_on, self.value_on = aux, value
        self.card = nn.Embedding(CARD_V, d)
        self.zone = nn.Embedding(ZONE_V, d)
        self.card_num = nn.Linear(7, d)              # pos, upgraded, cost, costForTurn, free, retain, special
        self.mon = nn.Embedding(MON_V, d)
        self.mon_idx = nn.Embedding(8, d)
        self.move = nn.Embedding(MOVE_V, d)
        self.mon_num = nn.Linear(m_num, d)
        self.stat = nn.Embedding(STAT_V, d)
        self.stat_num = nn.Linear(1, d)
        self.queue = nn.Linear(q_len, d)
        self.glob = nn.Sequential(nn.Linear(g_len + 128 + 128, d), nn.GELU(), nn.Linear(d, d))
        self.pot = nn.Embedding(POT_V, d)
        self.tok_type = nn.Embedding(5, d)                # token types: global, card, monster, status, queue
        enc = nn.TransformerEncoderLayer(d, heads, 4 * d, dropout=0.0, batch_first=True, norm_first=True)
        self.trunk = nn.TransformerEncoder(enc, layers)
        self.norm = nn.LayerNorm(d)
        # actions
        self.a_type = nn.Embedding(8, d)
        self.a_card = nn.Embedding(CARD_V, d)
        self.a_pot = nn.Embedding(POT_V, d)
        self.a_target = nn.Embedding(8, d)
        self.a_num = nn.Linear(a_len, d)
        self.a_sel = nn.Embedding(CARD_V, d)
        self.pol = nn.Sequential(nn.Linear(3 * d, d), nn.GELU(), nn.Linear(d, 1))
        self.val = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, VALUE_BINS + 1))
        self.auxh = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, 2))

    def forward(self, b):
        B = b["glob"].shape[0]
        g = self.glob(torch.cat([slog(b["glob"]), b["relics"].float(), b["sbits"].float()], -1))
        g = g + self.pot(b["potions"].clamp(0, POT_V - 1)).sum(1) + self.tok_type.weight[0]
        c = b["cards"]
        ct = (self.card(c[..., 2].clamp(0, CARD_V - 1)) + self.zone(c[..., 0].clamp(0, ZONE_V - 1))
              + self.card_num(slog(c[..., [1, 3, 4, 5, 6, 7, 8]].float())) + self.tok_type.weight[1])
        m = b["mcat"]
        mt = (self.mon(m[..., 1].clamp(0, MON_V - 1)) + self.mon_idx(m[..., 0].clamp(0, 7))
              + self.move(m[..., 2].clamp(0, MOVE_V - 1)) + 0.5 * self.move(m[..., 3].clamp(0, MOVE_V - 1))
              + self.mon_num(b["mnum"]) + self.tok_type.weight[2])
        M = m.shape[1]
        m_mask = torch.arange(M)[None, :] < b["nmon"][:, None]
        s = b["smap"]
        st = self.stat(s[..., 0].clamp(0, STAT_V - 1)) + self.stat_num(slog(s[..., 1:2].float())) + self.tok_type.weight[3]
        s_mask = s[..., 0] > 0
        q = b["queues"]
        qt = self.queue(slog(q.float())) + self.tok_type.weight[4]
        q_mask = torch.arange(q.shape[1])[None, :] < b["nqueue"][:, None]
        x = torch.cat([g[:, None], ct, mt, st, qt], 1)
        mask = torch.cat([torch.ones(B, 1, dtype=torch.bool), b["card_mask"], m_mask, s_mask, q_mask], 1)
        h = self.norm(self.trunk(x, src_key_padding_mask=~mask))
        cls = h[:, 0]
        mon_h = h[:, 1 + ct.shape[1]:1 + ct.shape[1] + M]
        # actions: t, s, c[8], o, p[2], x, d, k, task, sel[10][id, specialData, upgraded]
        a = b["actions"]
        sel_ids = a[..., 17::3].clamp(0, CARD_V - 1)
        at = (self.a_type(a[..., 0].clamp(0, 7)) + self.a_card(a[..., 2].clamp(0, CARD_V - 1))
              + self.a_pot(a[..., 11].clamp(0, POT_V - 1)) + self.a_target((a[..., 13] + 1).clamp(0, 7))
              + self.a_num(slog(a.float())) + (self.a_sel(sel_ids) * (sel_ids > 0)[..., None]).sum(2))
        tgt = a[..., 13].clamp(0, M - 1)
        tgt_h = torch.gather(mon_h, 1, tgt[..., None].expand(-1, -1, mon_h.shape[-1]))
        tgt_h = tgt_h * (a[..., 13] >= 0)[..., None]
        E = a.shape[1]
        logits = self.pol(torch.cat([cls[:, None].expand(-1, E, -1), at, tgt_h], -1)).squeeze(-1)
        logits = logits.masked_fill(~b["act_mask"], -1e9)
        return logits, self.val(cls), self.auxh(cls)


def losses(net, b, logits, vlog, aux):
    multi = b["multi"].float()
    logp = F.log_softmax(logits, -1)
    pol_ce = -(b["policy"] * logp.masked_fill(~b["act_mask"], 0)).sum(-1)
    pol_loss = (pol_ce * multi).sum() / multi.sum().clamp(min=1)
    vc = value_class(b["won"], b["endFrac"])
    val_loss = F.cross_entropy(vlog, vc)
    aux_t = torch.stack([b["hpLoss1"], b["hpLoss2"]], -1) / 10.0
    aux_loss = F.smooth_l1_loss(aux, aux_t)
    total = pol_loss + (val_loss if net.value_on else 0) + (aux_loss if net.aux_on else 0)
    return total, {"policy_ce": pol_loss.item(), "value_nll": val_loss.item(), "aux": aux_loss.item()}
