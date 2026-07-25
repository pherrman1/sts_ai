#!/usr/bin/env python3
"""Train a flat 2-layer ReLU MLP combat value model.

Matches the C++ combat_mlp_sparse_v1 format in CombatValueNet.
Target: won * (WIN_BONUS + hpfrac * maxHp) — the expected end-state utility.
Architecture: 1766 -> h1 -> h2 -> 1, ReLU, sparse-normalized for fast CPU.
"""
import os, sys, gc, copy
import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/cbuffer/_train_combat.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_mlp.txt"
VAL = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_mlp_val.csv"

SAMPLE_MOD = max(1, int(os.environ.get("MLP_SAMPLE_MOD", "1")))
EPOCHS = int(os.environ.get("MLP_EPOCHS", "30"))
BATCH = int(os.environ.get("MLP_BATCH", "4096"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
WIN_BONUS = float(os.environ.get("MLP_WIN_BONUS", "50"))
H1 = int(os.environ.get("MLP_H1", "256"))
H2 = int(os.environ.get("MLP_H2", "128"))
LR = float(os.environ.get("MLP_LR", "1e-3"))
DEVICE = os.environ.get("MLP_DEVICE", "cuda")

if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)}", flush=True)
else:
    DEVICE = "cpu"

torch.set_num_threads(THREADS)
torch.manual_seed(0)
rng = np.random.default_rng(0)

header = list(pd.read_csv(CSV, nrows=0).columns)
canonical = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")]
NFEAT = len(canonical)
print(f"{NFEAT} features", flush=True)

dtypes = {c: np.float32 for c in header}
dtypes["seed"] = np.int32; dtypes["fightIdx"] = np.int16
dtypes["encounter"] = np.int16; dtypes["turn"] = np.int16

def mix64(x):
    x = np.asarray(x, dtype=np.uint64)
    x ^= x >> np.uint64(30); x *= np.uint64(0xbf58476d1ce4e5b9)
    x ^= x >> np.uint64(27); x *= np.uint64(0x94d049bb133111eb)
    return x ^ (x >> np.uint64(31))

parts_x, parts_y, parts_w, parts_g, parts_mh = [], [], [], [], []
seen = kept = 0
print(f"streaming (sample 1/{SAMPLE_MOD}) ...", flush=True)
CHUNK = 5000
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
        # Target: risk-adjusted end-HP utility
        y = won * (WIN_BONUS + hpfrac * maxhp)
        parts_x.append(p[canonical].to_numpy(np.float32))
        parts_y.append(y)
        parts_w.append(won)
        parts_mh.append(maxhp)
        parts_g.append(group[keep])
        kept += int(keep.sum())

X = np.concatenate(parts_x); Y = np.concatenate(parts_y)
Won = np.concatenate(parts_w); Mhp = np.concatenate(parts_mh)
Group = np.concatenate(parts_g)
del parts_x, parts_y, parts_w, parts_mh, parts_g; gc.collect()
print(f"sampled {len(X):,} rows", flush=True)

# Fight-group split
is_val = (mix64(Group + np.uint64(0xd1b54a32d192ed03)) % np.uint64(10)) == 0
tr = np.flatnonzero(~is_val); va = np.flatnonzero(is_val)
print(f"train {len(tr):,}, val {len(va):,}", flush=True)

# Feature normalization
x_mean = X[tr].mean(0).astype(np.float32)
x_invstd = 1 / np.maximum(X[tr].std(0).astype(np.float32), 1e-6)
Xn = np.clip((X - x_mean) * x_invstd, -8, 8).astype(np.float32)
Y_mean = float(Y[tr].mean())
Y_scale = max(float(Y[tr].std()), 1.0)
Yn = (Y - Y_mean) / Y_scale
del X; gc.collect()

# Simple 2-layer MLP (no embedding, just ReLU)
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
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
print(f"model: {sum(p.numel() for p in model.parameters()):,} params, h1={H1} h2={H2}", flush=True)

TX = torch.from_numpy(Xn); TY = torch.from_numpy(Yn.astype(np.float32))
del Xn, Yn; gc.collect()
TWon = torch.from_numpy(Won); TMhp = torch.from_numpy(Mhp)
t_itr, t_iva = torch.from_numpy(tr), torch.from_numpy(va)

def bfwd(ids_np):
    ids = torch.from_numpy(ids_np)
    return model(TX[ids].to(DEVICE))

@torch.no_grad()
def evaluate(indices):
    model.eval()
    idx_np = indices.numpy()
    preds = []
    for lo in range(0, len(idx_np), BATCH):
        preds.append(bfwd(idx_np[lo:lo+BATCH]).cpu())
    pred = torch.cat(preds).numpy() * Y_scale + Y_mean
    true = TWon[indices].numpy() * (WIN_BONUS + (Mhp[indices].numpy() if 0 else 0))
    # Reconstruct won/hpfrac from utility prediction for metric
    yw = TWon[indices].numpy()
    mhp_arr = TMhp[indices].numpy()
    actual = yw * (WIN_BONUS + (Mhp[indices].numpy() if 0 else np.zeros(len(idx_np))))
    # Simple RMSE on utility
    return {"rmse": float(np.sqrt(np.mean((pred - actual) ** 2))),
            "mae": float(np.mean(np.abs(pred - actual)))}, pred, actual

best_metric = float("inf"); best_state = None; stale = 0
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = rng.permutation(tr)
    losses = []
    for lo in range(0, len(order), BATCH):
        ids_np = order[lo:lo+BATCH]
        pred = bfwd(ids_np)
        target = TY[torch.from_numpy(ids_np)].to(DEVICE)
        loss = nn.functional.mse_loss(pred, target)
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        losses.append(float(loss.detach()))
    m, _, _ = evaluate(t_iva)
    if epoch == 1 or epoch % 5 == 0:
        print(f"epoch {epoch:02d} train_mse={np.mean(losses):.5f} val_rmse={m['rmse']:.3f} val_mae={m['mae']:.3f}", flush=True)
    if m["rmse"] < best_metric - .01:
        best_metric = m["rmse"]; best_state = copy.deepcopy(model.state_dict()); stale = 0
    else:
        stale += 1
        if stale >= 5: break

model.load_state_dict(best_state)
metrics, val_pred, val_true = evaluate(t_iva)
model = model.cpu()
print(f"best val rmse={metrics['rmse']:.3f} mae={metrics['mae']:.3f}", flush=True)

# Export in combat_mlp_sparse_v1 format
sd = model.state_dict()
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)

w1 = sd["net.0.weight"].numpy(); b1 = sd["net.0.bias"].numpy()
w2 = sd["net.2.weight"].numpy(); b2 = sd["net.2.bias"].numpy()
w3 = sd["net.4.weight"].numpy(); b3 = sd["net.4.bias"].numpy()

# Fold normalization: w1' = w1 * diag(invstd), b1' = b1 - w1 * diag(invstd) * mean
w1_fold = w1 * x_invstd.reshape(1, -1)
b1_fold = b1 - (w1 * x_invstd.reshape(1, -1) * x_mean.reshape(1, -1)).sum(1)

def write_vec(f, token, arr):
    f.write(token)
    for v in np.asarray(arr, np.float32).ravel(): f.write(f" {float(v):.9g}")
    f.write("\n")

with open(OUT, "w") as f:
    f.write("combat_mlp_sparse_v1\n")
    f.write(f"nfeat {NFEAT}\n")
    for name in canonical: f.write(f"feat {name}\n")
    write_vec(f, "y_mean", [float(Y_mean)])
    write_vec(f, "y_scale", [float(Y_scale)])
    f.write(f"h1 {H1}\n")
    write_vec(f, "w1", w1_fold)
    write_vec(f, "b1", b1_fold)
    f.write(f"h2 {H2}\n")
    write_vec(f, "w2", w2)
    write_vec(f, "b2", b2)
    write_vec(f, "w3", w3.ravel())
    write_vec(f, "b3", [float(b3.item())])

# Validation sample
sample = pd.read_csv(CSV, nrows=200)
sx = sample[canonical].to_numpy(np.float32)
with torch.no_grad():
    sp = model(torch.from_numpy((sx - x_mean) * x_invstd)).numpy().ravel()
vout = sample[canonical].copy()
vout["pyPred"] = sp * Y_scale + Y_mean
vout.to_csv(VAL, index=False)

torch.save({"state_dict": sd, "mean": x_mean, "inv": x_invstd,
            "y_mean": Y_mean, "y_scale": Y_scale,
            "features": canonical, "win_bonus": WIN_BONUS, "metrics": metrics}, OUT + ".pt")
print(f"wrote {OUT}, {OUT}.pt, {VAL}", flush=True)
