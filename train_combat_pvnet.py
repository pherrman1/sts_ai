#!/usr/bin/env python3
"""CombatPolicyValueNet training — binary-preprocessed, vectorized, GPU-efficient.

Preprocesses fairgen CSVs once into compact float16 memmaps (like
train_strategic_tok.py), then trains from the memmap with no pandas in the
training loop. Policy loss is vectorized across all action groups via scatter
operations instead of a per-group Python loop.

Usage:
  train_combat_pvnet.py VAL_CSV POL_CSV [OUT]
"""
import hashlib, os, sys, time
import numpy as np
import pandas as pd
import torch
from torch import nn

VAL_CSV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fair_final_v.csv"
POL_CSV = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fair_final_p.csv"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_pvnet.txt"

# ── Hyperparameters ──────────────────────────────────────────────────────────
EPOCHS = int(os.environ.get("PVNET_EPOCHS", "10"))
BATCH = int(os.environ.get("PVNET_BATCH", "512"))
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
COMPILE = os.environ.get("PVNET_COMPILE", "1") == "1"
USE_AMP = os.environ.get("PVNET_AMP", "0") == "1"
CHUNK = int(os.environ.get("PVNET_CHUNK_ROWS", "50000"))  # preprocessing chunk

LAMBDA = {"policy": L_POL, "win": L_WIN, "quantile": L_QUANT,
          "potion": 0.2, "turns": 0.1, "death": 1.0}

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
if DEVICE.startswith("cuda"):
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    torch.set_float32_matmul_precision("high")

# ── CSV schema ───────────────────────────────────────────────────────────────
val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
RICH_LABELS = "endTurn" in val_header and "potionsConsumed" in val_header
pused_cols = [c for c in val_header if c.startswith("pUsed")]
if RICH_LABELS:
    extra_excl = ["endTurn", "potionsConsumed"] + pused_cols
else:
    extra_excl = []
    print("[pvnet] WARNING: value CSV has no endTurn/potionsConsumed/pUsed* "
          "rich labels; potion/turns heads will stay fallback-trained. "
          "Re-generate with fairgen on the current binary for full labels.",
          flush=True)
canonical = [c for c in val_header
             if c not in ("seed", "fightIdx", "won", "endHp", *extra_excl)]
assert len(canonical) == 1766

pol_header = list(pd.read_csv(POL_CSV, nrows=0).columns)
POL_META = ("seed", "fightIdx", "decIdx", "visit", "total")
action_names = [c for c in pol_header if c not in canonical and c not in POL_META]
assert len(action_names) >= 14
action_names = action_names[:14]

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

# ── Binary layout: pre-extracted state components, float16 ───────────────────
# 1771 elements per row: scalar(64) + cards(4*371) + relics(128) + potions(44)
#   + encounter(1) + mids(5) + intents(5) + mcont(35) + mmask(5)
NSTATE = 64 + 4 * 371 + 128 + 44 + 1 + 5 + 5 + 35 + 5  # 1771
S_SCALAR = slice(0, 64)
S_CARDS = slice(64, 64 + 1484)
S_RELICS = slice(64 + 1484, 64 + 1484 + 128)
S_POTIONS = slice(64 + 1484 + 128, 64 + 1484 + 128 + 44)
I_ENCOUNTER = 64 + 1484 + 128 + 44
S_MIDS = slice(I_ENCOUNTER + 1, I_ENCOUNTER + 1 + 5)
S_INTENTS = slice(I_ENCOUNTER + 1 + 5, I_ENCOUNTER + 1 + 5 + 5)
S_MCONT = slice(I_ENCOUNTER + 1 + 5 + 5, I_ENCOUNTER + 1 + 5 + 5 + 35)
S_MMASK = slice(I_ENCOUNTER + 1 + 5 + 5 + 35, I_ENCOUNTER + 1 + 5 + 5 + 35 + 5)

# Label columns for value rows
V_LABEL_COLS = ["won", "endHp", "maxHp"]
if RICH_LABELS:
    V_LABEL_COLS += ["endTurn", "turn"] + pused_cols
N_VLABEL = len(V_LABEL_COLS)


# ── State extraction (pandas-based, used only during preprocessing) ──────────
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


def pack_state(scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask):
    """Pack extracted components into a single (N, NSTATE) float16 array."""
    n = len(scalar)
    out = np.zeros((n, NSTATE), np.float16)
    out[:, S_SCALAR] = scalar.astype(np.float16)
    out[:, S_CARDS] = cards.reshape(n, -1).astype(np.float16)
    out[:, S_RELICS] = relics.astype(np.float16)
    out[:, S_POTIONS] = potions.astype(np.float16)
    out[:, I_ENCOUNTER] = encounter.astype(np.float16)
    out[:, S_MIDS] = mids.astype(np.float16)
    out[:, S_INTENTS] = intents.astype(np.float16)
    out[:, S_MCONT] = mcont.reshape(n, -1).astype(np.float16)
    out[:, S_MMASK] = mmask.astype(np.float16)
    return out


def unpack_state(row):
    """row: (N, NSTATE) float32 array → components as tensors on DEVICE."""
    scalar = torch.from_numpy(np.ascontiguousarray(row[:, S_SCALAR])).to(DEVICE)
    cards = torch.from_numpy(np.ascontiguousarray(row[:, S_CARDS].reshape(-1, 4, 371))).to(DEVICE)
    relics = torch.from_numpy(np.ascontiguousarray(row[:, S_RELICS])).to(DEVICE)
    potions = torch.from_numpy(np.ascontiguousarray(row[:, S_POTIONS])).to(DEVICE)
    encounter = torch.from_numpy(np.ascontiguousarray(row[:, I_ENCOUNTER])).to(DEVICE)
    mids = torch.from_numpy(np.ascontiguousarray(row[:, S_MIDS])).to(DEVICE)
    intents = torch.from_numpy(np.ascontiguousarray(row[:, S_INTENTS])).to(DEVICE)
    mcont = torch.from_numpy(np.ascontiguousarray(row[:, S_MCONT].reshape(-1, 5, 7))).to(DEVICE)
    mmask = torch.from_numpy(np.ascontiguousarray(row[:, S_MMASK] > 0.5)).to(DEVICE)
    return scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask


# ── Normalization pass + binary preprocessing ────────────────────────────────
V_STATE_FILE = OUT + "_v_state.bin"
V_SEED_FILE = OUT + "_v_seed.bin"
V_LABEL_FILE = OUT + "_v_labels.bin"
P_STATE_FILE = OUT + "_p_state.bin"
P_SEED_FILE = OUT + "_p_seed.bin"
P_ACT_FILE = OUT + "_p_act.bin"
P_VISIT_FILE = OUT + "_p_visit.bin"
P_TOTAL_FILE = OUT + "_p_total.bin"
P_OFFSET_FILE = OUT + "_p_offset.bin"
FP_FILE = OUT + "_pvnet_binaries.fp"

# Fingerprint to skip reprocessing
fp = hashlib.sha256()
for f in (VAL_CSV, POL_CSV, os.path.abspath(__file__)):
    try:
        st = os.stat(f)
        fp.update(f.encode()); fp.update(str(st.st_size).encode()); fp.update(str(st.st_mtime_ns).encode())
    except OSError:
        pass
fp.update(str(RICH_LABELS).encode())
fp_hex = fp.hexdigest()

binaries_exist = all(os.path.exists(f) for f in (
    V_STATE_FILE, V_SEED_FILE, V_LABEL_FILE,
    P_STATE_FILE, P_SEED_FILE, P_ACT_FILE, P_VISIT_FILE, P_TOTAL_FILE, P_OFFSET_FILE))
old_fp = None
if os.path.exists(FP_FILE):
    with open(FP_FILE) as f:
        old_fp = f.read().strip()

if not binaries_exist or old_fp != fp_hex:
    # ── Normalization scan (all value rows) ──
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

    # ── Build value binary ──
    print("[prep] building value binary...", flush=True)
    n_val = 0
    for df in pd.read_csv(VAL_CSV, chunksize=CHUNK, usecols=canonical + ["seed"] + V_LABEL_COLS):
        n_val += len(df)
    v_state = np.memmap(V_STATE_FILE, dtype=np.float16, mode="w+", shape=(n_val, NSTATE))
    v_seed = np.memmap(V_SEED_FILE, dtype=np.int32, mode="w+", shape=(n_val,))
    v_label = np.memmap(V_LABEL_FILE, dtype=np.float16, mode="w+", shape=(n_val, N_VLABEL))
    lo = 0
    for df in pd.read_csv(VAL_CSV, chunksize=CHUNK):
        hi = lo + len(df)
        s, c, r, p, e, mi, it, mc, mm = extract_state(df)
        v_state[lo:hi] = pack_state(s, c, r, p, e, mi, it, mc, mm)
        v_seed[lo:hi] = df["seed"].to_numpy(np.int32)
        labels = df[V_LABEL_COLS].to_numpy(np.float32).astype(np.float16)
        v_label[lo:hi] = labels
        lo = hi
    v_state.flush(); v_seed.flush(); v_label.flush()
    print(f"[prep] value: {n_val:,} rows → {V_STATE_FILE} ({n_val * NSTATE * 2:,} bytes)", flush=True)

    # ── Build policy binary ──
    print("[prep] building policy binary...", flush=True)
    # Read entire policy CSV, sort by group key to get clean contiguous groups
    pol_df = pd.read_csv(POL_CSV)
    pol_df["_grp"] = (pol_df["seed"].astype(np.int64) * 1000000 +
                      pol_df["fightIdx"].astype(np.int64) * 10000 +
                      pol_df["decIdx"].astype(np.int64))
    pol_df = pol_df.sort_values("_grp", kind="mergesort").reset_index(drop=True)

    # Find group boundaries
    grp = pol_df["_grp"].to_numpy(np.int64)
    changes = np.where(grp[1:] != grp[:-1])[0] + 1
    g_starts = np.concatenate([[0], changes])
    g_ends = np.concatenate([changes, [len(pol_df)]])
    valid = (g_ends - g_starts) >= 2
    g_starts = g_starts[valid]
    g_ends = g_ends[valid]
    n_g = len(g_starts)
    n_act_total = int((g_ends - g_starts).sum())

    print(f"[prep] policy: {n_g:,} groups, {n_act_total:,} actions", flush=True)

    # Extract group-start states
    gs_rows = pol_df.iloc[g_starts]
    s, c, r, p, e, mi, it, mc, mm = extract_state(gs_rows[canonical])

    p_state = np.memmap(P_STATE_FILE, dtype=np.float16, mode="w+", shape=(n_g, NSTATE))
    p_state[:] = pack_state(s, c, r, p, e, mi, it, mc, mm)
    p_state.flush()

    p_seed = np.memmap(P_SEED_FILE, dtype=np.int32, mode="w+", shape=(n_g,))
    p_seed[:] = pol_df["seed"].iloc[g_starts].to_numpy(np.int32)
    p_seed.flush()

    p_total = np.memmap(P_TOTAL_FILE, dtype=np.int32, mode="w+", shape=(n_g,))
    p_total[:] = pol_df["total"].iloc[g_starts].to_numpy(np.int32)
    p_total.flush()

    p_act = np.memmap(P_ACT_FILE, dtype=np.float16, mode="w+", shape=(n_act_total, 14))
    p_visit = np.memmap(P_VISIT_FILE, dtype=np.int32, mode="w+", shape=(n_act_total,))
    p_offset = np.memmap(P_OFFSET_FILE, dtype=np.int32, mode="w+", shape=(n_g + 1,))

    pos = 0
    for gi in range(n_g):
        gs, ge = g_starts[gi], g_ends[gi]
        sz = ge - gs
        p_act[pos:pos + sz] = pol_df[action_names].iloc[gs:ge].to_numpy(np.float32).astype(np.float16)
        p_visit[pos:pos + sz] = pol_df["visit"].iloc[gs:ge].to_numpy(np.int32)
        p_offset[gi] = pos
        pos += sz
    p_offset[n_g] = pos
    p_act.flush(); p_visit.flush(); p_offset.flush()

    with open(FP_FILE, "w") as f:
        f.write(fp_hex)
    print(f"[prep] policy: {n_g:,} groups → {P_STATE_FILE}", flush=True)
    del pol_df
else:
    # Re-read normalization stats from the binary values
    print("[prep] reusing binary files, recomputing normalization...", flush=True)
    n_val_tmp = os.path.getsize(V_STATE_FILE) // (NSTATE * 2)
    v_state_tmp = np.memmap(V_STATE_FILE, dtype=np.float16, mode="r", shape=(n_val_tmp, NSTATE))
    scalar_raw = v_state_tmp[:, S_SCALAR].astype(np.float64)
    scalar_mean = scalar_raw.mean(axis=0).astype(np.float32)
    scalar_sq = (scalar_raw ** 2).mean(axis=0)
    scalar_std = np.sqrt(np.maximum(scalar_sq - scalar_mean.astype(np.float64) ** 2, 0)).astype(np.float32) + 1e-6
    mcont_all = v_state_tmp[:, S_MCONT].astype(np.float64)
    mmask_all = v_state_tmp[:, S_MMASK].astype(np.float64)
    mon_mask = mmask_all.reshape(-1, 5) > 0.5
    mon_vals = mcont_all.reshape(-1, 5, 7)[mon_mask]
    if len(mon_vals) > 0:
        mon_mean = mon_vals.mean(axis=0).astype(np.float32)
        mon_sq = (mon_vals ** 2).mean(axis=0)
        mon_std = np.sqrt(np.maximum(mon_sq - mon_mean.astype(np.float64) ** 2, 0)).astype(np.float32) + 1e-6
    else:
        mon_mean = np.zeros(7, np.float32)
        mon_std = np.ones(7, np.float32)
    del v_state_tmp
    print(f"[prep] normalization recomputed from {n_val_tmp:,} binary rows", flush=True)

# ── Open memmaps ──
n_val = os.path.getsize(V_STATE_FILE) // (NSTATE * 2)
v_state_mmap = np.memmap(V_STATE_FILE, dtype=np.float16, mode="r", shape=(n_val, NSTATE))
v_seed_mmap = np.memmap(V_SEED_FILE, dtype=np.int32, mode="r", shape=(n_val,))
v_label_mmap = np.memmap(V_LABEL_FILE, dtype=np.float16, mode="r", shape=(n_val, N_VLABEL))

n_groups = os.path.getsize(P_STATE_FILE) // (NSTATE * 2)
p_state_mmap = np.memmap(P_STATE_FILE, dtype=np.float16, mode="r", shape=(n_groups, NSTATE))
p_seed_mmap = np.memmap(P_SEED_FILE, dtype=np.int32, mode="r", shape=(n_groups,))
p_act_mmap = np.memmap(P_ACT_FILE, dtype=np.float16, mode="r",
                       shape=(os.path.getsize(P_ACT_FILE) // (14 * 2), 14))
p_visit_mmap = np.memmap(P_VISIT_FILE, dtype=np.int32, mode="r",
                         shape=(os.path.getsize(P_VISIT_FILE) // 4,))
p_total_mmap = np.memmap(P_TOTAL_FILE, dtype=np.int32, mode="r", shape=(n_groups,))
p_offset_mmap = np.memmap(P_OFFSET_FILE, dtype=np.int32, mode="r", shape=(n_groups + 1,))

# Precompute train/val masks
v_is_val = np.array([is_val_seed(s) for s in v_seed_mmap])
v_train = ~v_is_val if TRAIN_ONLY else np.ones(n_val, bool)
v_train_rows = np.flatnonzero(v_train)
v_val_rows = np.flatnonzero(v_is_val)

p_is_val = np.array([is_val_seed(s) for s in p_seed_mmap])
p_train_groups = np.flatnonzero(~p_is_val if TRAIN_ONLY else np.ones(n_groups, bool))
p_val_groups = np.flatnonzero(p_is_val)

print(f"[data] value: {n_val:,} rows (train={len(v_train_rows):,}, val={len(v_val_rows):,})", flush=True)
print(f"[data] policy: {n_groups:,} groups (train={len(p_train_groups):,}, val={len(p_val_groups):,})",
      flush=True)

# ── Model ────────────────────────────────────────────────────────────────────
class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden, heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, hidden), nn.GELU(), nn.Linear(hidden, dim))
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        a, _ = self.attn(x, x, x, need_weights=False)
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
        t = self.enc_embed(encounter.long().clamp(0, 127))
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
        return x[:, 0, :]


class PolicyHead(nn.Module):
    def __init__(self, dim=DIM):
        super().__init__()
        self.act_enc = nn.Sequential(nn.Linear(14, 64), nn.ReLU(), nn.Linear(64, dim), nn.ReLU())
        self.scorer = nn.Sequential(nn.Linear(dim * 3, dim), nn.ReLU(), nn.Linear(dim, 1))

    def forward(self, z_global, action_feats):
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
def policy_loss_vectorized(logits, group_ids, visits, totals):
    """Vectorized grouped cross-entropy via scatter operations.

    logits: (N_actions,)  group_ids: (N_actions,)  visits: (N_actions,)
    totals: (N_groups,)  — returns scalar mean over groups.
    """
    n_g = len(totals)
    # Per-group log-sum-exp
    max_g = torch.full((n_g,), float("-inf"), device=logits.device)
    max_g.scatter_reduce_(0, group_ids, logits, reduce="amax", include_self=False)
    shifted = logits - max_g[group_ids]
    lse_g = max_g + torch.zeros(n_g, device=logits.device).scatter_add_(
        0, group_ids, shifted.exp()).clamp_min(1e-30).log()

    log_probs = logits - lse_g[group_ids]
    targets = visits.float() / (totals[group_ids].float() + 1e-8)

    per_group_ce = torch.zeros(n_g, device=logits.device)
    per_group_ce.scatter_add_(0, group_ids, -(targets * log_probs))
    return per_group_ce.mean()


def value_losses(preds, y_won, y_hp, max_hp, y_pot=None, y_turns=None):
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
    if y_pot is not None:
        mask = y_pot.sum(-1) > 0
        if mask.any():
            lp = nn.functional.binary_cross_entropy_with_logits(
                preds["potion"][mask], y_pot[mask])
        else:
            lp = 0.01 * preds["potion"].abs().mean()
    else:
        lp = 0.01 * preds["potion"].abs().mean()
    if y_turns is not None:
        lt = nn.functional.smooth_l1_loss(preds["turns"], torch.log1p(y_turns))
    else:
        lt = torch.tensor(0.0, device=DEVICE)
    return {"death": ld, "win": lw, "quantile": lq, "potion": lp, "turns": lt}


def value_forward(model, encoder_fn, rows, labels):
    """Forward value heads on a batch of state rows. labels: (B, N_VLABEL) float16."""
    row_data = v_state_mmap[rows].astype(np.float32)
    s, ca, r, po, en, mi, it, mc, mm = unpack_state(row_data)
    z = encoder_fn(s, ca, r, po, en, mi, it, mc, mm)
    out = {
        "death": model.death(z).squeeze(-1),
        "win": model.win(z).squeeze(-1),
        "quantile": model.quantile(z),
        "potion": model.potion(z),
        "turns": model.turns(z).squeeze(-1),
    }
    yw = torch.from_numpy(np.ascontiguousarray(labels[:, 0].astype(np.float32))).to(DEVICE)
    yh = torch.from_numpy(np.ascontiguousarray(labels[:, 1].astype(np.float32))).to(DEVICE)
    mh = torch.from_numpy(np.ascontiguousarray(labels[:, 2].astype(np.float32))).to(DEVICE)
    yp = yt = None
    if RICH_LABELS:
        yt_raw = np.maximum(0.0, labels[:, 3].astype(np.float32) - labels[:, 4].astype(np.float32))
        yt = torch.from_numpy(np.ascontiguousarray(yt_raw)).to(DEVICE)
        yp = torch.from_numpy(np.ascontiguousarray(labels[:, 5:].astype(np.float32))).to(DEVICE)
    vlosses = value_losses(out, yw, yh, mh, yp, yt)
    loss = sum(LAMBDA[k] * vlosses[k] for k in vlosses)
    return loss


def validation_pass(model, encoder_fn, policy_fn):
    model.eval()
    total_v = 0.0; total_p = 0.0; total_n = 0
    with torch.no_grad():
        # Value validation
        for b in range(0, len(v_val_rows), BATCH):
            e = min(b + BATCH, len(v_val_rows))
            rows = v_val_rows[b:e]
            n = e - b
            labels = v_label_mmap[rows]
            loss = value_forward(model, encoder_fn, rows, labels)
            total_v += loss.item() * n
            total_n += n

        # Policy validation (vectorized)
        for b in range(0, len(p_val_groups), BATCH):
            be = min(b + BATCH, len(p_val_groups))
            gs = p_val_groups[b:be]
            n_g = be - b
            if n_g == 0:
                continue

            # Gather group-start states
            gs_rows = p_state_mmap[gs].astype(np.float32)
            s, ca, r, po, en, mi, it, mc, mm = unpack_state(gs_rows)
            z_all = encoder_fn(s, ca, r, po, en, mi, it, mc, mm)

            # Collect all actions for these groups
            offsets = p_offset_mmap[gs]
            ends = p_offset_mmap[gs + 1]
            sizes = ends - offsets
            total_actions = int(sizes.sum())
            if total_actions == 0:
                continue

            # Build flat action arrays and group_ids
            act_idx = np.concatenate([np.arange(offsets[i], ends[i]) for i in range(n_g)])
            group_ids = np.repeat(np.arange(n_g), sizes)

            z_expanded = z_all[torch.from_numpy(group_ids).to(DEVICE)]
            act_t = torch.from_numpy(np.ascontiguousarray(
                p_act_mmap[act_idx].astype(np.float32))).to(DEVICE)
            vis_t = torch.from_numpy(p_visit_mmap[act_idx].astype(np.float32).copy()).to(DEVICE)
            totals_t = torch.from_numpy(p_total_mmap[gs].astype(np.int32)).to(DEVICE)
            gids_t = torch.from_numpy(group_ids).to(DEVICE)

            logits = policy_fn(z_expanded, act_t)
            ce = policy_loss_vectorized(logits, gids_t, vis_t, totals_t)
            total_p += ce.item() * total_actions
            total_n += total_actions

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

    # torch.compile — compile the expensive submodules individually.
    # Compiling at the PolicyValueNet level doesn't help because we call
    # model.encoder() / model.policy() directly, which bypasses the wrapper.
    encoder_fn = model.encoder
    policy_fn = model.policy
    if COMPILE and DEVICE.startswith("cuda"):
        try:
            torch._dynamo.config.suppress_errors = True
            encoder_fn = torch.compile(model.encoder, mode="default")
            policy_fn = torch.compile(model.policy, mode="default")
            print("[pvnet] torch.compile enabled on encoder + policy head (default mode)", flush=True)
        except Exception as ex:
            print(f"[pvnet] torch.compile failed ({ex!r}); running eager", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    scaler = torch.amp.GradScaler("cuda") if USE_AMP and DEVICE.startswith("cuda") else None
    if scaler is not None:
        print("[pvnet] AMP enabled (FP16 autocast + GradScaler)", flush=True)

    best_loss = float("inf")
    t_start = time.time()

    for epoch in range(EPOCHS):
        model.train()
        total_v = 0.0; total_p = 0.0; total_n = 0
        print(f"\n[epoch {epoch+1}/{EPOCHS}]", flush=True)

        # ── Value training pass ──
        rng = np.random.default_rng(epoch)
        v_order = rng.permutation(v_train_rows)
        for b in range(0, len(v_order), BATCH):
            e = min(b + BATCH, len(v_order))
            rows = v_order[b:e]
            n = e - b
            labels = v_label_mmap[rows]

            optimizer.zero_grad(set_to_none=True)
            if scaler is not None:
                with torch.autocast("cuda", dtype=torch.float16):
                    loss = value_forward(model, encoder_fn, rows, labels)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                loss = value_forward(model, encoder_fn, rows, labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

            total_v += loss.item() * n
            total_n += n

        # ── Policy training pass (vectorized) ──
        p_order = rng.permutation(p_train_groups)
        for b in range(0, len(p_order), BATCH):
            be = min(b + BATCH, len(p_order))
            gs = p_order[b:be]
            n_g = be - b
            if n_g == 0:
                continue

            # Gather group-start states and encode
            g_rows = p_state_mmap[gs].astype(np.float32)
            s, ca, r, po, en, mi, it, mc, mm = unpack_state(g_rows)
            z_all = encoder_fn(s, ca, r, po, en, mi, it, mc, mm)

            # Collect all actions for these groups
            offsets = p_offset_mmap[gs]
            ends = p_offset_mmap[gs + 1]
            sizes = ends - offsets
            total_actions = int(sizes.sum())
            if total_actions == 0:
                continue

            # Flat action arrays and group_ids
            act_idx = np.concatenate([np.arange(offsets[i], ends[i]) for i in range(n_g)])
            group_ids = np.repeat(np.arange(n_g), sizes)

            z_expanded = z_all[torch.from_numpy(group_ids).to(DEVICE)]
            act_t = torch.from_numpy(np.ascontiguousarray(
                p_act_mmap[act_idx].astype(np.float32))).to(DEVICE)
            vis_t = torch.from_numpy(p_visit_mmap[act_idx].astype(np.float32).copy()).to(DEVICE)
            totals_t = torch.from_numpy(p_total_mmap[gs].astype(np.int32)).to(DEVICE)
            gids_t = torch.from_numpy(group_ids).to(DEVICE)

            optimizer.zero_grad(set_to_none=True)
            if scaler is not None:
                with torch.autocast("cuda", dtype=torch.float16):
                    logits = policy_fn(z_expanded, act_t)
                    p_loss = policy_loss_vectorized(logits, gids_t, vis_t, totals_t)
                    loss = LAMBDA["policy"] * p_loss
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                logits = policy_fn(z_expanded, act_t)
                p_loss = policy_loss_vectorized(logits, gids_t, vis_t, totals_t)
                loss = LAMBDA["policy"] * p_loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

            total_p += p_loss.item() * total_actions
            total_n += total_actions

        val_loss = validation_pass(model, encoder_fn, policy_fn)
        elapsed = time.time() - t_start
        print(f"  v={total_v/max(total_n,1):.4f}  p={total_p/max(total_n,1):.4f}  "
              f"val={val_loss:.4f}  {elapsed:.0f}s", flush=True)

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

        for i, s in enumerate(["0", "2"]):
            wv(f"policy_act_enc_{s}_weight", st[f"policy.act_enc.{i*2}.weight"])
            wv(f"policy_act_enc_{s}_bias", st[f"policy.act_enc.{i*2}.bias"])
        for i, s in enumerate(["0", "2"]):
            wv(f"policy_scorer_{s}_weight", st[f"policy.scorer.{i*2}.weight"])
            wv(f"policy_scorer_{s}_bias", st[f"policy.scorer.{i*2}.bias"])

        for n in ("win", "death", "quantile", "potion", "turns"):
            wv(f"{n}_weight", st[f"{n}.weight"])
            wv(f"{n}_bias", st[f"{n}.bias"])

    print(f"[export] → {path}", flush=True)


if __name__ == "__main__":
    main()
