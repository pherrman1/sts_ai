#!/usr/bin/env python3
"""Value-only combat utility-distribution training (plan-value-targets phase 5).

Trains a value-only network (same 14-token encoder as CombatPVNet, NO policy
head) to predict the MCTS terminal utility distribution directly:

    R = 0 on loss, 50 + endHp on win        (matches BattleScumSearcher3's
    terminal evaluation, curHp + 50).

Target = 51-bin categorical (NBIN default 51): bin 0 = loss / mass around
zero; bins 1..NBIN-1 = endHp/maxHp fraction on wins, mapped back to the HP
scale by maxHp at inference. Loss = cross-entropy. Win probability (1 - p0),
death probability (p0), expected value, and CVaR all derive from the one head.

Bootstrap data: fairgen value rows (single realized outcomes) — default
build/fair34_v.csv (2026-08-07 §3.4 datagen: vnet-era, live-valid, current
controller, 225k rows). Particle-multisample labels (plan phases 2/3)
replace this source with the same target schema when ready.

Two model variants (answer "does policy sharing hurt value quality?"):
  default       = value-only (encoder + util head) — this session
  shared-encoder variant (policy head + policy CE on fairgen policy rows,
  the train_combat_pvnet.py dual-CSV loop) = follow-up, only if the
  value-only result warrants it.

Checkpoint selection: held-out seed distribution CE (sibling ranking/regret
replaces this when phase-4 data exists).

Usage:
  train_combat_utility.py VAL_CSV [OUT]
"""
import os, sys, time
import numpy as np, pandas as pd
import torch
from torch import nn

VAL_CSV = sys.argv[1] if len(sys.argv) > 1 else "build/fair34_v.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_utility.txt"

# ── Hyperparameters ──────────────────────────────────────────────────────────
EPOCHS = int(os.environ.get("UTIL_EPOCHS", "10"))
BATCH = int(os.environ.get("UTIL_BATCH", "512"))
CHUNK = int(os.environ.get("UTIL_CHUNK_ROWS", "50000"))
DEVICE = os.environ.get("UTIL_DEVICE", "cuda")
DIM = int(os.environ.get("UTIL_ENTITY_DIM", "128"))
HIDDEN = int(os.environ.get("UTIL_HIDDEN_DIM", "256"))
HEADS = int(os.environ.get("UTIL_NUM_HEADS", "4"))
LAYERS = int(os.environ.get("UTIL_NUM_LAYERS", "2"))
NBIN = int(os.environ.get("UTIL_BINS", "51"))
LR = float(os.environ.get("UTIL_LR", "1e-4"))
WD = float(os.environ.get("UTIL_WD", "1e-5"))
WIN_BONUS = float(os.environ.get("UTIL_WIN_BONUS", "50"))
MAX_ROWS = int(os.environ.get("UTIL_MAX_ROWS", "0"))  # 0 = all (smoke knob)

VAL_FRAC = float(os.environ.get("UTIL_VAL_FRAC", "0.2"))
TRAIN_ONLY = os.environ.get("UTIL_TRAIN_ONLY", "0") == "1"

def is_val_seed(seed):
    return int(seed) % 100 < int(VAL_FRAC * 100)

if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)} "
          f"VRAM={torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB", flush=True)
else:
    DEVICE = "cpu"
torch.manual_seed(0)
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "8")))


# ── CSV schema (mirrors train_combat_pvnet.py) ───────────────────────────────
val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
RICH_LABELS = "endTurn" in val_header and "potionsConsumed" in val_header
extra_excl = (["endTurn", "potionsConsumed"] +
              [c for c in val_header if c.startswith("pUsed")]) if RICH_LABELS else []
canonical = [c for c in val_header if c not in ("seed", "fightIdx", "won", "endHp", *extra_excl)]
assert len(canonical) == 1766, f"expected 1766 canonical features, got {len(canonical)}"

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


# ── Normalization pass (identical to PVNet trainer) ──────────────────────────
print("[norm] scanning value CSV...", flush=True)
scalar_sum = np.zeros(64, np.float64)
scalar_sq = np.zeros(64, np.float64)
mon_sum = np.zeros(7, np.float64)
mon_sq = np.zeros(7, np.float64)
n_total = 0; n_mon = 0
for df in pd.read_csv(VAL_CSV, chunksize=CHUNK):
    if MAX_ROWS and n_total + len(df) > MAX_ROWS:
        df = df.iloc[:MAX_ROWS - n_total]
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


# ── Model (encoder identical to CombatPVNet; value head only) ────────────────
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
        s = (scalar - self.scalar_mean) * self.scalar_inv
        tokens.append((self.scalar_enc(s) + self.type_embed[0]).unsqueeze(1))
        for z in range(4):
            t = torch.einsum("bc,ce->be", cards[:, z, :].float(), self.card_embed)
            tokens.append((t + self.zone_pos[z] + self.type_embed[1]).unsqueeze(1))
        t = torch.einsum("br,re->be", relics.float(), self.relic_embed)
        if 64 != self.dim: t = self.relic_proj(t)
        tokens.append((t + self.type_embed[2]).unsqueeze(1))
        t = torch.einsum("bp,pe->be", potions.float(), self.potion_embed)
        if 32 != self.dim: t = self.potion_proj(t)
        tokens.append((t + self.type_embed[3]).unsqueeze(1))
        t = self.enc_embed(encounter.long())
        if 32 != self.dim: t = self.enc_proj(t)
        tokens.append((t + self.type_embed[4]).unsqueeze(1))
        for s in range(5):
            alive = mmask[:, s]
            if not alive.any():
                tokens.append(torch.zeros(B, 1, self.dim, device=scalar.device))
                continue
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


class UtilityNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = SharedEncoder()
        self.util = nn.Linear(DIM, NBIN)

    def forward(self, *state):
        return self.encoder(*state)


# ── Targets: 51-bin categorical over R = 0 | 50+endHp ────────────────────────
def utility_targets(y_won, y_hp, max_hp):
    """(N,) long bin indices: 0 = loss; 1..NBIN-1 = win HP-fraction bins."""
    b = torch.zeros_like(y_won, dtype=torch.long)
    won = y_won > 0.5
    if won.any():
        frac = (y_hp[won] / (max_hp[won] + 1e-6)).clamp(0.0, 1.0)
        bb = torch.clamp(torch.ceil(frac * (NBIN - 1)), min=1, max=NBIN - 1).long()
        b[won] = bb
    return b


def bin_midpoints():
    """(NBIN,) HP fractions per bin: bin 0 = 0, bin b = (b-0.5)/(NBIN-1)."""
    m = torch.zeros(NBIN)
    m[1:] = (torch.arange(1, NBIN) - 0.5) / (NBIN - 1)
    return m


def expected_utility(probs, max_hp):
    """EV in the terminal scale (50 + endHp on win): probs (N, NBIN), max_hp (N,)."""
    mids = bin_midpoints().to(probs.device)
    return (probs * (WIN_BONUS + max_hp.unsqueeze(-1) * mids.unsqueeze(0))).sum(-1)


# ── Validation pass (held-out seeds) ────────────────────────────────────────
def validation_pass(model):
    model.eval()
    total = 0.0; total_n = 0
    with torch.no_grad():
        for df in pd.read_csv(VAL_CSV, chunksize=CHUNK):
            if MAX_ROWS and total_n + len(df) > MAX_ROWS:
                df = df.iloc[:MAX_ROWS - total_n]
            m = df["seed"].map(is_val_seed).to_numpy(np.bool_)
            if not m.any(): continue
            sdf = df[m]
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(sdf)
            y_won = sdf["won"].to_numpy(np.float32)
            y_hp = sdf["endHp"].to_numpy(np.float32)
            max_hp = sdf["maxHp"].to_numpy(np.float32)
            yb = utility_targets(torch.from_numpy(y_won), torch.from_numpy(y_hp),
                                 torch.from_numpy(max_hp))
            for b in range(0, len(sdf), BATCH):
                e = min(b + BATCH, len(sdf))
                s, ca, r, po, en, mi, it, mc, mm = to_tensors(
                    scalar[b:e], cards[b:e], relics[b:e], potions[b:e],
                    enc[b:e], mids[b:e], intents[b:e], mcont[b:e], mmask[b:e])
                yt = yb[b:e].to(DEVICE)
                z = model.encoder(s, ca, r, po, en, mi, it, mc, mm)
                logits = model.util(z)
                loss = nn.functional.cross_entropy(logits, yt)
                total += loss.item() * (e - b)
                total_n += e - b
    model.train()
    return total / max(total_n, 1)


# ── Training ─────────────────────────────────────────────────────────────────
def main():
    model = UtilityNet().to(DEVICE)
    model.encoder.scalar_mean.data = torch.from_numpy(scalar_mean).to(DEVICE)
    model.encoder.scalar_inv.data = torch.from_numpy(1.0 / scalar_std).to(DEVICE)
    model.encoder.mon_mean.data = torch.from_numpy(mon_mean).to(DEVICE)
    model.encoder.mon_inv.data = torch.from_numpy(1.0 / mon_std).to(DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[model] value-only utility net: {n_params:,} params, bins={NBIN}", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    best_loss = float("inf")
    t_start = time.time()

    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0.0; total_n = 0
        print(f"\n[epoch {epoch+1}/{EPOCHS}]", flush=True)
        for df in pd.read_csv(VAL_CSV, chunksize=CHUNK):
            if MAX_ROWS and total_n + len(df) > MAX_ROWS:
                df = df.iloc[:MAX_ROWS - total_n]
            if TRAIN_ONLY:
                m = ~df["seed"].map(is_val_seed).to_numpy(np.bool_)
                df = df[m]
                if len(df) == 0: continue
            scalar, cards, relics, potions, enc, mids, intents, mcont, mmask = extract_state(df)
            y_won = df["won"].to_numpy(np.float32)
            y_hp = df["endHp"].to_numpy(np.float32)
            max_hp = df["maxHp"].to_numpy(np.float32)
            yb = utility_targets(torch.from_numpy(y_won), torch.from_numpy(y_hp),
                                 torch.from_numpy(max_hp))
            for b in range(0, len(df), BATCH):
                e = min(b + BATCH, len(df))
                n = e - b
                s, ca, r, po, en, mi, it, mc, mm = to_tensors(
                    scalar[b:e], cards[b:e], relics[b:e], potions[b:e],
                    enc[b:e], mids[b:e], intents[b:e], mcont[b:e], mmask[b:e])
                yt = yb[b:e].to(DEVICE)
                z = model.encoder(s, ca, r, po, en, mi, it, mc, mm)
                logits = model.util(z)
                loss = nn.functional.cross_entropy(logits, yt)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total_loss += loss.item() * n
                total_n += n

        avg_loss = total_loss / max(total_n, 1)
        val_loss = validation_pass(model)
        elapsed = time.time() - t_start
        print(f"  loss={avg_loss:.4f}  val_ce={val_loss:.4f}  {elapsed:.0f}s", flush=True)

        if val_loss < best_loss or epoch == 0:
            best_loss = val_loss
            export_model(model, OUT)

    print(f"\n[done] best_val={best_loss:.4f} → {OUT}  ({time.time()-t_start:.0f}s)", flush=True)


# ── Export (native combat_utility_v1; encoder section identical to v1) ───────
def export_model(model, path):
    st = model.state_dict()
    enc = model.encoder
    with open(path, "w") as f:
        f.write(f"combat_utility_v1\nentity_dim {DIM}\nhidden_dim {HIDDEN}\n"
                f"num_heads {HEADS}\nnum_layers {LAYERS}\n"
                f"nbins {NBIN}\nwin_bonus {WIN_BONUS}\n")

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

        wv("util_weight", st["util.weight"])
        wv("util_bias", st["util.bias"])

    print(f"[export] → {path}", flush=True)


if __name__ == "__main__":
    main()
