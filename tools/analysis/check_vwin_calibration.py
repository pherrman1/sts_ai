#!/usr/bin/env python3
"""V_win bootstrap calibration check (Wave A2, bootstrap-problem step).

The Tier-B row labels are per-action averages over STRATEGIC_BRANCH_FUTURES
sampled continuations: `labelWon` is V_win(s_cutoff) when a continuation is
censored and bootstrapped, the terminal outcome {0,1} when it terminates, and
a fractional average when futures mix (e.g. several futures all terminating at
different outcomes).  `labelBootstrap` averages the per-future censored flag
over the same futures, so labelBootstrap==0 means none of the sampled
continuations bootstrapped (all terminated).  This script keeps only each
decision's CHOSEN action row (chosen==1) whose sampled counterfactual
continuation(s) terminated without bootstrapping (labelBootstrap==0),
re-evaluates the native win trees on the shared pre-decision state block,
and compares the prediction against the live run's terminal outcome `won`
(not the action-specific counterfactual `labelWon`): Brier, log loss,
calibration deciles.  Systematic error here would corrupt the Q_win labels
that bootstrap from V_win.

Usage: check_vwin_calibration.py <tierb.csv> [trees.txt]
       check_vwin_calibration.py --ckpt <trainer.pt> <tierb.csv>

Wave B truth-check (--ckpt): instead of the win trees, predict Q_win(s,a) with
an exported strategic net checkpoint (the V5 Q_win head, sigmoided) on the same
terminal chosen rows.  The checkpoint is parity-checked against the native
artifact by export_strategic.py (max logit err ~1e-5).  Run once with the
pre-recalibration checkpoint and once with the post-recalibration one to test
whether the V_win bootstrap bias propagated into the Q_win head.
"""
import sys
import numpy as np
import pandas as pd
import torch
from torch import nn

CKPT = None
ARGS = [a for a in sys.argv[1:]]
if "--ckpt" in ARGS:
    i = ARGS.index("--ckpt")
    CKPT = ARGS[i + 1]
    del ARGS[i:i + 2]

CSV = ARGS[0] if len(ARGS) > 0 else "build/strategic_qwin.csv"
TREES = ARGS[1] if len(ARGS) > 1 else "models/v_win_trees.txt"
if CKPT:
    TREES = None

# --- Q_win head prediction (the trainer's Net, exported parity-checked) ---
def parse_bits(x):
    if isinstance(x, str) and x.startswith("bits="):
        return int(x.split("=")[1])
    return int(x)

def net_predictor(ckpt_path):
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    nstate = ckpt["features"]
    mean = ckpt["mean"].astype(np.float32)
    inv = ckpt["inv"].astype(np.float32)
    if ckpt.get("maps", False):
        raise SystemExit(
            "[check_vwin_calibration] checkpoint was trained with the map-DAG "
            "encoder (maps=True); this checker only supports the plain V5 "
            "layout. Re-run with a non-map checkpoint (e.g. "
            "ooc_strategic_qwin_cal.pt); MAP-screen Q_win predictions here "
            "would be silently wrong without the map features.")

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.s = nn.Sequential(nn.Linear(nstate, 256), nn.LayerNorm(256), nn.GELU(),
                                   nn.Dropout(0.2), nn.Linear(256, 128), nn.GELU())
            self.a_bits = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Dropout(0.2),
                                        nn.Linear(32, 16))
            self.a_cat = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Linear(32, 16))
            self.cats = nn.ModuleList([nn.Embedding(512, 4) for _ in range(6)])
            self.atype = nn.Embedding(16, 8)
            self.screen = nn.Embedding(16, 8)
            self.pol = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
            self.q = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
            self.q_hp = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
            self.q_floor = nn.Sequential(nn.Linear(168, 96), nn.GELU(), nn.Linear(96, 1))
            self.vals = nn.ModuleList([nn.Sequential(nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))
                                       for _ in range(8)])

        def forward(self, x, bits, cat, atype, screen):
            z = self.s(x)
            b = self.a_bits(bits)
            cat_in = torch.cat([self.cats[i](cat[:, i]) for i in range(6)]
                               + [self.atype(atype)], 1)
            a = self.a_cat(cat_in)
            ha = torch.cat((z, b, a, self.screen(screen)), 1)
            q = self.q(ha).squeeze(1)
            return q

    model = Net()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    ar = np.arange(32, dtype=np.int64)
    cat_cols = ["c1", "c2", "c3", "cand1", "cand2", "cand3"]

    def predict(X, action, cat, atype, screen):
        x = torch.from_numpy(np.clip((X - mean) * inv, -8, 8).astype(np.float32))
        bits = torch.from_numpy(((np.asarray([parse_bits(a) for a in action])[:, None] >> ar[None, :]) & 1)
                                .astype(np.float32))
        c = torch.from_numpy(np.clip(cat + 1, 0, 511).astype(np.int64))
        a = torch.from_numpy(np.clip(atype + 1, 0, 15).astype(np.int64))
        s = torch.from_numpy(np.clip(screen, 0, 15).astype(np.int64))
        with torch.no_grad():
            return torch.sigmoid(model(x, bits, c, a, s)).numpy()

    return predict, mean.shape[0]

# --- load the native tree format (export_win_model.py output) ---
def load_trees(path):
    feats = []
    logistic = 0
    base_score = 0.0
    trees = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if parts[0] == "nfeat":
                nfeat = int(parts[1])
            elif parts[0] == "feat":
                feats.append(parts[1])
            elif parts[0] == "logistic":
                logistic = int(parts[1])
            elif parts[0] == "base_score":
                base_score = float(parts[1])
            elif parts[0] == "ntrees":
                ntrees = int(parts[1])
            elif parts[0] == "tree":
                n = int(parts[2])
                nodes = []
                for _ in range(n):
                    p = f.readline().split()
                    if p[0] == "L":
                        nodes.append(("L", float(p[1])))
                    else:
                        nodes.append(("S", int(p[1]), float(p[2]), int(p[3]), int(p[4])))
                trees.append(nodes)
    feat_idx = {name: i for i, name in enumerate(feats)}
    # Mirror the C++ WinNet::predict exactly (one_combat.cpp): base_score is a
    # probability; it is converted to logit space before adding leaf margins,
    # then sigmoided. Starting from the raw probability instead of its logit
    # inflates every prediction by ~1.0 logit — a systematic checker bias.
    base_margin = float(np.log(base_score / (1.0 - base_score))) if logistic else base_score
    print(f"loaded {len(trees)} trees, {len(feats)} feats, logistic={logistic}, "
          f"base={base_score} (logit {base_margin:.4f})")

    def predict_row(vec):
        acc = base_margin
        for nodes in trees:
            idx = 0
            while nodes[idx][0] != "L":
                _, fi, thr, yes, no = nodes[idx]
                idx = yes if vec[fi] < thr else no
            acc += nodes[idx][1]
        return 1.0 / (1.0 + np.exp(-acc)) if logistic else acc

    return feats, predict_row

if CKPT:
    net_predict, nstate = net_predictor(CKPT)
    print(f"loaded Q_win checkpoint {CKPT} ({nstate} state features)")
    feats = None
    predict_row = None
else:
    feats, predict_row = load_trees(TREES)

# --- read the CSV in chunks; keep terminal rows (labelBootstrap==0) ---
hdr = pd.read_csv(CSV, nrows=0).columns
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
state_cols = list(hdr[ci + 1:wi])
state_idx = {name: i for i, name in enumerate(state_cols)}
if CKPT:
    if len(state_cols) != nstate:
        raise ValueError(f"checkpoint expects {nstate} state features, CSV has {len(state_cols)}")
    need = None
    print(f"state block: {len(state_cols)} cols")
else:
    need = [c for c in feats if c in state_idx]
    missing = [c for c in feats if c not in state_idx]
    print(f"state block: {len(state_cols)} cols; {len(need)}/{len(feats)} model features present"
          + (f"; MISSING: {missing[:5]}" if missing else ""))

CHUNK = 200000
preds = []
labels = []
read_cols = (["labelBootstrap", "won", "chosen"]
             + (state_cols if CKPT else need))
if CKPT:
    read_cols += ["action", "actionType", "c1", "c2", "c3", "cand1", "cand2", "cand3", "screen"]
for chunk in pd.read_csv(CSV, usecols=read_cols, chunksize=CHUNK, dtype=np.float32):
    # Restrict to chosen-action rows whose sampled counterfactual continuations
    # all terminated: labelBootstrap averages the per-future censored flag over
    # STRATEGIC_BRANCH_FUTURES, so labelBootstrap==0 means every sampled future
    # terminated without bootstrapping. All actions at a decision share the same
    # live pre-decision state; non-chosen rows differ by counterfactual action,
    # while `won` records the live run outcome.
    m = (chunk.labelBootstrap.to_numpy(np.float32) == 0) & (chunk.chosen.to_numpy(np.float32) == 1)
    if not m.any():
        continue
    y = chunk.won.to_numpy(np.float32)[m]
    if CKPT:
        X = chunk[state_cols].to_numpy(np.float32)[m]
        p = net_predict(X, chunk.action.to_numpy()[m],
                        chunk[["c1", "c2", "c3", "cand1", "cand2", "cand3"]].to_numpy(np.int64)[m],
                        chunk.actionType.to_numpy(np.int64)[m],
                        chunk.screen.to_numpy(np.int64)[m])
    else:
        X = chunk[need].to_numpy(np.float32)[m]
        p = np.array([predict_row(X[i]) for i in range(len(X))])
    preds.append(p)
    labels.append(y)
    print(f"  chunk: +{int(m.sum())} terminal chosen rows (total {sum(len(l) for l in labels)})", flush=True)

p = np.concatenate(preds)
y = np.concatenate(labels)
n = len(p)
print(f"\nterminal rows: {n}, terminal win rate: {y.mean():.4f}")
if n < 50:
    print("too few terminal rows for a calibration verdict")
    sys.exit(0)
brier = float(np.mean((p - y) ** 2))
eps = 1e-12
ll = float(-np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1))))
order = np.argsort(p)
ps, ys = p[order], y[order]
cal = []
for b in range(10):
    lo, hi = (b * n) // 10, ((b + 1) * n) // 10
    if hi - lo >= 5:
        cal.append((float(ps[lo:hi].mean()), float(ys[lo:hi].mean())))
cal_max = max(abs(a - b) for a, b in cal) if cal else float("nan")
print(f"Brier: {brier:.4f}  (baseline always-{y.mean():.2f}: {(y.mean() * (1 - y.mean())):.4f})")
print(f"log loss: {ll:.4f}")
print(f"max decile |pred - emp|: {cal_max:.4f}")
print("deciles (pred, emp):")
for a, b in cal:
    print(f"  {a:.3f} {b:.3f}")
