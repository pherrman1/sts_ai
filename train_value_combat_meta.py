#!/usr/bin/env python3
"""Reptile meta-learning for a small MLP combat value model (tail encounters).

Goal: an initialization theta such that a few SGD steps on an encounter's own
rows yield a good per-encounter combat value model. Tail encounters (rare
events, Act 4, event fights) have too few rows for pooled fine-tuning; a
meta-learned initialization is the "learning how to learn" alternative.

Recipe:
  1. Load the combat CSV; canonical features; fight key seed*1000+fightIdx.
  2. Fight-group split: 10% of fights (by a seed-stable hash) are meta-val,
     the rest meta-train. No fight straddles the split.
  3. Standardize with x_mean/x_invstd (and y_mean/y_scale) from meta-train
     fights only. Inference applies the identical standardization (the C++
     combat_mlp_v1 dense path normalizes at predict time), so no clipping is
     applied — a train/inference mismatch would fail the vnettest parity check.
  4. Reptile outer loop: sample B encounters per iteration; for each, clone
     the meta weights and run K SGD steps on that encounter's rows to get
     theta'_e; then theta <- theta + eps * (theta'_e - theta) / B.
  5. Offline adaptation (no online gradient descent at inference): for each
     tail encounter (meta-train rows <= META_TAIL_MAX_ROWS and >=
     META_MIN_ADAPT_ROWS), fine-tune from meta-theta for META_ADAPT_STEPS and
     store the weight delta vs the base weights.
  6. Export combat_mlp_meta_v1: base MLP (dense layout, raw weights +
     x_mean/x_invstd) followed by the per-encounter delta table. The C++
     loader reconstructs per-encounter weights as base + delta and dispatches
     predict(bc) on the encounter.

Architecture: NFEAT -> H1 -> H2 -> 1 with ReLU. NOTE: the native
combat_mlp_v1 C++ path is ReLU, so ReLU is required here; a GELU-trained
export would silently mispredict at inference (deviation from the plan's
"GELU" wording, see docs/knowledge-base/architecture/training-and-inference.md).

Usage: python3 train_value_combat_meta.py [csv] [out.txt]

Environment:
  META_H1/META_H2            hidden sizes (default 128/64)
  META_ITERS                 outer-loop iterations (default 40)
  META_B                     encounters sampled per iteration (default 8)
  META_K                     inner SGD steps per encounter (default 5)
  META_LR_INNER              inner-loop learning rate (default 0.01)
  META_LR_OUTER              Reptile step size eps (default 0.5)
  META_BATCH                 inner minibatch (default 256)
  META_MAX_ROWS_PER_ENC      cap on rows used per encounter (default 2048)
  META_MIN_TRAIN_ROWS        meta-train requires >= this many rows (default 64)
  META_TAIL_MAX_ROWS         adapt encounters with <= this many rows (default 3000)
  META_MIN_ADAPT_ROWS        adapt requires >= this many rows (default 8)
  META_ADAPT_STEPS           offline adaptation SGD steps (default 40)
  META_PATIENCE              early stop after this many iters w/o val gain (default 8)
  META_SAMPLE_MOD            keep 1/N of fights (row sampling, default 1)
  META_DEVICE                device override ("cuda"/"cpu"; default cuda if present)
"""
import os, sys, gc, copy
import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat_honest.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_meta.txt"
VAL = OUT + "_val.csv"
WIN_BONUS = float(os.environ.get("META_WIN_BONUS", "50"))

H1 = int(os.environ.get("META_H1", "128"))
H2 = int(os.environ.get("META_H2", "64"))
ITERS = int(os.environ.get("META_ITERS", "40"))
B = int(os.environ.get("META_B", "8"))
K = int(os.environ.get("META_K", "5"))
LR_INNER = float(os.environ.get("META_LR_INNER", "0.01"))
LR_OUTER = float(os.environ.get("META_LR_OUTER", "0.5"))
BATCH = int(os.environ.get("META_BATCH", "256"))
MAX_ROWS = int(os.environ.get("META_MAX_ROWS_PER_ENC", "2048"))
MIN_TRAIN_ROWS = int(os.environ.get("META_MIN_TRAIN_ROWS", "64"))
TAIL_MAX_ROWS = int(os.environ.get("META_TAIL_MAX_ROWS", "3000"))
MIN_ADAPT_ROWS = int(os.environ.get("META_MIN_ADAPT_ROWS", "8"))
ADAPT_STEPS = int(os.environ.get("META_ADAPT_STEPS", "40"))
PATIENCE = int(os.environ.get("META_PATIENCE", "8"))
SAMPLE_MOD = max(1, int(os.environ.get("META_SAMPLE_MOD", "1")))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))

DEVICE = os.environ.get("META_DEVICE", "")
if not DEVICE:
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)}", flush=True)
else:
    DEVICE = "cpu"
torch.set_num_threads(THREADS)
torch.manual_seed(0)
rng = np.random.default_rng(0)

# MonsterEncounter enum name -> int (mirror of monsterEncounterEnumNames).
_ENUM_NAMES = ["INVALID","CULTIST","JAW_WORM","TWO_LOUSE","SMALL_SLIMES",
"BLUE_SLAVER","GREMLIN_GANG","LOOTER","LARGE_SLIME","LOTS_OF_SLIMES",
"EXORDIUM_THUGS","EXORDIUM_WILDLIFE","RED_SLAVER","THREE_LOUSE",
"TWO_FUNGI_BEASTS","GREMLIN_NOB","LAGAVULIN","THREE_SENTRIES","SLIME_BOSS",
"THE_GUARDIAN","HEXAGHOST","SPHERIC_GUARDIAN","CHOSEN","SHELL_PARASITE",
"THREE_BYRDS","TWO_THIEVES","CHOSEN_AND_BYRDS","SENTRY_AND_SPHERE",
"SNAKE_PLANT","SNECKO","CENTURION_AND_HEALER","CULTIST_AND_CHOSEN",
"THREE_CULTIST","SHELLED_PARASITE_AND_FUNGI","GREMLIN_LEADER","SLAVERS",
"BOOK_OF_STABBING","AUTOMATON","COLLECTOR","CHAMP","THREE_DARKLINGS",
"ORB_WALKER","THREE_SHAPES","SPIRE_GROWTH","TRANSIENT","FOUR_SHAPES","MAW",
"SPHERE_AND_TWO_SHAPES","JAW_WORM_HORDE","WRITHING_MASS","GIANT_HEAD",
"NEMESIS","REPTOMANCER","AWAKENED_ONE","TIME_EATER","DONU_AND_DECA",
"SHIELD_AND_SPEAR","THE_HEART","LAGAVULIN_EVENT","COLOSSEUM_EVENT_SLAVERS",
"COLOSSEUM_EVENT_NOBS","MASKED_BANDITS_EVENT","MUSHROOMS_EVENT",
"MYSTERIOUS_SPHERE_EVENT"]
ENUM_INT = {n: i for i, n in enumerate(_ENUM_NAMES)}

def mix64(x):
    x = np.asarray(x, dtype=np.uint64)
    x ^= x >> np.uint64(30); x *= np.uint64(0xbf58476d1ce4e5b9)
    x ^= x >> np.uint64(27); x *= np.uint64(0x94d049bb133111eb)
    return x ^ (x >> np.uint64(31))

# ---- load + standardize ----------------------------------------------------
header = list(pd.read_csv(CSV, nrows=0).columns)
canonical = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")]
NFEAT = len(canonical)
print(f"{NFEAT} canonical features; loading {CSV} ...", flush=True)

dtypes = {c: np.float32 for c in header}
dtypes["seed"] = np.int32; dtypes["fightIdx"] = np.int16
dtypes["encounter"] = np.int16; dtypes["turn"] = np.int16

parts_x, parts_y, parts_g, parts_e = [], [], [], []
seen = kept = 0
CHUNK = 10000
for ci, df in enumerate(pd.read_csv(CSV, dtype=dtypes, chunksize=CHUNK)):
    seed = df["seed"].to_numpy(np.uint64)
    fight = df["fightIdx"].to_numpy(np.uint64)
    group = seed * np.uint64(1000) + fight
    keep = (mix64(group + np.uint64(0x9e3779b97f4a7c15)) % np.uint64(SAMPLE_MOD)) == 0
    seen += len(df)
    if keep.any():
        p = df.loc[keep]
        won = p["won"].to_numpy(np.float32)
        maxhp = np.maximum(p["maxHp"].to_numpy(np.float32), 1.0)
        hpfrac = np.clip(p["endHp"].to_numpy(np.float32) / maxhp, 0, 1)
        y = won * (WIN_BONUS + hpfrac * maxhp)      # utility target, same as the MLP trainer
        parts_x.append(p[canonical].to_numpy(np.float32))
        parts_y.append(y)
        parts_g.append(group[keep])
        parts_e.append(p["encounter"].to_numpy(np.int16))
        kept += int(keep.sum())
X = np.concatenate(parts_x); Y = np.concatenate(parts_y)
Group = np.concatenate(parts_g); Enc = np.concatenate(parts_e)
del parts_x, parts_y, parts_g, parts_e; gc.collect()
print(f"loaded {len(X):,} rows (seen {seen:,}, sample 1/{SAMPLE_MOD})", flush=True)

is_val = (mix64(Group + np.uint64(0xd1b54a32d192ed03)) % np.uint64(10)) == 0
tr = np.flatnonzero(~is_val); va = np.flatnonzero(is_val)
print(f"meta-train fights {len(np.unique(Group[tr])):,}  meta-val fights "
      f"{len(np.unique(Group[va])):,}", flush=True)

x_mean = X[tr].mean(0).astype(np.float32)
x_invstd = 1 / np.maximum(X[tr].std(0).astype(np.float32), 1e-6)
Xn = ((X - x_mean) * x_invstd).astype(np.float32)      # no clip: matches C++ inference
Y_mean = float(Y[tr].mean())
Y_scale = max(float(Y[tr].std()), 1.0)
Yn = ((Y - Y_mean) / Y_scale).astype(np.float32)
del X, Y; gc.collect()
print(f"standardization from meta-train only: x_mean/x_invstd, "
      f"y_mean={Y_mean:.1f} y_scale={Y_scale:.1f}", flush=True)

# ---- model -----------------------------------------------------------------
class FlatMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(NFEAT, H1), nn.ReLU(),
            nn.Linear(H1, H2), nn.ReLU(),
            nn.Linear(H2, 1),
        )
    def forward(self, x):
        return self.net(x).squeeze(1)

model = FlatMLP().to(DEVICE)
n_params = sum(p.numel() for p in model.parameters())
print(f"MLP {NFEAT}x{H1}x{H2}x1 ({n_params:,} params) on {DEVICE}", flush=True)

TX = torch.from_numpy(Xn); TY = torch.from_numpy(Yn)
del Xn, Yn; gc.collect()

# Row indices per encounter (meta-train fights only).
tr_enc = Enc[tr]
enc_rows = {}
for e in np.unique(tr_enc):
    idx = tr[np.flatnonzero(tr_enc == e)]
    if len(idx) >= MIN_TRAIN_ROWS:
        enc_rows[int(e)] = idx
print(f"meta-train encounters: {len(enc_rows)} (of {len(np.unique(Enc))} present; "
      f"need >= {MIN_TRAIN_ROWS} rows)", flush=True)

def batch_loss(m, ids):
    ids_t = torch.from_numpy(ids)
    pred = m(TX[ids_t].to(DEVICE))
    target = TY[ids_t].to(DEVICE)
    return nn.functional.mse_loss(pred, target)

def inner_steps(m, rows, steps):
    opt = torch.optim.SGD(m.parameters(), lr=LR_INNER)
    for _ in range(steps):
        ids = rows[rng.integers(0, len(rows), size=min(BATCH, len(rows)))]
        loss = batch_loss(m, ids)
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
    return m

@torch.no_grad()
def val_rmse():
    model.eval()
    sample = va[rng.choice(len(va), size=min(20000, len(va)), replace=False)]
    preds = []
    for lo in range(0, len(sample), BATCH):
        preds.append(model(TX[torch.from_numpy(sample[lo:lo+BATCH])].to(DEVICE)).cpu())
    pred = torch.cat(preds).numpy()
    return float(np.sqrt(np.mean((pred * Y_scale + Y_mean - (TY[sample].numpy() * Y_scale + Y_mean)) ** 2)))

# ---- Reptile outer loop ----------------------------------------------------
best_state = None; best_rmse = float("inf"); stale = 0
enc_list = sorted(enc_rows)
print(f"reptile: {ITERS} iterations, B={B}, K={K}, eps={LR_OUTER}, "
      f"lr_inner={LR_INNER}, patience={PATIENCE}", flush=True)
for it in range(1, ITERS + 1):
    chosen = rng.choice(enc_list, size=min(B, len(enc_list)), replace=False)
    deltas = None
    for e in chosen:
        rows = enc_rows[e]
        if len(rows) > MAX_ROWS:
            rows = rows[rng.choice(len(rows), size=MAX_ROWS, replace=False)]
        m = copy.deepcopy(model)
        inner_steps(m, rows, K)
        with torch.no_grad():
            d = [m.state_dict()[k].to("cpu") - model.state_dict()[k].to("cpu")
                 for k in model.state_dict()]
        if deltas is None:
            deltas = d
        else:
            deltas = [a + b for a, b in zip(deltas, d)]
    with torch.no_grad():
        for p, delta in zip(model.parameters(), deltas):
            p += (LR_OUTER / len(chosen)) * delta.to(p.device)
    rmse = val_rmse()
    if it == 1 or it % 5 == 0 or rmse < best_rmse:
        print(f"iter {it:3d} meta-val RMSE {rmse:7.3f}", flush=True)
    if rmse < best_rmse - 1e-3:
        best_rmse = rmse; best_state = copy.deepcopy(model.state_dict()); stale = 0
    else:
        stale += 1
        if stale >= PATIENCE:
            print(f"early stop at iter {it} (patience {PATIENCE})", flush=True)
            break
if best_state is None:
    best_state = copy.deepcopy(model.state_dict())
model.load_state_dict(best_state)
model = model.cpu()
print(f"meta-training done: best meta-val RMSE {best_rmse:.3f}", flush=True)

# ---- offline adaptation for tail encounters --------------------------------
def weights_of(sd):
    return [sd["net.0.weight"], sd["net.0.bias"], sd["net.2.weight"],
            sd["net.2.bias"], sd["net.4.weight"], sd["net.4.bias"]]

base_sd = copy.deepcopy(model.state_dict())
deltas = {}
tail = [e for e, rows in enc_rows.items()
        if len(rows) <= TAIL_MAX_ROWS and len(rows) >= MIN_ADAPT_ROWS]
tail.sort()
print(f"adapting {len(tail)} tail encounters (rows <= {TAIL_MAX_ROWS}): "
      f"{[(_ENUM_NAMES[e], len(enc_rows[e])) for e in tail]}", flush=True)
for e in tail:
    rows = enc_rows[e]
    if len(rows) > MAX_ROWS:
        rows = rows[rng.choice(len(rows), size=MAX_ROWS, replace=False)]
    m = copy.deepcopy(model)
    inner_steps(m, rows, ADAPT_STEPS)
    adapted_sd = m.state_dict()
    dw = [w - b for w, b in zip(weights_of(adapted_sd), weights_of(base_sd))]
    deltas[e] = dw
    print(f"  {_ENUM_NAMES[e]:<24s} rows {len(rows):5d} -> delta L2 "
          f"{float(np.sqrt(sum(float((d.numpy() ** 2).sum()) for d in dw))):.4f}", flush=True)

# ---- export combat_mlp_meta_v1 ---------------------------------------------
def write_vec(f, token, arr):
    f.write(token)
    for v in np.asarray(arr, np.float32).ravel(): f.write(f" {float(v):.9g}")
    f.write("\n")

sd = base_sd
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w") as f:
    f.write("combat_mlp_meta_v1\n")
    f.write(f"nfeat {NFEAT}\n")
    for name in canonical: f.write(f"feat {name}\n")
    write_vec(f, "x_mean", x_mean)
    write_vec(f, "x_invstd", x_invstd)
    write_vec(f, "y_mean", [Y_mean])
    write_vec(f, "y_scale", [Y_scale])
    f.write(f"h1 {H1}\n")
    write_vec(f, "w1", sd["net.0.weight"])
    write_vec(f, "b1", sd["net.0.bias"])
    f.write(f"h2 {H2}\n")
    write_vec(f, "w2", sd["net.2.weight"])
    write_vec(f, "b2", sd["net.2.bias"])
    write_vec(f, "w3", sd["net.4.weight"].ravel())
    write_vec(f, "b3", [float(sd["net.4.bias"].item())])
    f.write(f"n_encounter_deltas {len(deltas)}\n")
    for e in sorted(deltas):
        f.write(f"encounter {_ENUM_NAMES[e]}\n")
        dw1, db1, dw2, db2, dw3, db3 = deltas[e]
        write_vec(f, "dw1", dw1)
        write_vec(f, "db1", db1)
        write_vec(f, "dw2", dw2)
        write_vec(f, "db2", db2)
        write_vec(f, "dw3", dw3.ravel())
        write_vec(f, "db3", [float(db3.item())])
print(f"wrote {OUT} ({len(deltas)} per-encounter deltas)", flush=True)

# ---- validation sample (base model predictions, canonical + pyPred) --------
sample = pd.read_csv(CSV, nrows=200)
sx = sample[canonical].to_numpy(np.float32)
with torch.no_grad():
    sp = model(torch.from_numpy((sx - x_mean) * x_invstd)).numpy().ravel()
vout = sample[canonical].copy()
vout["pyPred"] = sp * Y_scale + Y_mean
vout.to_csv(VAL, index=False)
print(f"wrote {VAL}", flush=True)

torch.save({"state_dict": base_sd, "deltas": {int(e): [d.numpy() for d in dl]
                                               for e, dl in deltas.items()},
            "mean": x_mean, "inv": x_invstd, "y_mean": Y_mean, "y_scale": Y_scale,
            "features": canonical}, OUT + ".pt")
print(f"wrote {OUT}.pt (checkpoint for re-export)", flush=True)
