#!/usr/bin/env python3
"""Train a Phase-5 run-level strategic model from `strategicgen` CSV rows.

Each row is one legal run-level action at a decision: the rich state vector,
the packed GameAction bits, structured candidate fields (c1..c3, cand1..c3),
and a `chosen` flag; only chosen rows carry the terminal labels (won, endHp).
The network learns a policy (softmax over each decision group's legal actions,
supervised by the chosen row) and one run-value head per screen (10*won + endHp,
trained on that screen's chosen rows), jointly with group-CE + per-screen
value-MSE. Held-out decisions are scored by per-group policy top-1, per-screen
value MAE/RMSE, and logit margin.
"""
import json, os, sys

import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_200.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_strategic"
EPOCHS = int(os.environ.get("STRAT_EPOCHS", "60"))
BATCH = int(os.environ.get("STRAT_BATCH", "4096"))   # target ROWS per batch (whole groups)
LR = float(os.environ.get("STRAT_LR", "2e-3"))
VLAMBDA = float(os.environ.get("STRAT_VLAMBDA", "0.5"))
CLIP = float(os.environ.get("STRAT_CLIP", "1.0"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
# Default to CUDA when available; STRAT_DEVICE only overrides (e.g. "cpu").
DEVICE = os.environ.get("STRAT_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(THREADS)
torch.manual_seed(0)
print(f"device: {DEVICE}", flush=True)

df = pd.read_csv(CSV)
need = {"seed", "decIdx", "screen", "action", "actionType", "c1", "c2", "c3",
        "cand1", "cand2", "cand3", "chosen", "won", "endHp"}
missing = need - set(df.columns)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")

# State block = all numeric columns strictly between `chosen` and `won`
# (found by column index; act/floor live inside it, no separate act column).
cols = list(df.columns)
ci, wi = cols.index("chosen"), cols.index("won")
NSTATE = wi - ci - 1
if NSTATE < 1000:
    raise ValueError(f"expected a rich state block between chosen and won, got {NSTATE} columns")
state = df.iloc[:, ci + 1:wi].to_numpy(np.float32)

groups = df.seed.to_numpy(np.int64) * 1000000 + df.decIdx.to_numpy(np.int64)
grp_vals, grp_ids = np.unique(groups, return_inverse=True)
NG = len(grp_vals)
rows_by_group = [np.flatnonzero(grp_ids == g) for g in range(NG)]

chosen = df.chosen.to_numpy(np.int64) == 1
one_chosen = np.bincount(grp_ids[chosen], minlength=NG) == 1
chosen_row_idx = np.full(NG, -1, np.int64)
cp = np.flatnonzero(chosen)
chosen_row_idx[grp_ids[cp]] = cp
act_col = df.action.to_numpy(np.int64)
chosen_act = np.where(chosen_row_idx >= 0, act_col[np.maximum(chosen_row_idx, 0)], -2)
valid_pol = one_chosen & (chosen_act != -1)

# Reorder all rows by group once, so every batch (a consecutive run of groups)
# is a single CONTIGUOUS slice of the input tensors: no per-batch gather over
# the 549MB state matrix, no np.concatenate. group g occupies
# [block_start[g], block_start[g]+sizes[g]) in reordered space.
sizes = np.array([len(r) for r in rows_by_group], np.int64)
block_start = np.concatenate(([0], np.cumsum(sizes[:-1])))
grp_of_row = np.repeat(np.arange(NG), sizes)
chosen_in_block = np.full(NG, -1, np.int64)
for g in range(NG):
    r = chosen_row_idx[g]
    if r >= 0:
        chosen_in_block[g] = block_start[g] + int(np.searchsorted(rows_by_group[g], r))

print(f"{len(df):,} rows, {df.seed.nunique()} seeds, {NG} decisions, "
      f"{int(one_chosen.sum())} groups with exactly one chosen row "
      f"({int(valid_pol.sum())} with a valid policy action)", flush=True)

# Grouped 80/20 split, shuffling decision groups.
rng = np.random.default_rng(0)
order = rng.permutation(NG)
cut = max(1, int(0.8 * NG))
tr_mask = np.zeros(NG, bool)
tr_mask[order[:cut]] = True
va_groups = order[cut:]
if len(va_groups) == 0:
    raise ValueError("need held-out decision groups")
tr_rows, va_rows = tr_mask[grp_ids], ~tr_mask[grp_ids]
print(f"train: {int(tr_rows.sum()):,} rows / {int(tr_mask.sum()):,} groups, "
      f"val: {int(va_rows.sum()):,} rows / {len(va_groups):,} groups", flush=True)

# Standardize on train rows only.
mean = state[tr_rows].mean(0).astype(np.float32)
inv = 1 / np.maximum(state[tr_rows].std(0).astype(np.float32), 1e-6)
state = np.clip((state - mean) * inv, -8, 8)


def parse_bits(x):
    if isinstance(x, str) and x.startswith("bits="):
        return int(x.split("=")[1])
    return int(x)


action_ints = np.array([parse_bits(x) for x in df.action], np.int64)
bits = np.asarray([[(int(a) >> i) & 1 for i in range(32)] for a in action_ints], np.float32)
cat = np.stack([np.clip(df[c].to_numpy(np.int64) + 1, 0, 511)
                for c in ("c1", "c2", "c3", "cand1", "cand2", "cand3")], 1)
atype = np.clip(df.actionType.to_numpy(np.int64) + 1, 0, 15)
screen = np.clip(df.screen.to_numpy(np.int64), 0, 15)
value = (10 * df.won.to_numpy(np.float32) + df.endHp.to_numpy(np.float32)).astype(np.float32)

# Reorder every row array by group id (see block_start above): batches become
# contiguous slices and no per-batch gather over the state matrix is needed.
ro = np.concatenate(rows_by_group)
state, bits = state[ro], bits[ro]
cat, atype, screen = cat[ro], atype[ro], screen[ro]
value, chosen = value[ro], chosen[ro]


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
        # One value head per screen (screens 1..8 -> index 0..7), trained on
        # that screen's chosen rows only; the shared encoder is unchanged.
        self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))
                                   for _ in range(8)])

    def forward(self, x, bits, cat, atype, screen):
        z = self.s(x)
        b = self.a_bits(bits)
        cat_in = torch.cat([self.cats[i](cat[:, i]) for i in range(6)]
                           + [self.atype(atype)], 1)
        a = self.a_cat(cat_in)
        logit = self.pol(torch.cat((z, b, a, self.screen(screen)), 1)).squeeze(1)
        v = torch.empty(z.shape[0], device=z.device)
        for h in range(8):
            m = (screen == h + 1)
            if m.any():
                v[m] = self.vals[h](z[m]).squeeze(1)
        return logit, v


model = Net().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)

T = [torch.from_numpy(x) for x in (state, bits, cat, atype, screen, value)]
# chosen offset within its own group's block (reordered space).
chosen_off = np.where(chosen_in_block >= 0, chosen_in_block - block_start, -1)

# Fixed evaluation permutation: val-group blocks packed in va_groups order.
va_perm = np.concatenate([np.arange(block_start[g], block_start[g] + sizes[g])
                          for g in va_groups])
EV = [t[va_perm] for t in T]
va_start = np.full(NG, -1, np.int64)
pos = 0
for g in va_groups:
    va_start[g] = pos
    pos += sizes[g]
va_chosen = chosen[va_perm]
va_target = T[5][va_perm]
va_screen = T[4][va_perm]


def fwd_ev(lo, hi):
    x = (EV[0][lo:hi].to(DEVICE), EV[1][lo:hi].to(DEVICE), EV[2][lo:hi].to(DEVICE),
         EV[3][lo:hi].to(DEVICE), EV[4][lo:hi].to(DEVICE))
    return model(*x)


def batch_loss(gs, P, ch_perm, target_perm, pos_in_perm, chosen_in_perm):
    """Group-CE + value-MSE over all rows of the given CONSECUTIVE groups
    (contiguous slice of the epoch-permuted tensors P)."""
    lo = pos_in_perm[gs[0]]
    hi = pos_in_perm[gs[-1]] + sizes[gs[-1]]
    sizes_b = sizes[gs]
    logit, val = fwd_slice(P, lo, hi)
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
        cpos = chosen_in_perm[gs] - lo
        pc = logit[cpos] - lse[loc[cpos]]
        pol_loss = -pc[torch.from_numpy(ok)].mean()
    else:
        pol_loss = torch.zeros((), device=DEVICE)
    # Value MSE on chosen rows only (any group), one mean per screen.
    m = ch_perm[lo:hi]
    if m.any():
        scr = P[4][lo:hi][m]
        tl = target_perm[lo:hi].to(DEVICE)[m]
        vv = val[m]
        vlosses = []
        for h in range(8):
            mm = (scr == h + 1)
            if mm.any():
                vlosses.append(nn.functional.mse_loss(vv[mm], tl[mm]))
        val_loss = torch.stack(vlosses).mean() if vlosses else torch.zeros((), device=DEVICE)
    else:
        val_loss = torch.zeros((), device=DEVICE)
    loss = pol_loss + VLAMBDA * val_loss
    if not torch.isfinite(loss):
        loss = torch.zeros((), device=DEVICE)
    return loss, float(pol_loss.detach()), float(val_loss.detach())


def fwd_slice(P, lo, hi):
    x = (P[0][lo:hi].to(DEVICE), P[1][lo:hi].to(DEVICE), P[2][lo:hi].to(DEVICE),
         P[3][lo:hi].to(DEVICE), P[4][lo:hi].to(DEVICE))
    return model(*x)


@torch.no_grad()
def evaluate():
    """Held-out metrics over the fixed evaluation permutation EV; ranking
    metrics need groups with >= 2 rows."""
    full_logit = np.empty(len(va_perm), np.float32)
    full_val = np.empty(len(va_perm), np.float32)
    for lo in range(0, len(va_perm), BATCH):
        hi = min(lo + BATCH, len(va_perm))
        l, v = fwd_ev(lo, hi)
        full_logit[lo:hi] = l.cpu().numpy()
        full_val[lo:hi] = v.cpu().numpy()
    vtarget = va_target.numpy()
    ch = va_chosen
    vmse = float(np.mean((full_val[ch] - vtarget[ch]) ** 2))
    vmae = float(np.mean(np.abs(full_val[ch] - vtarget[ch])))
    per_screen = {}
    scr_all = va_screen.numpy()
    for h in range(8):
        sm = (scr_all == h + 1) & ch
        if sm.sum() >= 10:
            per_screen[h + 1] = {
                "mae": float(np.mean(np.abs(full_val[sm] - vtarget[sm]))),
                "rmse": float(np.sqrt(np.mean((full_val[sm] - vtarget[sm]) ** 2))),
                "n": int(sm.sum()),
            }
    top1 = 0
    margin = 0.0
    ce = 0.0
    ntop = 0
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
    return {"groups": ntop,
            "policy_top1": top1 / max(1, ntop),
            "margin": margin / max(1, ntop),
            "value_mae": vmae,
            "value_rmse": float(np.sqrt(vmse)),
            "value_n": int(ch.sum()),
            "value_mae_screen": per_screen,
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
pos_in_perm = np.empty(NG, np.int64)
chosen_in_perm = np.empty(NG, np.int64)
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = rng.permutation(tr_gs)
    # One gather per epoch: pack the epoch's group permutation contiguously so
    # every batch is a plain slice (no per-batch gather over the state matrix).
    n_tr = int(sizes[tr_gs].sum())
    perm = np.empty(n_tr, np.int64)
    pos = 0
    for g in order:
        n = sizes[g]
        perm[pos:pos + n] = block_start[g] + np.arange(n)
        pos_in_perm[g] = pos
        chosen_in_perm[g] = pos + chosen_off[g]
        pos += n
    P = [t[perm] for t in T]
    ch_perm = chosen[perm]
    target_perm = T[5][perm]
    batches = []
    cur, nrows = [], 0
    for g in order:
        cur.append(g)
        nrows += sizes[g]
        if nrows >= BATCH:
            batches.append(np.asarray(cur))
            cur, nrows = [], 0
    if cur:
        batches.append(np.asarray(cur))
    p_losses, v_losses = [], []
    for gs in batches:
        loss, pl, vl = batch_loss(gs, P, ch_perm, target_perm, pos_in_perm, chosen_in_perm)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)
        opt.step()
        p_losses.append(pl)
        v_losses.append(vl)
    model.eval()
    em = evaluate()
    if em["val_pol_ce"] < best_ce:
        best_ce = em["val_pol_ce"]
        best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if epoch == 1 or epoch % 10 == 0 or epoch == EPOCHS:
        print(f"epoch={epoch:03d} train_pol={np.mean(p_losses):.4f} "
              f"train_val={np.mean(v_losses):.4f} val_pol_ce={em['val_pol_ce']:.4f} "
              f"metrics={to_py(em)}", flush=True)

model.load_state_dict(best_state)
model.eval()
eval_metrics = to_py(evaluate())
print(f"\nbest held-out (val_pol_ce={best_ce:.4f}): {eval_metrics}", flush=True)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.cpu().state_dict(), "mean": mean, "inv": inv,
            "metrics": eval_metrics, "features": NSTATE}, OUT + ".pt")
with open(OUT + "_metrics.json", "w") as f:
    json.dump(eval_metrics, f, indent=2)
print(f"wrote {OUT}.pt, {OUT}_metrics.json", flush=True)
