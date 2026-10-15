#!/usr/bin/env python3
"""PPO/GAE policy trainer from `strategicgen2` CSV rows (OOC continuation R8).

Same row schema, state/action encoders, head contract and held-out metrics as
`train_strategic.py` (V3), but the policy objective is a PPO-clip surrogate
instead of group-CE, and the value head trains on EVERY group's state (not
only chosen rows) with GAE returns.

Trajectory reconstruction: per seed, decision groups sorted by decIdx form the
run sequence s_0, a_0, s_1, ...; s_t is the state block of group t's rows
(take the first row), the successor is the next group, and after the last
group the run is terminal (V(s_{T+1}) = 0).  Df_t = max(0, floor_{t+1} -
floor_t) with floor = state column index 2 (z-normalized, read back from the
state file).  Non-terminal rewards are 0; the terminal reward is 10*won +
endHp.  GAE: delta_t = r_t + gamma^Df * V_old(s_{t+1}) - V_old(s_t); A_t =
delta_t + sum_{k>=1} (gamma*lambda)^{cumsum Df} * delta_{t+k}, i.e. the
advantage chain decays by (gamma*lambda) per elapsed floor, accumulated
cumulatively (A_t = delta_t + (gamma*lambda)^Df_t * A_{t+1}).  V_old is a
per-epoch frozen snapshot of the value heads (computed on GPU in chunks).

Losses: PPO clip (PPO_EPS) on the chosen-row logit ratio with per-epoch frozen
old logits; 0.5 * per-screen value-MSE on all train group states (target
A_t + V_old(s_t)); PPO_QLAMBDA * Q-MSE on Tier-B labels (10*labelWon +
labelHp).  Best checkpoint by held-out val_pol_ce.

Memory: the state block is read in pandas chunks and written ONCE to a
group-ordered float16 binary (OUT + "_ppo_state.bin"); training then reads
contiguous slices from an mmap of that file.  The file is reused when its
byte size matches nrows*NSTATE*2.  Trajectory/advantage arrays are per-group
numpy, recomputed each epoch from the V_old snapshot.
"""
import json, os, sys

import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_tierb.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_strategic_ppo"
EPOCHS = int(os.environ.get("STRAT_EPOCHS", "40"))
BATCH = int(os.environ.get("STRAT_BATCH", "4096"))   # target ROWS per batch (whole groups)
LR = float(os.environ.get("STRAT_LR", "2e-3"))
CLIP = float(os.environ.get("STRAT_CLIP", "1.0"))
PPO_GAMMA = float(os.environ.get("PPO_GAMMA", "0.995"))
PPO_LAMBDA = float(os.environ.get("PPO_LAMBDA", "0.95"))
PPO_EPS = float(os.environ.get("PPO_EPS", "0.2"))
PPO_QLAMBDA = float(os.environ.get("PPO_QLAMBDA", "1.0"))
CHUNK = int(os.environ.get("STRAT_CHUNK", "250000"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
# Default to CUDA when available; STRAT_DEVICE only overrides (e.g. "cpu").
DEVICE = os.environ.get("STRAT_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(THREADS)
torch.manual_seed(0)
print(f"device: {DEVICE}  epochs: {EPOCHS}  ppo: gamma={PPO_GAMMA} lambda={PPO_LAMBDA} "
      f"eps={PPO_EPS} ql={PPO_QLAMBDA}", flush=True)

hdr = pd.read_csv(CSV, nrows=0).columns
need = {"seed", "decIdx", "screen", "action", "actionType", "c1", "c2", "c3",
        "cand1", "cand2", "cand3", "chosen", "won", "endHp",
        "labelWon", "labelHp"}
missing = need - set(hdr)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")
if "labelWon" not in hdr or "labelHp" not in hdr:
    raise ValueError("Tier-B training requires labelWon,labelHp (strategicgen2 schema)")
opt_cols = ["labelFloor", "labelBootstrap"]
for c in opt_cols:
    if c not in hdr:
        print(f"[train-strategic-ppo] optional column {c} absent; using NaN", flush=True)

# State block = all numeric columns strictly between `chosen` and `won`
# (found by column index; act/floor live inside it, no separate act column).
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
NSTATE = wi - ci - 1
if NSTATE < 1000:
    raise ValueError(f"expected a rich state block between chosen and won, got {NSTATE} columns")
state_cols = list(hdr[ci + 1:wi])

use_cols = sorted(need | set(opt_cols))
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
q_target = (10 * df.labelWon.to_numpy(np.float32) + df.labelHp.to_numpy(np.float32)).astype(np.float32)
q_valid = np.isfinite(q_target)

# Reorder every small array by group id once: batches are contiguous slices.
action_ints, cat = action_ints[order], cat[order]
atype, screen, value = atype[order], screen[order], value[order]
q_target, q_valid = q_target[order], q_valid[order]
chosen = chosen[order]

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

STATE_FILE = OUT + "_ppo_state.bin"
expected = nrows * NSTATE * 2
reused = False
if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) == expected:
    reused = True
    print(f"[train-strategic-ppo] reusing {STATE_FILE} ({expected:,} bytes)", flush=True)
else:
    state_mem = np.memmap(STATE_FILE, dtype=np.float16, mode="w+", shape=(nrows, NSTATE))
    lo = 0
    for chunk in pd.read_csv(CSV, usecols=state_cols, chunksize=CHUNK, dtype=np.float32):
        hi = lo + len(chunk)
        x = np.clip((chunk.to_numpy(np.float64) - mean) * inv, -8, 8).astype(np.float16)
        state_mem[inv_perm[lo:hi]] = x
        lo = hi
    state_mem.flush()
    print(f"[train-strategic-ppo] wrote {STATE_FILE} ({expected:,} bytes)", flush=True)

state_mmap = np.memmap(STATE_FILE, dtype=np.float16, mode="r", shape=(nrows, NSTATE))

# --- Trajectory reconstruction: per seed, groups sorted by decIdx are the run
# sequence; succ links each group to the next group of the same seed (-1 = run
# end).  floor = state column index 2, read from the (z-normalized) state
# file; df = max(0, floor[succ] - floor).  r_term is the terminal reward. ---
grp_seed = grp_vals // 1000000
grp_decidx = grp_vals % 1000000
seq_idx = np.argsort(grp_vals, kind="stable")
succ = np.full(NG, -1, np.int64)
same_seed = grp_seed[seq_idx[:-1]] == grp_seed[seq_idx[1:]]
succ[seq_idx[:-1][same_seed]] = seq_idx[1:][same_seed]
grp_floor = state_mmap[block_start, 2].astype(np.float32)
df_floor = np.zeros(NG, np.float32)
nz = succ >= 0
df_floor[nz] = np.maximum(grp_floor[succ[nz]] - grp_floor[nz], 0.0)
grp_screen = screen[block_start]
r_term = np.zeros(NG, np.float32)
r_term[~nz] = value[block_start[~nz]]
bounds = np.flatnonzero(np.diff(grp_seed[seq_idx]))
seg_starts = np.concatenate(([0], bounds + 1))
seg_ends = np.concatenate((bounds + 1, [NG]))
print(f"trajectories: {len(seg_starts)} seeds, {int((~nz).sum())} terminal groups, "
      f"{int((df_floor > 0).sum())} transitions with floor gain", flush=True)
bad_scr = (grp_screen < 1) | (grp_screen > 8)
if bad_scr.any():
    print(f"[train-strategic-ppo] warning: {int(bad_scr.sum())} groups with screen "
          f"outside 1..8; their V_old is treated as 0", flush=True)


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(NSTATE, 256), nn.LayerNorm(256), nn.GELU(),
                               nn.Dropout(0.2), nn.Linear(256, 128), nn.GELU())
        self.a_bits = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Dropout(0.2),
                                    nn.Linear(32, 16))
        self.a_cat = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Linear(32, 16))
        self.cats = nn.ModuleList([nn.Embedding(512, 4) for _ in range(6)])
        self.atype = nn.Embedding(16, 8)
        self.screen = nn.Embedding(16, 8)
        self.pol = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        # Q(s,a) head on the same (z,b,a,screen) concat as the policy head,
        # trained on Tier-B one-ply labels (10*labelWon + labelHp).
        self.q = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
        # One value head per screen (screens 1..8 -> index 0..7), trained on
        # every group's state (PPO value contract), not just chosen rows.
        self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))
                                   for _ in range(8)])

    def forward(self, x, bits, cat, atype, screen):
        z = self.s(x)
        b = self.a_bits(bits)
        cat_in = torch.cat([self.cats[i](cat[:, i]) for i in range(6)]
                           + [self.atype(atype)], 1)
        a = self.a_cat(cat_in)
        ha = torch.cat((z, b, a, self.screen(screen)), 1)
        logit = self.pol(ha).squeeze(1)
        q = self.q(ha).squeeze(1)
        v = torch.empty(z.shape[0], device=z.device)
        for h in range(8):
            m = (screen == h + 1)
            if m.any():
                v[m] = self.vals[h](z[m]).squeeze(1)
        return logit, v, q


model = Net().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)

AR = np.arange(32, dtype=np.int64)


def fwd_rows(rows):
    """Forward over an arbitrary row set (epoch-permuted train batch).  The
    rows are gathered once per batch from the group-ordered mmap + small
    arrays; ~BATCH*NSTATE*2 bytes per gather."""
    x = torch.from_numpy(state_mmap[rows].copy()).to(DEVICE, torch.float32)
    bits = torch.from_numpy(((action_ints[rows, None] >> AR[None, :]) & 1)
                            .astype(np.float32)).to(DEVICE)
    c = torch.from_numpy(cat[rows]).to(DEVICE, torch.long)
    a = torch.from_numpy(atype[rows]).to(DEVICE, torch.long)
    s = torch.from_numpy(screen[rows]).to(DEVICE, torch.long)
    return model(x, bits, c, a, s)


# --- GAE (per-floor discount, accumulated cumulatively).  delta_t = r_t +
# gamma^df * V_old(succ) - V_old(s_t); A_t = delta_t + (gamma*lambda)^df *
# A_{t+1}, evaluated backward per trajectory segment (recurrence solved as a
# reversed cumulative product/sum: A_work[i] = P_work[i] * cumsum(d/P_work)). ---
def compute_advantages(vold):
    delta = np.zeros(NG, np.float64)
    delta[nz] = r_term[nz] + PPO_GAMMA ** df_floor[nz] * vold[succ[nz]] - vold[nz]
    delta[~nz] = r_term[~nz] - vold[~nz]
    c = (PPO_GAMMA * PPO_LAMBDA) ** df_floor
    adv = np.zeros(NG, np.float64)
    for a, b in zip(seg_starts, seg_ends):
        seg = seq_idx[a:b]
        dw = delta[seg][::-1]
        cw = c[seg][::-1]
        Pw = np.cumprod(cw)
        if Pw.min() <= 0.0 or not np.isfinite(Pw[-1]):
            aw = np.empty(len(seg), np.float64)
            for i in range(len(seg)):
                aw[i] = dw[i] + (cw[i] * aw[i - 1] if i > 0 else 0.0)
            adv[seg] = aw[::-1]
        else:
            adv[seg] = (Pw * np.cumsum(dw / Pw))[::-1]
    return adv, delta


def adv_naive(delta):
    c = (PPO_GAMMA * PPO_LAMBDA) ** df_floor
    adv = np.zeros(NG, np.float64)
    for g in seq_idx[::-1]:
        s = succ[g]
        adv[g] = delta[g] + (c[g] * adv[s] if s >= 0 else 0.0)
    return adv


SNAP = 16384


@torch.no_grad()
def snapshots():
    """Per-epoch frozen snapshots: V_old over ALL group states (first row of
    each group) and the policy's old chosen-row logits, on GPU in chunks."""
    model.eval()
    vold = np.zeros(NG, np.float32)
    for lo in range(0, NG, SNAP):
        hi = min(lo + SNAP, NG)
        rows = block_start[lo:hi]
        z = model.s(torch.from_numpy(state_mmap[rows].copy()).to(DEVICE, torch.float32))
        scr = screen[rows]
        for h in range(8):
            m = np.flatnonzero(scr == h + 1)
            if m.size:
                mm = torch.from_numpy(m).to(DEVICE)
                vold[lo + m] = model.vals[h](z[mm]).squeeze(1).cpu().numpy()
    old_logit = np.full(NG, np.nan, np.float32)
    polg = np.flatnonzero(valid_pol)
    for lo in range(0, len(polg), SNAP):
        hi = min(lo + SNAP, len(polg))
        gids = polg[lo:hi]
        logit, _, _ = fwd_rows(chosen_in_block[gids])
        old_logit[gids] = logit.cpu().numpy()
    return vold, old_logit


def train_batch_loss(gs):
    """PPO-clip policy loss (valid chosen rows) + per-screen value MSE on all
    group states + Q-MSE; batches are consecutive groups, gathered once."""
    sizes_b = sizes[gs]
    rows = np.concatenate([np.arange(block_start[g], block_start[g] + sizes[g])
                           for g in gs])
    logit, val, q = fwd_rows(rows)
    gstart = np.concatenate(([0], np.cumsum(sizes_b[:-1])))
    # Policy: clipped surrogate on the chosen row's logit ratio; the old
    # logits are frozen once per epoch (snapshots()).
    ok = valid_pol[gs]
    if ok.any():
        cpos = torch.from_numpy(gstart[ok] + chosen_off[gs][ok]).to(DEVICE)
        # Clamp the ratio: exp() can overflow float32 on large logit deltas,
        # and an Inf ratio * negative advantage would make the loss Inf.
        ratio = torch.clamp(
            (logit[cpos] - torch.from_numpy(old_logit[gs][ok]).to(DEVICE)).exp(),
            0.0, 1e2)
        ac = torch.from_numpy(adv[gs][ok]).to(DEVICE)
        clipped = torch.clamp(ratio, 1.0 - PPO_EPS, 1.0 + PPO_EPS)
        pol_loss = -(torch.minimum(ratio * ac, clipped * ac)).mean()
    else:
        pol_loss = torch.zeros((), device=DEVICE)
    # Value: per-screen MSE of V(s_t) (first row of each group) vs the GAE
    # target A_t + V_old(s_t), one mean per screen like V3.
    vok = (grp_screen[gs] >= 1) & (grp_screen[gs] <= 8)
    if vok.any():
        vpred = val[gstart[vok]]
        scr = grp_screen[gs][vok]
        tl = torch.from_numpy(v_target[gs][vok]).to(DEVICE)
        vlosses = []
        for h in range(8):
            vv = (scr == h + 1)
            if vv.any():
                vlosses.append(nn.functional.mse_loss(vpred[vv], tl[vv]))
        val_loss = torch.stack(vlosses).mean() if vlosses else torch.zeros((), device=DEVICE)
    else:
        val_loss = torch.zeros((), device=DEVICE)
    # Q MSE on all Tier-B labeled rows in the batch.
    qm = q_valid[rows]
    if qm.any():
        ql = torch.from_numpy(q_target[rows]).to(DEVICE)[qm]
        q_loss = nn.functional.mse_loss(q[qm], ql)
    else:
        q_loss = torch.zeros((), device=DEVICE)
    loss = pol_loss + 0.5 * val_loss + PPO_QLAMBDA * q_loss
    if not torch.isfinite(loss):
        # A NaN/Inf batch contributes nothing; keep requires_grad=True so the
        # backward pass below never hits a constant tensor.
        loss = torch.zeros((), device=DEVICE, requires_grad=True)
    return loss, float(pol_loss.detach()), float(val_loss.detach()), float(q_loss.detach())


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
va_qtarget = q_target[va_perm]
va_qvalid = q_valid[va_perm]


@torch.no_grad()
def evaluate():
    """Held-out metrics over the fixed evaluation permutation EV; ranking
    metrics need groups with >= 2 rows."""
    full_logit = np.empty(len(va_perm), np.float32)
    full_val = np.empty(len(va_perm), np.float32)
    full_q = np.empty(len(va_perm), np.float32)
    for lo in range(0, len(va_perm), BATCH):
        hi = min(lo + BATCH, len(va_perm))
        l, v, q = fwd_rows(va_perm[lo:hi])
        full_logit[lo:hi] = l.cpu().numpy()
        full_val[lo:hi] = v.cpu().numpy()
        full_q[lo:hi] = q.cpu().numpy()
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
    qv = va_qvalid
    qmae = float(np.mean(np.abs(full_q[qv] - va_qtarget[qv]))) if qv.any() else 0.0
    qrmse = float(np.sqrt(np.mean((full_q[qv] - va_qtarget[qv]) ** 2))) if qv.any() else 0.0
    q_screen = {}
    for h in range(8):
        sm = (scr_all == h + 1) & qv
        if sm.sum() >= 10:
            q_screen[h + 1] = {
                "mae": float(np.mean(np.abs(full_q[sm] - va_qtarget[sm]))),
                "n": int(sm.sum()),
            }
    top1 = 0
    qtop1 = 0
    margin = 0.0
    ce = 0.0
    ntop = 0
    nqtop = 0
    for g in va_groups:
        sz = sizes[g]
        if sz < 2:
            continue
        lo = va_start[g]
        p = full_logit[lo:lo + sz]
        c = int(chosen_off[g])
        if valid_pol[g]:
            srt = np.sort(p)[::-1]
            top1 += int(np.argmax(p) == c)
            margin += srt[0] - srt[1]
            lse = p.max() + np.log(np.exp(p - p.max()).sum())
            ce += lse - p[c]
            ntop += 1
        qg = qv[lo:lo + sz]
        if qg.sum() >= 2:
            qoracle = np.argmax(va_qtarget[lo:lo + sz])
            qpred = np.argmax(full_q[lo:lo + sz])
            qtop1 += int(qoracle == qpred)
            nqtop += 1
    return {"groups": ntop,
            "policy_top1": top1 / max(1, ntop),
            "margin": margin / max(1, ntop),
            "value_mae": vmae,
            "value_rmse": float(np.sqrt(vmse)),
            "value_n": int(ch.sum()),
            "value_mae_screen": per_screen,
            "q_top1": qtop1 / max(1, nqtop),
            "q_top1_n": nqtop,
            "q_mae": qmae,
            "q_rmse": qrmse,
            "q_n": int(qv.sum()),
            "q_mae_screen": q_screen,
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
tr_gs = np.flatnonzero(tr_mask)
for epoch in range(1, EPOCHS + 1):
    vold, old_logit = snapshots()
    adv64, delta = compute_advantages(vold)
    if epoch == 1:
        nv = adv_naive(delta)
        assert np.allclose(adv64, nv, atol=1e-6), "GAE vectorization mismatch"
        print(f"GAE verified vs naive backward pass: mean={adv64.mean():.4f} "
              f"std={adv64.std():.4f} min={adv64.min():.4f} max={adv64.max():.4f}",
              flush=True)
    assert np.isfinite(adv64).all(), "PPO advantages are not finite"
    assert np.isfinite(delta).all(), "PPO GAE deltas are not finite"
    adv = adv64.astype(np.float32)
    v_target = (adv + vold).astype(np.float32)
    assert np.isfinite(v_target).all(), "PPO value targets are not finite"
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
    p_losses, v_losses, q_losses = [], [], []
    for gs in batches:
        loss, pl, vl, ql = train_batch_loss(gs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)
        opt.step()
        p_losses.append(pl)
        v_losses.append(vl)
        q_losses.append(ql)
    model.eval()
    em = evaluate()
    if em["val_pol_ce"] < best_ce:
        best_ce = em["val_pol_ce"]
        best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if epoch == 1 or epoch % 10 == 0 or epoch == EPOCHS:
        print(f"epoch={epoch:03d} train_pol={np.mean(p_losses):.4f} "
              f"train_val={np.mean(v_losses):.4f} train_q={np.mean(q_losses):.4f} "
              f"val_pol_ce={em['val_pol_ce']:.4f} "
              f"metrics={to_py(em)}", flush=True)

model.load_state_dict(best_state)
model.eval()
eval_metrics = to_py(evaluate())
print(f"\nbest held-out (val_pol_ce={best_ce:.4f}): {eval_metrics}", flush=True)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.cpu().state_dict(), "mean": mean, "inv": inv,
            "metrics": eval_metrics, "nrows": int(nrows), "features": NSTATE,
            "ppo": {"gamma": PPO_GAMMA, "lambda": PPO_LAMBDA, "eps": PPO_EPS}},
           OUT + ".pt")
with open(OUT + "_metrics.json", "w") as f:
    json.dump(eval_metrics, f, indent=2)
print(f"wrote {OUT}.pt, {OUT}_metrics.json", flush=True)
