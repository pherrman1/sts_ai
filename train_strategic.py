#!/usr/bin/env python3
"""Train a Phase-5 run-level strategic model from `strategicgen2` CSV rows.

Each row is one legal run-level action at a decision: the rich state vector,
the packed GameAction bits, structured candidate fields (c1..c3, cand1..c3), a
`chosen` flag, terminal labels (won, endHp, chosen rows), and Tier-B one-ply
counterfactual labels (labelWon, labelHp, labelFloor, labelBootstrap; NaN for
unsampled decisions).  The network learns a policy (softmax over each decision
group's legal actions, supervised by a (1-STRAT_DIST_LAMBDA) blend of the
chosen row and the softmax(labelWon/STRAT_DIST_TAU) search-distillation
target), one run-value head per
screen (10*won + endHp, trained on that screen's chosen rows), a Q_win(s,a)
head — sigmoid output on the soft win-probability label `labelWon` (BCE; no HP
term in the action score) — and two auxiliary probability heads Q_HP
(labelHp/maxHp) and Q_floor (labelFloor/60), trained jointly with group-CE +
per-screen value-MSE + STRAT_QLAMBDA*Q-BCE + STRAT_HPLAMBDA*HP-BCE +
STRAT_FLOORLAMBDA*floor-BCE.  Action selection uses Q_win only; the auxiliary
heads enrich the shared representation without corrupting the objective.

Memory: the state block is read in pandas chunks and written ONCE to a
group-ordered float16 binary (OUT + "_state.bin"); training then reads
contiguous slices from an mmap of that file, so multi-GB CSVs (tens of
millions of rows) train on a modest-RAM machine.  The file is reused when its
byte size matches nrows*NSTATE*2.
"""
import json, os, sys

# Defragment the CUDA caching allocator before torch initializes; the
# GPU-resident state (6.2 GB) leaves little contiguous VRAM otherwise.
# Respects a user setting.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_200.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_strategic"
# Map-DAG encoder (5.3.2): optional third CLI arg (or STRAT_MAPS_CSV) is the
# `one_combat mapbatch` table (one lossless 15x7 graph per (seed, act)); the
# MAP-screen rows then feed the reverse-DAG encoder with a zero-init residual
# adapter into the (z,b,a,screen) concat. STRAT_FREEZE_BASE=1 freezes every
# non-map parameter (the §62-style isolation run).
MAPS = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("STRAT_MAPS_CSV")
FREEZE_BASE = os.environ.get("STRAT_FREEZE_BASE", "0") != "0"
INIT_PT = os.environ.get("STRAT_INIT_PT")   # seed the base weights (map_* stay fresh)
MAP_SCREEN_ID = 5   # ScreenState::MAP_SCREEN (GameContext.h)
EPOCHS = int(os.environ.get("STRAT_EPOCHS", "60"))
BATCH = int(os.environ.get("STRAT_BATCH", "4096"))   # target ROWS per batch (whole groups)
LR = float(os.environ.get("STRAT_LR", "2e-3"))
VLAMBDA = float(os.environ.get("STRAT_VLAMBDA", "0.5"))
QLAMBDA = float(os.environ.get("STRAT_QLAMBDA", "1.0"))
HPLAMBDA = float(os.environ.get("STRAT_HPLAMBDA", "0.5"))
FLOORLAMBDA = float(os.environ.get("STRAT_FLOORLAMBDA", "0.5"))
# Search distillation (Phase F, 5.7.2): the policy CE blends the one-hot
# chosen target with softmax(labelWon/TAU) search targets:
# (1-LAMBDA)*CE(one-hot chosen) + LAMBDA*CE(softmax(labelWon/TAU)).
DIST_LAMBDA = float(os.environ.get("STRAT_DIST_LAMBDA", "0.5"))
DIST_TAU = float(os.environ.get("STRAT_DIST_TAU", "1.0"))
# Label-noise knobs (all default-off): STRAT_DIST_MARGIN_EPS>0 -> uniform
# target over rows within eps of the group max (denoises the coarse bootstrap
# grid); STRAT_DIST_SPREAD_W>0 -> group weight clip((max-min)/0.15,0,1) on the
# dist term; STRAT_DIST_TERM_W!=1 -> row weight on terminal
# (labelBootstrap==0) rows. Defaults reproduce the §104 numbers exactly.
DIST_MARGIN_EPS = float(os.environ.get("STRAT_DIST_MARGIN_EPS", "0.0"))
DIST_SPREAD_W = float(os.environ.get("STRAT_DIST_SPREAD_W", "0.0"))
DIST_TERM_W = float(os.environ.get("STRAT_DIST_TERM_W", "1.0"))
CLIP = float(os.environ.get("STRAT_CLIP", "1.0"))
CHUNK = int(os.environ.get("STRAT_CHUNK", "250000"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
# Stop after STRAT_PATIENCE epochs without an improvement in held-out
# val_pol_ce (0 = never stop early).  Useful on slow CPU-only machines.
PATIENCE = int(os.environ.get("STRAT_PATIENCE", "0"))
# Default to CUDA when available; STRAT_DEVICE only overrides (e.g. "cpu").
DEVICE = os.environ.get("STRAT_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(THREADS)
torch.manual_seed(0)
print(f"device: {DEVICE}", flush=True)

hdr = pd.read_csv(CSV, nrows=0).columns
need = {"seed", "decIdx", "screen", "action", "actionType", "c1", "c2", "c3",
        "cand1", "cand2", "cand3", "chosen", "won", "endHp", "maxHp",
        "labelWon", "labelHp", "labelFloor"}
missing = need - set(hdr)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")
if "labelWon" not in hdr or "labelHp" not in hdr:
    raise ValueError("Tier-B training requires labelWon,labelHp (strategicgen2 schema)")
opt_cols = ["labelBootstrap"]
for c in opt_cols:
    if c not in hdr:
        print(f"[train-strategic] optional column {c} absent; using NaN", flush=True)

# State block = all numeric columns strictly between `chosen` and `won`
# (found by column index; act/floor live inside it, no separate act column).
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
NSTATE = wi - ci - 1
if NSTATE < 1000:
    raise ValueError(f"expected a rich state block between chosen and won, got {NSTATE} columns")
state_cols = list(hdr[ci + 1:wi])

use_cols = sorted(need | set(opt_cols)
                  | ({"act", "greenKey", "curMapX", "curMapY"} if MAPS else set()))
chunks = pd.read_csv(CSV, usecols=use_cols, chunksize=CHUNK)
small = []
for ch in chunks:
    small.append(ch)
df = pd.concat(small, ignore_index=True)
del small
nrows = len(df)
print(f"{nrows:,} rows, {df.seed.nunique()} seeds", flush=True)

groups = df.seed.to_numpy(np.int64) * 1000000 + df.decIdx.to_numpy(np.int64)
grp_vals, grp_ids = np.unique(groups, return_inverse=True)
NG = len(grp_vals)
sizes = np.bincount(grp_ids, minlength=NG).astype(np.int64)
block_start = np.concatenate(([0], np.cumsum(sizes[:-1])))

chosen = df.chosen.to_numpy(np.int64) == 1
one_chosen = np.bincount(grp_ids[chosen], minlength=NG) == 1
chosen_row_idx = np.full(NG, -1, np.int64)
cp = np.flatnonzero(chosen)
chosen_row_idx[grp_ids[cp]] = cp
act_col = df.action.to_numpy(np.int64)
chosen_act = np.where(chosen_row_idx >= 0, act_col[np.maximum(chosen_row_idx, 0)], -2)
valid_pol = one_chosen & (chosen_act != -1)
print(f"{NG} decisions, {int(one_chosen.sum())} groups with exactly one chosen row "
      f"({int(valid_pol.sum())} with a valid policy action)", flush=True)

# Grouped 80/20 split, shuffling decision groups.
rng = np.random.default_rng(0)
order_g = rng.permutation(NG)
cut = max(1, int(0.8 * NG))
tr_mask = np.zeros(NG, bool)
tr_mask[order_g[:cut]] = True
va_groups = order_g[cut:]
if len(va_groups) == 0:
    raise ValueError("need held-out decision groups")
tr_rows = tr_mask[grp_ids]
print(f"train: {int(tr_rows.sum()):,} rows / {int(tr_mask.sum()):,} groups, "
      f"val: {int((~tr_rows).sum()):,} rows / {len(va_groups):,} groups", flush=True)

# Group-ordered row sequence and its inverse (CSV row -> group-order position).
order = np.argsort(grp_ids, kind="stable")
inv_perm = np.empty(nrows, np.int64)
inv_perm[order] = np.arange(nrows)
pos_of_row = inv_perm.copy()
rank_in_group = pos_of_row - block_start[grp_ids]
cr = np.maximum(chosen_row_idx, 0)
chosen_in_block = np.where(chosen_row_idx >= 0,
                           block_start[grp_ids[cr]] + rank_in_group[cr], -1)
chosen_off = np.where(chosen_in_block >= 0, chosen_in_block - block_start, -1)


def parse_bits(x):
    if isinstance(x, str) and x.startswith("bits="):
        return int(x.split("=")[1])
    return int(x)


action_ints = np.array([parse_bits(x) for x in df.action], np.int64)
cat = np.stack([np.clip(df[c].to_numpy(np.int64) + 1, 0, 511).astype(np.int16)
                for c in ("c1", "c2", "c3", "cand1", "cand2", "cand3")], 1)
atype = np.clip(df.actionType.to_numpy(np.int64) + 1, 0, 15).astype(np.int16)
screen = np.clip(df.screen.to_numpy(np.int64), 0, 15).astype(np.int16)
value = (10 * df.won.to_numpy(np.float32) + df.endHp.to_numpy(np.float32)).astype(np.float32)
# Q_win target: the soft win probability (0/1 on terminal branches, the native
# V_win bootstrap on censored ones, futures-averaged). No HP or floor term.
q_win_target = df.labelWon.to_numpy(np.float32)
q_win_valid = np.isfinite(q_win_target)
# Auxiliary probability targets (normalized; not part of action scoring).
maxHp = np.maximum(df.maxHp.to_numpy(np.float32), 1.0)
q_hp_target = np.clip(df.labelHp.to_numpy(np.float32) / maxHp, 0.0, 1.0).astype(np.float32)
q_hp_valid = np.isfinite(q_hp_target)
q_floor_target = np.clip(df.labelFloor.to_numpy(np.float32) / 60.0, 0.0, 1.0).astype(np.float32)
q_floor_valid = np.isfinite(q_floor_target)
# Terminal/censored row mask (labelBootstrap==0 = exact 0/1 outcome; used by
# the STRAT_DIST_TERM_W row weighting; None when the column is absent).
bt_term = None
if "labelBootstrap" in df:
    bt = df.labelBootstrap.to_numpy(np.float32)
    bt_term = np.isfinite(bt) & (bt == 0)

# --- Map-DAG encoder inputs (5.3.2): per-row graph tensors for MAP_SCREEN
# rows (screen == MAP_SCREEN_ID), zero elsewhere. The table is one lossless
# 15x7 graph per (seed, act) from `one_combat mapbatch` (burningEliteX/Y +
# room0..104 + edges0..104); the burning cell is marked only while the green
# key is absent (mirrors train_meta_entity.py). Position = (curMapX, curMapY,
# child x) — curMapY is -1 before the act's first pick (roots pooled).
USE_MAP = MAPS is not None
map_rooms = map_edges = map_special = None
map_px = map_py = map_chosen = None
if USE_MAP:
    mdf = pd.read_csv(MAPS)
    mkeys = mdf.seed.to_numpy(np.int64) * 16 + mdf.act.to_numpy(np.int64)
    mrooms = mdf[[f"room{i}" for i in range(105)]].to_numpy(np.int16)
    medges = mdf[[f"edges{i}" for i in range(105)]].to_numpy(np.int16)
    mbx = mdf.burningEliteX.to_numpy(np.int16)
    mby = mdf.burningEliteY.to_numpy(np.int16)
    lookup = {int(mkeys[i]): (mrooms[i], medges[i], int(mbx[i]), int(mby[i]))
              for i in range(len(mdf))}
    map_rooms = np.zeros((nrows, 105), np.int16)
    map_edges = np.zeros((nrows, 105), np.int16)
    map_special = np.zeros((nrows, 105), np.int8)
    map_px = np.full(nrows, -1, np.int16)
    map_py = np.full(nrows, -1, np.int16)
    map_chosen = np.full(nrows, -1, np.int16)
    seeds_n = df.seed.to_numpy(np.int64)
    acts_n = df.act.to_numpy(np.int64)
    greens = df.greenKey.to_numpy(np.float32)
    pxs = df.curMapX.to_numpy(np.int64)
    pys = df.curMapY.to_numpy(np.int64)
    c1s = df.c1.to_numpy(np.int64)
    is_map = df.screen.to_numpy(np.int64) == MAP_SCREEN_ID
    keys_n = seeds_n * 16 + acts_n
    for k, (r, e, bxv, byv) in lookup.items():
        sel = is_map & (keys_n == k)
        if not sel.any():
            continue
        map_rooms[sel] = r
        map_edges[sel] = e
        if bxv >= 0 and byv >= 0:
            map_special[sel, byv * 7 + bxv] = np.where(greens[sel] < 0.5, 1, 0).astype(np.int8)
        map_px[sel] = pxs[sel]
        map_py[sel] = pys[sel]
        map_chosen[sel] = c1s[sel]
    print(f"[train-strategic] map-DAG encoder ON: {len(lookup)} maps, "
          f"{int(is_map.sum()):,} MAP-screen rows", flush=True)

# Reorder every small array by group id once: batches are contiguous slices.
action_ints, cat = action_ints[order], cat[order]
atype, screen, value = atype[order], screen[order], value[order]
q_win_target, q_win_valid = q_win_target[order], q_win_valid[order]
q_hp_target, q_hp_valid = q_hp_target[order], q_hp_valid[order]
q_floor_target, q_floor_valid = q_floor_target[order], q_floor_valid[order]
chosen = chosen[order]
if bt_term is not None:
    bt_term = bt_term[order]
if USE_MAP:
    map_rooms, map_edges, map_special = map_rooms[order], map_edges[order], map_special[order]
    map_px, map_py, map_chosen = map_px[order], map_py[order], map_chosen[order]

# --- State block: chunked two-pass stats over TRAIN rows, then scatter to a
# group-ordered float16 file; training reads contiguous mmap slices. ---
mean = np.zeros(NSTATE, np.float64)
sumsq = np.zeros(NSTATE, np.float64)
cnt = 0
lo = 0
for chunk in pd.read_csv(CSV, usecols=state_cols, chunksize=CHUNK, dtype=np.float32):
    hi = lo + len(chunk)
    c = chunk.to_numpy(np.float64)
    m = tr_rows[lo:hi]
    sub = c[m]
    mean += sub.sum(0)
    sumsq += (sub * sub).sum(0)
    cnt += int(m.sum())
    lo = hi
mean /= max(1, cnt)
var = sumsq / max(1, cnt) - mean * mean
std = np.sqrt(np.maximum(var, 0.0))
inv = 1 / np.maximum(std, 1e-6)
mean = mean.astype(np.float32)
inv = inv.astype(np.float32)

STATE_FILE = OUT + "_state.bin"
expected = nrows * NSTATE * 2
reused = False
if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) == expected:
    reused = True
    print(f"[train-strategic] reusing {STATE_FILE} ({expected:,} bytes)", flush=True)
else:
    state_mem = np.memmap(STATE_FILE, dtype=np.float16, mode="w+", shape=(nrows, NSTATE))
    lo = 0
    for chunk in pd.read_csv(CSV, usecols=state_cols, chunksize=CHUNK, dtype=np.float32):
        hi = lo + len(chunk)
        x = np.clip((chunk.to_numpy(np.float64) - mean) * inv, -8, 8).astype(np.float16)
        state_mem[inv_perm[lo:hi]] = x
        lo = hi
    state_mem.flush()
    print(f"[train-strategic] wrote {STATE_FILE} ({expected:,} bytes)", flush=True)

state_mmap = np.memmap(STATE_FILE, dtype=np.float16, mode="r", shape=(nrows, NSTATE))

# GPU-resident state: upload once, gather rows on-device (~0.15 ms vs ~12 ms
# per-batch CPU mmap gather). Falls back to the CPU mmap path on OOM.
state_gpu = None
if DEVICE.startswith("cuda"):
    try:
        state_gpu = torch.from_numpy(np.array(state_mmap)).to(DEVICE, torch.float16)
        print(f"[train-strategic] state resident on GPU: {state_gpu.shape} "
              f"({state_gpu.numel() * 2:,} bytes)", flush=True)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        print("[train-strategic] GPU state upload OOM; using CPU mmap gather", flush=True)


class FullMapGraphEncoder(nn.Module):
    """Bottom-up map-DAG encoder (5.3.2), ported from train_meta_entity.py:
    node = room+row+col+burning embeddings; reverse sweep rows 14->0 with
    mean+max child messages and log1p degree; readout pools the chosen legal
    child's subtree (roots when py<0 = pre-map first pick)."""

    def __init__(self, dnode=32, dout=96):
        super().__init__()
        self.room = nn.Embedding(10, dnode)
        self.row = nn.Embedding(15, dnode)
        self.col = nn.Embedding(7, dnode)
        self.burning = nn.Embedding(2, dnode)
        self.update = nn.Sequential(
            nn.Linear(3 * dnode + 1, 64), nn.LayerNorm(64), nn.SiLU(),
            nn.Linear(64, dnode))
        self.norm = nn.LayerNorm(dnode)
        self.readout = nn.Sequential(
            nn.Linear(2 * dnode, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Linear(128, dout), nn.SiLU())
        self.register_buffer("row_ids", torch.arange(15))
        self.register_buffer("col_ids", torch.arange(7))
        self.register_buffer("edge_bits", torch.arange(7))

    @staticmethod
    def masked_pool(nodes, mask):
        weight = mask.float()
        mean = (nodes * weight.unsqueeze(-1)).sum(1) / weight.sum(1, keepdim=True).clamp_min(1.0)
        maximum = nodes.masked_fill(~mask.unsqueeze(-1), -1e9).max(1).values
        maximum = torch.where(mask.any(1, keepdim=True), maximum, torch.zeros_like(maximum))
        return mean, maximum

    def forward(self, rooms, edges, special, position):
        batch = rooms.shape[0]
        rooms = rooms.long().view(batch, 15, 7)
        edges = edges.long().view(batch, 15, 7)
        special = special.long().view(batch, 15, 7)
        base = (self.room(rooms) + self.row(self.row_ids)[None, :, None, :]
                + self.col(self.col_ids)[None, None, :, :] + self.burning(special))
        adjacency = ((edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        encoded_rows = [base[:, 14]]
        for y in range(13, -1, -1):
            child = encoded_rows[-1]
            edge = adjacency[:, y]
            mean = torch.bmm(edge.float(), child) / edge.sum(2, keepdim=True).clamp_min(1.0)
            expanded = child[:, None, :, :].expand(-1, 7, -1, -1)
            maximum = expanded.masked_fill(~edge.unsqueeze(-1), -1e9).max(2).values
            maximum = torch.where(edge.any(2, keepdim=True), maximum, torch.zeros_like(maximum))
            degree = torch.log1p(edge.sum(2, keepdim=True).float())
            encoded_rows.append(self.norm(base[:, y] + self.update(
                torch.cat((base[:, y], mean, maximum, degree), 2))))
        graph = torch.stack(list(reversed(encoded_rows)), 1)

        px = position[:, 0].long().clamp(0, 6)
        py = position[:, 1].long()
        chosen_x = position[:, 2].long()
        safe_y = py.clamp(0, 14)
        batch_ids = torch.arange(batch, device=rooms.device)
        current_edges = edges[batch_ids, safe_y, px]
        child_mask = ((current_edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        root_mask = edges[:, 0] > 0
        future_mask = torch.where((py < 0).unsqueeze(1), root_mask, child_mask)
        singleton = self.col_ids[None, :] == chosen_x.unsqueeze(1)
        future_mask = torch.where((chosen_x >= 0).unsqueeze(1), future_mask & singleton, future_mask)
        future_mask = future_mask & (py < 14).unsqueeze(1)
        future_y = (py + 1).clamp(0, 14)
        future_nodes = graph[batch_ids, future_y]
        mean, maximum = self.masked_pool(future_nodes, future_mask)
        return self.readout(torch.cat((mean, maximum), 1))


class Net(nn.Module):
    def __init__(self, use_map=False):
        super().__init__()
        self.use_map = use_map
        self.s = nn.Sequential(nn.Linear(NSTATE, 256), nn.LayerNorm(256), nn.GELU(),
                               nn.Dropout(0.2), nn.Linear(256, 128), nn.GELU())
        self.a_bits = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Dropout(0.2),
                                    nn.Linear(32, 16))
        self.a_cat = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Linear(32, 16))
        self.cats = nn.ModuleList([nn.Embedding(512, 4) for _ in range(6)])
        self.atype = nn.Embedding(16, 8)
        self.screen = nn.Embedding(16, 8)
        self.pol = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        # Q_win(s,a) head on the same (z,b,a,screen) concat as the policy head,
        # trained on the soft win-probability label labelWon (sigmoid + BCE).
        self.q = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        # Auxiliary probability heads (shared encoders; never summed into the
        # action score): Q_HP = E[labelHp/maxHp], Q_floor = E[labelFloor/60].
        self.q_hp = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        self.q_floor = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        # One value head per screen (screens 1..8 -> index 0..7), trained on
        # that screen's chosen rows only; the shared encoder is unchanged.
        self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))
                                   for _ in range(8)])
        # Map-DAG route encoder + zero-init residual adapter (5.3.2): the
        # adapter output is added to the (z,b,a,screen) concat for MAP-screen
        # rows only, so at init the MAP path is a no-op on the base heads.
        if use_map:
            self.map_enc = FullMapGraphEncoder()
            self.map_adapter = nn.Sequential(nn.Linear(96, 168), nn.GELU(),
                                             nn.Linear(168, 168))
            with torch.no_grad():
                self.map_adapter[2].weight.zero_()
                self.map_adapter[2].bias.zero_()

    def forward(self, x, bits, cat, atype, screen, map_in=None):
        z = self.s(x)
        b = self.a_bits(bits)
        cat_in = torch.cat([self.cats[i](cat[:, i]) for i in range(6)]
                           + [self.atype(atype)], 1)
        a = self.a_cat(cat_in)
        ha = torch.cat((z, b, a, self.screen(screen)), 1)
        if map_in is not None:
            rooms, edges, special, position = map_in
            ha = ha + self.map_adapter(self.map_enc(rooms, edges, special, position)) \
                     * (screen == MAP_SCREEN_ID).float().unsqueeze(1)
        logit = self.pol(ha).squeeze(1)
        q = self.q(ha).squeeze(1)
        q_hp = self.q_hp(ha).squeeze(1)
        q_floor = self.q_floor(ha).squeeze(1)
        v = torch.empty(z.shape[0], device=z.device)
        for h in range(8):
            m = (screen == h + 1)
            if m.any():
                v[m] = self.vals[h](z[m]).squeeze(1)
        return logit, v, q, q_hp, q_floor


model = Net(USE_MAP).to(DEVICE)
if INIT_PT:
    init_sd = torch.load(INIT_PT, map_location="cpu", weights_only=False)["state_dict"]
    missing, unexpected = model.load_state_dict(init_sd, strict=False)
    if missing and not all(m.startswith("map_") for m in missing):
        raise ValueError(f"STRAT_INIT_PT missing non-map keys: {missing[:8]}")
    print(f"[train-strategic] initialized base from {INIT_PT} "
          f"({len(missing)} map_* keys kept fresh)", flush=True)
if FREEZE_BASE:
    trainable = [p for name, p in model.named_parameters() if name.startswith("map_")]
    opt = torch.optim.AdamW(trainable, lr=LR, weight_decay=2e-4)
    print(f"[train-strategic] STRAT_FREEZE_BASE=1: training only "
          f"{sum(p.numel() for p in trainable):,} map-encoder params", flush=True)
else:
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)

AR = np.arange(32, dtype=np.int64)


def fwd_rows(rows):
    """Forward over an arbitrary row set (epoch-permuted train batch).  The
    rows are gathered once per batch from the group-ordered mmap + small
    arrays; ~BATCH*NSTATE*2 bytes per gather."""
    if state_gpu is not None:
        rg = torch.from_numpy(rows).to(DEVICE)
        x = state_gpu[rg].float()
    else:
        x = torch.from_numpy(state_mmap[rows].copy()).to(DEVICE, torch.float32)
    bits = torch.from_numpy(((action_ints[rows, None] >> AR[None, :]) & 1)
                            .astype(np.float32)).to(DEVICE)
    c = torch.from_numpy(cat[rows]).to(DEVICE, torch.long)
    a = torch.from_numpy(atype[rows]).to(DEVICE, torch.long)
    s = torch.from_numpy(screen[rows]).to(DEVICE, torch.long)
    map_in = None
    if map_rooms is not None:
        map_in = (torch.from_numpy(map_rooms[rows]).to(DEVICE, torch.long),
                  torch.from_numpy(map_edges[rows]).to(DEVICE, torch.long),
                  torch.from_numpy(map_special[rows]).to(DEVICE, torch.long),
                  torch.from_numpy(np.stack([map_px[rows], map_py[rows], map_chosen[rows]], 1))
                  .to(DEVICE, torch.long))
    return model(x, bits, c, a, s, map_in)


def train_batch_loss(gs):
    """Group-CE + per-screen value-MSE + Q_win-BCE + auxiliary HP/floor-BCE
    over the (epoch-permuted) consecutive groups gs; their rows are gathered
    into one batch."""
    sizes_b = sizes[gs]
    rows = np.concatenate([np.arange(block_start[g], block_start[g] + sizes[g])
                           for g in gs])
    logit, val, q, q_hp, q_floor = fwd_rows(rows)
    # Row offset of each group within the gathered batch.
    gstart = np.concatenate(([0], np.cumsum(sizes_b[:-1])))
    # Policy CE: softmax over each group, target = its chosen row.
    ok = valid_pol[gs]
    if ok.any():
        loc = torch.from_numpy(np.repeat(np.arange(len(gs)), sizes_b)).to(DEVICE)
        # Stable per-group logsumexp: subtract each group's OWN max (a group far
        # below the batch max would otherwise underflow to -inf).
        gm = torch.full((len(gs),), float("-inf"), device=DEVICE)
        gm.scatter_reduce_(0, loc, logit, reduce="amax", include_self=True)
        lse = gm + torch.zeros(len(gs), device=DEVICE).scatter_add_(
            0, loc, (logit - gm[loc]).exp()).log()
        # Gather only groups with a valid chosen row: groups without one have
        # chosen_off = -1, which CUDA indexing rejects outright.
        cpos = torch.from_numpy(gstart[ok] + chosen_off[gs][ok]).to(DEVICE)
        pol_ce = -(logit[cpos] - lse[loc[cpos]]).mean()
        # Distillation CE (5.7.2): target = softmax(labelWon/TAU) over each
        # group's finite-label rows (sample-all -> every row is labeled; NaN
        # rows carry zero weight). Uses the same group machinery as the
        # one-hot CE. The soft argmax equals the hard label argmax at any TAU.
        dist_ce = torch.zeros((), device=DEVICE)
        if DIST_LAMBDA > 0.0:
            lwr = torch.from_numpy(q_win_target[rows]).to(DEVICE)
            dvalid = torch.isfinite(lwr)
            lwr = torch.where(dvalid, lwr, torch.tensor(float("-inf"), device=DEVICE))
            has_fin = torch.zeros(len(gs), device=DEVICE).scatter_add_(
                0, loc, dvalid.float()) > 0
            dm = torch.full((len(gs),), float("-inf"), device=DEVICE)
            dm.scatter_reduce_(0, loc, lwr, reduce="amax", include_self=True)
            dm = torch.where(has_fin, dm, torch.zeros((), device=DEVICE))
            # Target weights: exp(lw/tau) by default; with MARGIN_EPS>0 a
            # uniform target over rows within eps of the group max (denoises
            # the coarse bootstrap grid).
            if DIST_MARGIN_EPS > 0.0:
                w = torch.where(dvalid & (lwr >= dm[loc] - DIST_MARGIN_EPS),
                                torch.ones((), device=DEVICE),
                                torch.zeros((), device=DEVICE))
            else:
                w = torch.where(dvalid, torch.exp((lwr - dm[loc]) / DIST_TAU),
                                torch.zeros((), device=DEVICE))
            wsum = torch.zeros(len(gs), device=DEVICE).scatter_add_(0, loc, w)
            p = torch.where(wsum[loc] > 0, w / wsum[loc].clamp_min(1e-12),
                            torch.zeros((), device=DEVICE))
            dmask = torch.from_numpy(ok).to(DEVICE) & has_fin
            # Row weighting for the per-group CE (TERM_W on terminal rows).
            if DIST_TERM_W != 1.0 and bt_term is not None:
                rw = torch.from_numpy(bt_term[rows]).to(DEVICE).float()
                rw = torch.where(rw > 0, torch.tensor(DIST_TERM_W, device=DEVICE),
                                 torch.ones((), device=DEVICE))
                dn = torch.zeros(len(gs), device=DEVICE).scatter_add_(0, loc, rw * p)
                dce = torch.zeros(len(gs), device=DEVICE).scatter_add_(
                    0, loc, rw * p * (logit - lse[loc]))
                dce = torch.where(dn > 0, dce / dn.clamp_min(1e-12),
                                  torch.zeros((), device=DEVICE))
            else:
                dce = torch.zeros(len(gs), device=DEVICE).scatter_add_(
                    0, loc, p * (logit - lse[loc]))
            # Group weighting (SPREAD_W): near-tied groups contribute less.
            if DIST_SPREAD_W > 0.0:
                lwr_mn = torch.where(dvalid, lwr,
                                     torch.tensor(float("inf"), device=DEVICE))
                mn = torch.full((len(gs),), float("inf"), device=DEVICE)
                mn.scatter_reduce_(0, loc, lwr_mn, reduce="amin", include_self=True)
                spread = torch.where(has_fin, dm - mn, torch.zeros((), device=DEVICE))
                gw = torch.clamp(spread / 0.15, 0.0, 1.0)
                if bool((dmask & (gw > 0)).any()):
                    dist_ce = -(dce * gw)[dmask].sum() / gw[dmask].sum()
                else:
                    dist_ce = torch.zeros((), device=DEVICE)
            else:
                dist_ce = -dce[dmask].mean() if bool(dmask.any()) else torch.zeros((), device=DEVICE)
        pol_loss = (1.0 - DIST_LAMBDA) * pol_ce + DIST_LAMBDA * dist_ce
    else:
        pol_loss = torch.zeros((), device=DEVICE)
    # Value MSE on chosen rows only (any group), one mean per screen.
    m = chosen[rows]
    if m.any():
        scr = screen[rows][m]
        tl = torch.from_numpy(value[rows]).to(DEVICE)[m]
        vv = val[m]
        vlosses = []
        for h in range(8):
            mm = (scr == h + 1)
            if mm.any():
                vlosses.append(nn.functional.mse_loss(vv[mm], tl[mm]))
        val_loss = torch.stack(vlosses).mean() if vlosses else torch.zeros((), device=DEVICE)
    else:
        val_loss = torch.zeros((), device=DEVICE)
    # Q_win BCE on all labeled rows in the batch (soft labels, sigmoid output).
    qm = q_win_valid[rows]
    if qm.any():
        ql = torch.from_numpy(q_win_target[rows]).to(DEVICE)[qm]
        q_loss = nn.functional.binary_cross_entropy_with_logits(q[qm], ql)
    else:
        q_loss = torch.zeros((), device=DEVICE)
    # Auxiliary HP / floor BCE (probability heads on the same labeled rows).
    hm = q_hp_valid[rows]
    if hm.any():
        hl = torch.from_numpy(q_hp_target[rows]).to(DEVICE)[hm]
        hp_loss = nn.functional.binary_cross_entropy_with_logits(q_hp[hm], hl)
    else:
        hp_loss = torch.zeros((), device=DEVICE)
    fm = q_floor_valid[rows]
    if fm.any():
        fl = torch.from_numpy(q_floor_target[rows]).to(DEVICE)[fm]
        floor_loss = nn.functional.binary_cross_entropy_with_logits(q_floor[fm], fl)
    else:
        floor_loss = torch.zeros((), device=DEVICE)
    loss = (pol_loss + VLAMBDA * val_loss + QLAMBDA * q_loss
            + HPLAMBDA * hp_loss + FLOORLAMBDA * floor_loss)
    if not torch.isfinite(loss):
        loss = torch.zeros((), device=DEVICE)
    return (loss, float(pol_loss.detach()), float(val_loss.detach()),
            float(q_loss.detach()), float(hp_loss.detach()), float(floor_loss.detach()))


# Fixed evaluation permutation: val-group blocks packed in va_groups order.
va_perm = np.concatenate([np.arange(block_start[g], block_start[g] + sizes[g])
                          for g in va_groups])
va_start = np.full(NG, -1, np.int64)
pos = 0
for g in va_groups:
    va_start[g] = pos
    pos += sizes[g]
va_chosen = chosen[va_perm]
va_target = value[va_perm]
va_screen = screen[va_perm]
va_qwin = q_win_target[va_perm]
va_qwin_valid = q_win_valid[va_perm]
va_qhp = q_hp_target[va_perm]
va_qhp_valid = q_hp_valid[va_perm]
va_qfloor = q_floor_target[va_perm]
va_qfloor_valid = q_floor_valid[va_perm]


@torch.no_grad()
def evaluate():
    """Held-out metrics over the fixed evaluation permutation EV; ranking
    metrics need groups with >= 2 rows."""
    full_logit = np.empty(len(va_perm), np.float32)
    full_val = np.empty(len(va_perm), np.float32)
    full_q = np.empty(len(va_perm), np.float32)
    full_qhp = np.empty(len(va_perm), np.float32)
    full_qfloor = np.empty(len(va_perm), np.float32)
    for lo in range(0, len(va_perm), BATCH):
        hi = min(lo + BATCH, len(va_perm))
        l, v, q, qh, qf = fwd_rows(va_perm[lo:hi])
        full_logit[lo:hi] = l.cpu().numpy()
        full_val[lo:hi] = v.cpu().numpy()
        full_q[lo:hi] = q.cpu().numpy()
        full_qhp[lo:hi] = qh.cpu().numpy()
        full_qfloor[lo:hi] = qf.cpu().numpy()
    vtarget = va_target
    ch = va_chosen
    vmse = float(np.mean((full_val[ch] - vtarget[ch]) ** 2))
    vmae = float(np.mean(np.abs(full_val[ch] - vtarget[ch])))
    per_screen = {}
    scr_all = va_screen
    for h in range(8):
        sm = (scr_all == h + 1) & ch
        if sm.sum() >= 10:
            per_screen[h + 1] = {
                "mae": float(np.mean(np.abs(full_val[sm] - vtarget[sm]))),
                "rmse": float(np.sqrt(np.mean((full_val[sm] - vtarget[sm]) ** 2))),
                "n": int(sm.sum()),
            }
    # Q_win is a probability: report sigmoided predictions vs the soft label.
    qv = va_qwin_valid
    qp = 1.0 / (1.0 + np.exp(-full_q))          # sigmoid of the raw logit
    qbrier = float(np.mean((qp[qv] - va_qwin[qv]) ** 2)) if qv.any() else 0.0
    qmae = float(np.mean(np.abs(qp[qv] - va_qwin[qv]))) if qv.any() else 0.0
    qrmse = float(np.sqrt(np.mean((qp[qv] - va_qwin[qv]) ** 2))) if qv.any() else 0.0
    # Calibration: decile-binned |mean pred - mean label| (Q_win only).
    cal_max = 0.0
    if qv.sum() >= 20:
        order = np.argsort(qp[qv])
        y = va_qwin[qv][order]
        p = qp[qv][order]
        n = len(p)
        for b in range(10):
            lo, hi = (b * n) // 10, ((b + 1) * n) // 10
            if hi - lo >= 5:
                cal_max = max(cal_max, abs(float(p[lo:hi].mean() - y[lo:hi].mean())))
    # Auxiliary heads: sigmoided vs their normalized targets.
    hv = va_qhp_valid
    qhp_p = 1.0 / (1.0 + np.exp(-full_qhp))
    qhp_mae = float(np.mean(np.abs(qhp_p[hv] - va_qhp[hv]))) if hv.any() else 0.0
    fv = va_qfloor_valid
    qf_p = 1.0 / (1.0 + np.exp(-full_qfloor))
    qfloor_mae = float(np.mean(np.abs(qf_p[fv] - va_qfloor[fv]))) if fv.any() else 0.0
    q_screen = {}
    for h in range(8):
        sm = (scr_all == h + 1) & qv
        if sm.sum() >= 10:
            q_screen[h + 1] = {
                "mae": float(np.mean(np.abs(qp[sm] - va_qwin[sm]))),
                "brier": float(np.mean((qp[sm] - va_qwin[sm]) ** 2)),
                "n": int(sm.sum()),
            }
    top1 = 0
    qtop1 = 0
    qtop1_map = 0
    nqtop_map = 0
    margin = 0.0
    ce = 0.0
    ntop = 0
    nqtop = 0
    disttop1 = 0
    ndisttop = 0
    for g in va_groups:
        sz = sizes[g]
        if sz < 2:
            continue
        lo = va_start[g]
        p = full_logit[lo:lo + sz]
        c = int(chosen_off[g])
        parg = -1
        if valid_pol[g]:
            srt = np.sort(p)[::-1]
            top1 += int(np.argmax(p) == c)
            margin += srt[0] - srt[1]
            lse = p.max() + np.log(np.exp(p - p.max()).sum())
            ce += lse - p[c]
            ntop += 1
            parg = int(np.argmax(p))
        qg = qv[lo:lo + sz]
        if qg.sum() >= 2:
            qoracle = np.argmax(va_qwin[lo:lo + sz])
            qpred = np.argmax(qp[lo:lo + sz])
            qtop1 += int(qoracle == qpred)
            nqtop += 1
            if parg >= 0:
                lwoff = int(np.flatnonzero(qg)[np.argmax(va_qwin[lo:lo + sz][qg])])
                disttop1 += int(parg == lwoff)
                ndisttop += 1
            if scr_all[lo] == MAP_SCREEN_ID:
                qtop1_map += int(qoracle == qpred)
                nqtop_map += 1
    return {"groups": ntop,
            "policy_top1": top1 / max(1, ntop),
            "margin": margin / max(1, ntop),
            "value_mae": vmae,
            "value_rmse": float(np.sqrt(vmse)),
            "value_n": int(ch.sum()),
            "value_mae_screen": per_screen,
            "q_top1": qtop1 / max(1, nqtop),
            "q_top1_n": nqtop,
            "dist_top1": disttop1 / max(1, ndisttop),
            "dist_top1_n": ndisttop,
            "q_brier": qbrier,
            "q_mae": qmae,
            "q_rmse": qrmse,
            "q_cal_max": cal_max,
            "q_n": int(qv.sum()),
            "q_mae_screen": q_screen,
            "q_top1_map": qtop1_map / max(1, nqtop_map),
            "q_top1_map_n": nqtop_map,
            "q_hp_mae": qhp_mae,
            "q_floor_mae": qfloor_mae,
            "val_pol_ce": ce / max(1, ntop)}


def to_py(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: to_py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_py(x) for x in obj]
    return obj


best_ce = float("inf")
best_state = None
best_epoch = 0
tr_gs = np.flatnonzero(tr_mask)
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = rng.permutation(tr_gs)
    batches = []
    cur, nrows_b = [], 0
    for g in order:
        cur.append(g)
        nrows_b += sizes[g]
        if nrows_b >= BATCH:
            batches.append(np.asarray(cur))
            cur, nrows_b = [], 0
    if cur:
        batches.append(np.asarray(cur))
    p_losses, v_losses, q_losses, hp_losses, fl_losses = [], [], [], [], []
    for gs in batches:
        loss, pl, vl, ql, hl, fl = train_batch_loss(gs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)
        opt.step()
        p_losses.append(pl)
        v_losses.append(vl)
        q_losses.append(ql)
        hp_losses.append(hl)
        fl_losses.append(fl)
    model.eval()
    em = evaluate()
    if em["val_pol_ce"] < best_ce:
        best_ce = em["val_pol_ce"]
        best_epoch = epoch
        best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if epoch == 1 or epoch % 10 == 0 or epoch == EPOCHS:
        print(f"epoch={epoch:03d} train_pol={np.mean(p_losses):.4f} "
              f"train_val={np.mean(v_losses):.4f} train_q={np.mean(q_losses):.4f} "
              f"train_hp={np.mean(hp_losses):.4f} train_floor={np.mean(fl_losses):.4f} "
              f"val_pol_ce={em['val_pol_ce']:.4f} "
              f"metrics={to_py(em)}", flush=True)
    if PATIENCE > 0 and epoch - best_epoch >= PATIENCE and best_state is not None:
        print(f"[train-strategic] early stop: no val_pol_ce improvement for "
              f"{PATIENCE} epochs (best epoch {best_epoch})", flush=True)
        break

model.load_state_dict(best_state)
model.eval()
eval_metrics = to_py(evaluate())
print(f"\nbest held-out (val_pol_ce={best_ce:.4f}): {eval_metrics}", flush=True)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.cpu().state_dict(), "mean": mean, "inv": inv,
            "metrics": eval_metrics, "features": NSTATE, "nrows": int(nrows),
            "maps": bool(USE_MAP)},
           OUT + ".pt")
with open(OUT + "_metrics.json", "w") as f:
    json.dump(eval_metrics, f, indent=2)
print(f"wrote {OUT}.pt, {OUT}_metrics.json", flush=True)
