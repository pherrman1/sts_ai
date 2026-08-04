#!/usr/bin/env python3
"""Streaming CombatPolicyValueNet training — no full dataset preload.

Reads fairgen CSVs in chunks, groups policy rows within each chunk,
trains with alternating value/policy loss on a shared encoder.

Usage:
  train_combat_pvnet.py VAL_CSV POL_CSV [OUT]
"""
import os, sys, gc, math, time
import numpy as np, pandas as pd
import torch
from torch import nn

VAL_CSV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fair_final_v.csv"
POL_CSV = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fair_final_p.csv"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_pvnet.txt"

# ── Hyperparameters ──────────────────────────────────────────────────────────
EPOCHS = int(os.environ.get("PVNET_EPOCHS", "10"))
BATCH = int(os.environ.get("PVNET_BATCH", "512"))
CHUNK = int(os.environ.get("PVNET_CHUNK_ROWS", "50000"))
DEVICE = os.environ.get("PVNET_DEVICE", "cuda")
DIM = int(os.environ.get("PVNET_ENTITY_DIM", "128"))
HIDDEN = int(os.environ.get("PVNET_HIDDEN_DIM", "256"))
HEADS = int(os.environ.get("PVNET_NUM_HEADS", "4"))
LAYERS = int(os.environ.get("PVNET_NUM_LAYERS", "2"))
NQ = int(os.environ.get("PVNET_NQUANTILE", "11"))
LR = float(os.environ.get("PVNET_LR", "1e-4"))
WD = float(os.environ.get("PVNET_WD", "1e-5"))
L_POL = float(os.environ.get("PVNET_L_POLICY", "1.0"))
L_WIN = float(os.environ.get("PVNET_L_WIN", "1.0"))
L_QUANT = float(os.environ.get("PVNET_L_QUANTILE", "0.5"))
WIN_BONUS = float(os.environ.get("PVNET_WIN_BONUS", "50"))

LAMBDA = {"policy": L_POL, "win": L_WIN, "quantile": L_QUANT,
          "potion": 0.2, "turns": 0.1, "death": 1.0}

# Seed-grouped validation split: deterministic rule, no overlap with train rows.
# A group (seed, fightIdx, decIdx) is entirely train or val because the seed is
# constant within a group.
VAL_FRAC = float(os.environ.get("PVNET_VAL_FRAC", "0.2"))
TRAIN_ONLY = os.environ.get("PVNET_TRAIN_ONLY", "0") == "1"

def is_val_seed(seed):
    return int(seed) % 100 < int(VAL_FRAC * 100)

if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)} "
          f"VRAM={torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB", flush=True)
else:
    DEVICE = "cpu"
torch.manual_seed(0)
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "8")))


# ── CSV schema ───────────────────────────────────────────────────────────────
val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
canonical = [c for c in val_header if c not in ("seed", "fightIdx", "won", "endHp")]
assert len(canonical) == 1766

pol_header = list(pd.read_csv(POL_CSV, nrows=0).columns)
POL_META = ("seed", "fightIdx", "decIdx", "visit", "total")
action_names = [c for c in pol_header if c not in canonical and c not in POL_META]
assert len(action_names) == 14

# Entity decomposition
zones = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
relic_cols = [f"r{i}" for i in range(128)]
potion_cols = [f"pot{i}" for i in range(44)]
mon_cols = [[f"m{i}{s}" for s in ("Id", "Hp", "Block", "Str", "Intent", "Atk", "Vuln", "Weak", "Poison")]
            for i in range(5)]
mon_flat = [c for row in mon_cols for c in row]
entity_set = set(relic_cols + potion_cols + mon_flat + ["encounter"] +
                 [c for z in zones for c in z])
scalar_cols = [c for c in canonical if c not in entity_set]
assert len(scalar_cols) == 64


# ── Data extraction ──────────────────────────────────────────────────────────
def extract_state(df):
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


def to_tensors(*arrs, device=DEVICE):
    return tuple(torch.from_numpy(np.ascontiguousarray(a)).to(device) for a in arrs)


# ── Normalization pass (value CSV) ──────────────────────────────────────────
print("[norm] scanning value CSV...", flush=True)
scalar_sum = np.zeros(64, np.float64)
scalar_sq = np.zeros(64, np.float64)
mon_sum = np.zeros(7, np.float64)
mon_sq = np.zeros(7, np.float64)
n_total = 0; n_mon = 0
for df in pd.read_csv(VAL_CSV, chunksize=CHUNK):
    s, c, r, p, e, mi, it, mc, mm = extract_state(df)
    scalar_sum += s.sum(axis=0)
    scalar_sq += (s.astype(np.float64) ** 2).sum(axis=0)
    n_total += len(df)
    for i in range(5):
        mask = mm[:, i]
        if mask.any():
            mon_sum += mc[mask, i, :].sum(axis=0)
            mon_sq += (mc[mask, i, :].astype(np.float64) ** 2).sum(axis=0)
            n_mon += mask.sum()
scalar_mean = (scalar_sum / n_total).astype(np.float32)
scalar_std = np.sqrt(scalar_sq / n_total - scalar_mean ** 2).astype(np.float32) + 1e-6
mon_mean = (mon_sum / max(n_mon, 1)).astype(np.float32)
mon_std = np.sqrt(mon_sq / max(n_mon, 1) - mon_mean ** 2).astype(np.float32) + 1e-6
print(f"[norm] {n_total:,} rows, {n_mon:,} monster tokens", flush=True)


# ── Model ────────────────────────────────────────────────────────────────────
class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden, heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, hidden), nn.GELU(), nn.Linear(hidden, dim))
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        a, _ = self.attn(x, x, x)
        x = self.ln1(x + a)
        x = self.ln2(x + self.ffn(x))
        return x


class SharedEncoder(nn.Module):
    def __init__(self, dim=DIM, hidden=HIDDEN, heads=HEADS, layers=LAYERS):
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
        self.layers = nn.ModuleList([TransformerLayer(dim, hidden, heads) for _ in range(layers)])
        self.register_buffer("scalar_mean", torch.zeros(64))
        self.register_buffer("scalar_inv", torch.ones(64))
        self.register_buffer("mon_mean", torch.zeros(7))
        self.register_buffer("mon_inv", torch.ones(7))

    def build_tokens(self, scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask):
        B = scalar.shape[0]
        tokens = []
        # 0: scalar
        s = (scalar - self.scalar_mean) * self.scalar_inv
        tokens.append((self.scalar_enc(s) + self.type_embed[0]).unsqueeze(1))
        # 1: card zones
        for z in range(4):
            t = torch.einsum("bc,ce->be", cards[:, z, :].float(), self.card_embed)
            tokens.append((t + self.zone_pos[z] + self.type_embed[1]).unsqueeze(1))
        # 2: relic
        t = torch.einsum("br,re->be", relics.float(), self.relic_embed)
        if 64 != self.dim: t = self.relic_proj(t)
        tokens.append((t + self.type_embed[2]).unsqueeze(1))
        # 3: potion
        t = torch.einsum("bp,pe->be", potions.float(), self.potion_embed)
        if 32 != self.dim: t = self.potion_proj(t)
        tokens.append((t + self.type_embed[3]).unsqueeze(1))
        # 4: encounter
        t = self.enc_embed(encounter.long())
        if 32 != self.dim: t = self.enc_proj(t)
        tokens.append((t + self.type_embed[4]).unsqueeze(1))
        # 5: monsters
        for s in range(5):
            alive = mmask[:, s]
            if not alive.any(): continue
            me = self.mon_id(mids[:, s].long().clamp(0, 255))
            ie = self.mon_intent(intents[:, s].long().clamp(0, 31))
            mc = (mcont[:, s, :] - self.mon_mean) * self.mon_inv
            t = self.mon_enc(torch.cat([me, ie, mc], dim=-1)) + self.type_embed[5]
            tokens.append((t * alive.float().unsqueeze(-1)).unsqueeze(1))
        x = torch.cat([self.global_token.expand(B, -1, -1)] + tokens, dim=1)
        return x

    def forward(self, scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask):
        x = self.build_tokens(scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask)
        for layer in self.layers:
            x = layer(x)
        return x[:, 0, :]  # GLOBAL token


class PolicyHead(nn.Module):
    def __init__(self, dim=DIM):
        super().__init__()
        self.act_enc = nn.Sequential(nn.Linear(14, 64), nn.ReLU(), nn.Linear(64, dim), nn.ReLU())
        self.scorer = nn.Sequential(nn.Linear(dim * 3, dim), nn.ReLU(), nn.Linear(dim, 1))

    def forward(self, z_global, action_feats):
        """z_global: (B, dim), action_feats: (B, 14). Returns (B,) logits."""
        ea = self.act_enc(action_feats)
        ctx = torch.cat([z_global, ea, z_global * ea], dim=-1)
        return self.scorer(ctx).squeeze(-1)


class PolicyValueNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = SharedEncoder()
        self.policy = PolicyHead()
        self.win = nn.Linear(DIM, 1)
        self.death = nn.Linear(DIM, 1)
        self.quantile = nn.Linear(DIM, NQ)
        self.potion = nn.Linear(DIM, 44)
        self.turns = nn.Linear(DIM, 1)


# ── Losses ───────────────────────────────────────────────────────────────────
def policy_ce(logits, visit_counts, total):
    """Cross-entropy against visit distribution. logits: (N_actions,), visits: (N_actions,)"""
    logits = logits - logits.max()
    lp = logits - torch.logsumexp(logits, dim=0)
    target = visit_counts.float() / (float(total) + 1e-8)
    return -(target * lp).sum()


def value_losses(preds, y_won, y_hp, max_hp):
    ld = nn.functional.binary_cross_entropy_with_logits(preds["death"], (y_won <= 0).float())
    lw = nn.functional.binary_cross_entropy_with_logits(preds["win"], y_won)
    won = y_won > 0.5
    if won.any():
        frac = y_hp[won] / (max_hp[won] + 1e-6)
        qp = preds["quantile"][won]
        tau = torch.linspace(0.05, 0.95, NQ, device=DEVICE).view(1, -1)
        d = frac.unsqueeze(-1) - qp
        lq = (tau * d.clamp(min=0) + (1 - tau) * (-d).clamp(min=0)).mean()
    else:
        lq = torch.tensor(0.0, device=DEVICE)
    lp = 0.01 * preds["potion"].abs().mean()
    lt = torch.tensor(0.0, device=DEVICE)
    return {"death": ld, "win": lw, "quantile": lq, "potion": lp, "turns": lt}


# ── Validation pass (held-out seeds) ────────────────────────────────────────
def validation_pass(model):
    """Stream both CSVs, keep only val-seed rows/groups, return weighted loss."""
    model.eval()
    total_v = 0.0; total_p = 0.0; total_n = 0
    with torch.no_grad():
        v_reader = pd.read_csv(VAL_CSV, chunksize=CHUNK)
        for df in v_reader:
            m = df["seed"].map(is_val_seed).to_numpy(np.bool_)
            if not m.any(): continue
            sdf = df[m]
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(sdf)
            y_won = sdf["won"].to_numpy(np.float32)
            y_hp = sdf["endHp"].to_numpy(np.float32)
            max_hp = sdf["maxHp"].to_numpy(np.float32)
            for b in range(0, len(sdf), BATCH):
                e = min(b + BATCH, len(sdf))
                s, ca, r, po, en, mi, it, mc, mm = to_tensors(
                    scalar[b:e], cards[b:e], relics[b:e], potions[b:e],
                    enc[b:e], mids[b:e], intents[b:e], mcont[b:e], mmask[b:e])
                yw, yh, mh = to_tensors(y_won[b:e], y_hp[b:e], max_hp[b:e])
                z = model.encoder(s, ca, r, po, en, mi, it, mc, mm)
                out = {
                    "death": model.death(z).squeeze(-1),
                    "win": model.win(z).squeeze(-1),
                    "quantile": model.quantile(z),
                    "potion": model.potion(z),
                    "turns": model.turns(z).squeeze(-1),
                }
                vlosses = value_losses(out, yw, yh, mh)
                loss = sum(LAMBDA[k] * vlosses[k] for k in vlosses)
                total_v += loss.item() * (e - b)
                total_n += e - b

        p_reader = pd.read_csv(POL_CSV, chunksize=CHUNK)
        for df in p_reader:
            if len(df) < 2: continue
            seeds = df["seed"].to_numpy(np.int64)
            fights = df["fightIdx"].to_numpy(np.int32)
            decs = df["decIdx"].to_numpy(np.int32)
            changes = (seeds[1:] != seeds[:-1]) | (fights[1:] != fights[:-1]) | (decs[1:] != decs[:-1])
            boundaries = np.where(changes)[0] + 1
            g_starts = np.concatenate([[0], boundaries])
            g_ends = np.concatenate([boundaries, [len(df)]])
            valid = (g_ends - g_starts) >= 2
            g_starts = g_starts[valid]
            g_ends = g_ends[valid]
            valmask = np.array([is_val_seed(s) for s in seeds])
            keep = valmask[g_starts]
            g_starts = g_starts[keep]
            g_ends = g_ends[keep]
            if len(g_starts) == 0: continue
            state_arr = df[canonical].to_numpy(np.float32)
            action_arr = df[action_names].to_numpy(np.float32)
            visit_arr = df["visit"].to_numpy(np.int32)
            total_arr = df["total"].to_numpy(np.int32)
            batch_states = state_arr[g_starts]
            df_batch = pd.DataFrame(batch_states, columns=canonical)
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(df_batch)
            s_t, ca_t, r_t, po_t, en_t, mi_t, it_t, mc_t, mm_t = to_tensors(
                scalar, cards, relics, potions, enc, mids, intents, mcont, mmask)
            z_all = model.encoder(s_t, ca_t, r_t, po_t, en_t, mi_t, it_t, mc_t, mm_t)
            for gi in range(len(g_starts)):
                gs, ge = g_starts[gi], g_ends[gi]
                n_act = ge - gs
                if n_act < 2: continue
                tot = int(total_arr[gs])
                if tot <= 0: continue
                z_i = z_all[gi:gi+1].expand(n_act, -1)
                act_t = torch.from_numpy(np.ascontiguousarray(action_arr[gs:ge])).to(DEVICE)
                vis_t = torch.from_numpy(visit_arr[gs:ge].astype(np.float32).copy()).to(DEVICE)
                logits = model.policy(z_i, act_t)
                ce = policy_ce(logits, vis_t, torch.tensor(float(tot), device=DEVICE))
                total_p += ce.item() * n_act
                total_n += n_act
    model.train()
    return (total_v + total_p) / max(total_n, 1)


# ── Training ─────────────────────────────────────────────────────────────────
def main():
    model = PolicyValueNet().to(DEVICE)
    model.encoder.scalar_mean.data = torch.from_numpy(scalar_mean).to(DEVICE)
    model.encoder.scalar_inv.data = torch.from_numpy(1.0 / scalar_std).to(DEVICE)
    model.encoder.mon_mean.data = torch.from_numpy(mon_mean).to(DEVICE)
    model.encoder.mon_inv.data = torch.from_numpy(1.0 / mon_std).to(DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[model] {n_params:,} params", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    best_loss = float("inf")
    t_start = time.time()

    # ── Pre-scan policy CSV for decision group indices within each chunk ──
    # We'll process policy by reading chunks and grouping with pandas groupby.
    # Groups that cross chunk boundaries are skipped (safe — they're rare).

    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0.0; total_v = 0.0; total_p = 0.0; total_n = 0
        print(f"\n[epoch {epoch+1}/{EPOCHS}]", flush=True)

        # ── Value pass ──
        v_reader = pd.read_csv(VAL_CSV, chunksize=CHUNK)
        for df in v_reader:
            if TRAIN_ONLY:
                m = ~df["seed"].map(is_val_seed).to_numpy(np.bool_)
                df = df[m]
                if len(df) == 0: continue
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(df)
            y_won = df["won"].to_numpy(np.float32)
            y_hp = df["endHp"].to_numpy(np.float32)
            max_hp = df["maxHp"].to_numpy(np.float32)

            for b in range(0, len(df), BATCH):
                e = min(b + BATCH, len(df))
                n = e - b
                s, ca, r, po, en, mi, it, mc, mm = to_tensors(
                    scalar[b:e], cards[b:e], relics[b:e], potions[b:e],
                    enc[b:e], mids[b:e], intents[b:e], mcont[b:e], mmask[b:e])
                yw, yh, mh = to_tensors(y_won[b:e], y_hp[b:e], max_hp[b:e])

                z = model.encoder(s, ca, r, po, en, mi, it, mc, mm)
                out = {
                    "death": model.death(z).squeeze(-1),
                    "win": model.win(z).squeeze(-1),
                    "quantile": model.quantile(z),
                    "potion": model.potion(z),
                    "turns": model.turns(z).squeeze(-1),
                }
                vlosses = value_losses(out, yw, yh, mh)
                loss = sum(LAMBDA[k] * vlosses[k] for k in vlosses)

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                total_v += loss.item() * n
                total_n += n

        # ── Policy pass (streaming, no-allocation grouping) ──
        p_reader = pd.read_csv(POL_CSV, chunksize=CHUNK)
        for df in p_reader:
            if len(df) < 2: continue
            # Use numpy for fast group detection (contiguous rows)
            seeds = df["seed"].to_numpy(np.int64)
            fights = df["fightIdx"].to_numpy(np.int32)
            decs = df["decIdx"].to_numpy(np.int32)

            # Find group boundaries within this chunk
            changes = (seeds[1:] != seeds[:-1]) | (fights[1:] != fights[:-1]) | (decs[1:] != decs[:-1])
            boundaries = np.where(changes)[0] + 1
            g_starts = np.concatenate([[0], boundaries])
            g_ends = np.concatenate([boundaries, [len(df)]])

            # Filter to valid groups (skip singles, skip cross-chunk groups marked by flag)
            valid = (g_ends - g_starts) >= 2
            g_starts = g_starts[valid]
            g_ends = g_ends[valid]
            if TRAIN_ONLY:
                valmask = np.array([is_val_seed(s) for s in df["seed"].to_numpy(np.int64)])
                keep = ~valmask[g_starts]
                g_starts = g_starts[keep]
                g_ends = g_ends[keep]
            if len(g_starts) == 0:
                continue

            # Extract state features as numpy for all group-start rows
            state_arr = df[canonical].to_numpy(np.float32)
            action_arr = df[action_names].to_numpy(np.float32)
            visit_arr = df["visit"].to_numpy(np.int32)
            total_arr = df["total"].to_numpy(np.int32)

            # Batch state extraction
            batch_states = state_arr[g_starts]  # (N_groups, 1766)
            n_g = len(g_starts)

            # Build DataFrame for state extraction (fastest way to get entity tensors)
            df_batch = pd.DataFrame(batch_states, columns=canonical)
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(df_batch)
            s_t, ca_t, r_t, po_t, en_t, mi_t, it_t, mc_t, mm_t = to_tensors(
                scalar, cards, relics, potions, enc, mids, intents, mcont, mmask)
            z_all = model.encoder(s_t, ca_t, r_t, po_t, en_t, mi_t, it_t, mc_t, mm_t)

            # Compute policy loss
            p_loss = torch.tensor(0.0, device=DEVICE)
            p_n = 0
            for gi in range(n_g):
                gs, ge = g_starts[gi], g_ends[gi]
                n_act = ge - gs
                if n_act < 2: continue
                tot = int(total_arr[gs])
                if tot <= 0: continue

                z_i = z_all[gi:gi+1].expand(n_act, -1)
                act_t = torch.from_numpy(np.ascontiguousarray(action_arr[gs:ge])).to(DEVICE)
                vis_t = torch.from_numpy(visit_arr[gs:ge].astype(np.float32).copy()).to(DEVICE)

                logits = model.policy(z_i, act_t)
                p_loss = p_loss + policy_ce(logits, vis_t,
                    torch.tensor(float(tot), device=DEVICE))
                p_n += 1

            if p_n > 0:
                p_loss = p_loss / p_n
                optimizer.zero_grad()
                (LAMBDA["policy"] * p_loss).backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total_p += p_loss.item() * p_n
                total_n += p_n

        avg_loss = (total_v + total_p) / max(total_n, 1)
        val_loss = validation_pass(model)
        elapsed = time.time() - t_start
        print(f"  loss={avg_loss:.4f}  v={total_v/max(total_n,1):.4f}  "
              f"p={total_p/max(total_n,1):.4f}  val={val_loss:.4f}  {elapsed:.0f}s", flush=True)

        if val_loss < best_loss or epoch == 0:
            best_loss = val_loss
            export_model(model, OUT)

    print(f"\n[done] best_val={best_loss:.4f} → {OUT}  ({time.time()-t_start:.0f}s)", flush=True)


# ── Export ───────────────────────────────────────────────────────────────────
def export_model(model, path):
    st = model.state_dict()
    enc = model.encoder
    with open(path, "w") as f:
        f.write(f"combat_pvnet_v1\nentity_dim {DIM}\nhidden_dim {HIDDEN}\n"
                f"num_heads {HEADS}\nnum_layers {LAYERS}\n"
                f"nquantile {NQ}\nwin_bonus {WIN_BONUS}\n")

        si = [canonical.index(c) for c in scalar_cols]
        f.write(f"nscalar {len(si)}\n")
        for i in si: f.write(f" {i}")
        f.write("\n")

        def wv(name, arr):
            a = arr.detach().cpu().numpy().ravel()
            f.write(f"{name}")
            for v in a: f.write(f" {v:.6g}")
            f.write("\n")

        wv("scalar_mean", enc.scalar_mean); wv("scalar_inv", enc.scalar_inv)
        wv("mon_cont_mean", enc.mon_mean); wv("mon_cont_inv", enc.mon_inv)
        wv("scalar_weight", st["encoder.scalar_enc.0.weight"])
        wv("scalar_bias", st["encoder.scalar_enc.0.bias"])
        wv("card_embed", enc.card_embed); wv("zone_pos", enc.zone_pos)
        wv("type_embed", enc.type_embed); wv("global_token", enc.global_token)
        wv("relic_embed", enc.relic_embed)
        wv("potion_embed", enc.potion_embed)
        wv("encounter_embed", enc.enc_embed.weight)
        wv("mon_id_embed", enc.mon_id.weight)
        wv("mon_intent_embed", enc.mon_intent.weight)
        wv("mon_enc_weight", st["encoder.mon_enc.0.weight"])
        wv("mon_enc_bias", st["encoder.mon_enc.0.bias"])
        if hasattr(enc.relic_proj, "weight"):
            wv("relic_proj_weight", st["encoder.relic_proj.weight"])
            wv("relic_proj_bias", st["encoder.relic_proj.bias"])
        if hasattr(enc.potion_proj, "weight"):
            wv("potion_proj_weight", st["encoder.potion_proj.weight"])
            wv("potion_proj_bias", st["encoder.potion_proj.bias"])
        if hasattr(enc.enc_proj, "weight"):
            wv("enc_proj_weight", st["encoder.enc_proj.weight"])
            wv("enc_proj_bias", st["encoder.enc_proj.bias"])

        for l, layer in enumerate(enc.layers):
            p = f"encoder.layers.{l}."
            wv(f"layer_{l}_qkv_weight", st[p + "attn.in_proj_weight"])
            wv(f"layer_{l}_qkv_bias", st[p + "attn.in_proj_bias"])
            wv(f"layer_{l}_proj_weight", st[p + "attn.out_proj.weight"])
            wv(f"layer_{l}_proj_bias", st[p + "attn.out_proj.bias"])
            for ln in ("ln1", "ln2"):
                wv(f"layer_{l}_{ln}_weight", st[p + f"{ln}.weight"])
                wv(f"layer_{l}_{ln}_bias", st[p + f"{ln}.bias"])
            for part in ("0", "2"):
                wv(f"layer_{l}_ffn{part}_weight", st[p + f"ffn.{part}.weight"])
                wv(f"layer_{l}_ffn{part}_bias", st[p + f"ffn.{part}.bias"])

        # Policy head
        for i, s in enumerate(["0", "2"]):
            wv(f"policy_act_enc_{s}_weight", st[f"policy.act_enc.{i*2}.weight"])
            wv(f"policy_act_enc_{s}_bias", st[f"policy.act_enc.{i*2}.bias"])
        for i, s in enumerate(["0", "2"]):
            wv(f"policy_scorer_{s}_weight", st[f"policy.scorer.{i*2}.weight"])
            wv(f"policy_scorer_{s}_bias", st[f"policy.scorer.{i*2}.bias"])

        # Value heads
        for n in ("win", "death", "quantile", "potion", "turns"):
            wv(f"{n}_weight", st[f"{n}.weight"])
            wv(f"{n}_bias", st[f"{n}.bias"])

    print(f"[export] → {path}", flush=True)


if __name__ == "__main__":
    main()
