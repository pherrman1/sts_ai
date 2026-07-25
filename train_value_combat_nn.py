#!/usr/bin/env python3
"""Distil a combat XGBoost teacher into a compact native-inference MLP.

The replay CSV is streamed and sampled by whole fight, so the multi-gigabyte
window is never loaded in full.  The exported text format is consumed directly
by CombatValueNet in C++ and the validation CSV checks Python/C++ parity.

Usage:
  train_value_combat_nn.py replay.csv teacher.json out.nn validation.csv

Environment knobs: NN_SAMPLE_MOD (4), NN_H1 (64), NN_H2 (32),
NN_MAX_EPOCHS (20), NN_TRUTH_BLEND (0.2), NN_BATCH_SIZE (2048).
"""
import os
import sys
import gc
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score
from sklearn.neural_network import MLPRegressor


CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/cbuffer/_train.csv"
TEACHER = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/v_combat_iter28.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_nn.txt"
VAL = sys.argv[4] if len(sys.argv) > 4 else "build/v_combat_nn_val.csv"

SAMPLE_MOD = max(1, int(os.environ.get("NN_SAMPLE_MOD", "4")))
H1 = int(os.environ.get("NN_H1", "64"))
H2 = int(os.environ.get("NN_H2", "32"))
MAX_EPOCHS = int(os.environ.get("NN_MAX_EPOCHS", "20"))
TRUTH_BLEND = float(os.environ.get("NN_TRUTH_BLEND", "0.2"))
BATCH_SIZE = int(os.environ.get("NN_BATCH_SIZE", "2048"))
CHUNK_ROWS = int(os.environ.get("NN_CHUNK_ROWS", "10000"))


def mix64(x):
    """Deterministic vectorized SplitMix64 finalizer."""
    x = np.asarray(x, dtype=np.uint64)
    x = x ^ (x >> np.uint64(30))
    x = x * np.uint64(0xbf58476d1ce4e5b9)
    x = x ^ (x >> np.uint64(27))
    x = x * np.uint64(0x94d049bb133111eb)
    return x ^ (x >> np.uint64(31))


teacher = xgb.Booster()
teacher.load_model(TEACHER)
features = list(teacher.feature_names)
needed = ["seed", "fightIdx", "won", "endHp", "curHp", "maxHp"] + features
# Preserve order while removing curHp/maxHp duplicates from the teacher feature list.
needed = list(dict.fromkeys(needed))
dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in needed}

xs, ys, wins, hpfracs, groups = [], [], [], [], []
seen_rows = kept_rows = 0
print(f"streaming {CSV}; keeping about 1/{SAMPLE_MOD} of fights ...", flush=True)
for ci, df in enumerate(pd.read_csv(CSV, usecols=needed, dtype=dtypes,
                                    chunksize=CHUNK_ROWS)):
    seed = df["seed"].to_numpy(np.uint64)
    fight = df["fightIdx"].to_numpy(np.uint64)
    group = seed * np.uint64(1000) + fight
    keep = (mix64(group + np.uint64(0x9e3779b97f4a7c15))
            % np.uint64(SAMPLE_MOD)) == 0
    seen_rows += len(df)
    if keep.any():
        part = df.loc[keep]
        xs.append(part[features].to_numpy(np.float32))
        ys.append(part["endHp"].to_numpy(np.float32))
        wins.append(part["won"].to_numpy(np.float32))
        hpfracs.append(part["curHp"].to_numpy(np.float32)
                       / np.maximum(part["maxHp"].to_numpy(np.float32), 1.0))
        groups.append(group[keep])
        kept_rows += int(keep.sum())
    if ci % 25 == 0:
        print(f"  scanned {seen_rows:,}, kept {kept_rows:,}", flush=True)
print(f"sampled {kept_rows:,}/{seen_rows:,} rows", flush=True)

X = np.concatenate(xs); del xs
y = np.concatenate(ys); del ys
won = np.concatenate(wins); del wins
hp_frac = np.concatenate(hpfracs); del hpfracs
group = np.concatenate(groups); del groups
gc.collect()

# A second independent group hash makes a leakage-free validation split.
is_val = (mix64(group + np.uint64(0xd1b54a32d192ed03)) % np.uint64(10)) == 0
tr = np.flatnonzero(~is_val)
va = np.flatnonzero(is_val)
print(f"fight-group split: train {len(tr):,}, validation {len(va):,}", flush=True)

print("predicting full-tree teacher on the sampled rows ...", flush=True)
teacher_pred = teacher.predict(xgb.DMatrix(X, feature_names=features))
target = ((1.0 - TRUTH_BLEND) * teacher_pred + TRUTH_BLEND * y).astype(np.float32)

# Match the critical-state emphasis of train_value_combat.py without needing the
# much larger policy replay file.  The teacher component already contains its
# encounter- and disagreement-focused training signal.
weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)).astype(np.float32)
weight = np.clip(weight, 1.0, 6.0)
weight /= weight[tr].mean()

# Normalize using training fights only.  Store inverse std for a cheap native
# multiply instead of division at every MCTS leaf.
x_mean = X[tr].mean(axis=0, dtype=np.float64).astype(np.float32)
x_std = X[tr].std(axis=0, dtype=np.float64).astype(np.float32)
x_invstd = np.reciprocal(np.maximum(x_std, 1e-6)).astype(np.float32)
X -= x_mean
X *= x_invstd
y_mean = float(target[tr].mean())
y_scale = float(max(target[tr].std(), 1e-6))
target_z = ((target - y_mean) / y_scale).astype(np.float32)

net = MLPRegressor(hidden_layer_sizes=(H1, H2), activation="relu", solver="adam",
                   batch_size=BATCH_SIZE, learning_rate_init=1e-3,
                   max_iter=MAX_EPOCHS, early_stopping=True,
                   validation_fraction=0.08, n_iter_no_change=3, tol=1e-4,
                   random_state=0, verbose=True)
print(f"training MLP {len(features)} -> {H1} -> {H2} -> 1 on CPU ...", flush=True)
net.fit(X[tr], target_z[tr], sample_weight=weight[tr])

student = (net.predict(X[va]).astype(np.float32) * y_scale + y_mean)
teacher_rmse = float(np.sqrt(np.mean((teacher_pred[va] - y[va]) ** 2)))
student_truth_rmse = float(np.sqrt(np.mean((student - y[va]) ** 2)))
student_teacher_rmse = float(np.sqrt(np.mean((student - teacher_pred[va]) ** 2)))
critical = (hp_frac[va] < 0.35) | (won[va] < 0.5)
critical_rmse = float(np.sqrt(np.mean((student[critical] - y[va][critical]) ** 2)))
print(f"teacher truth RMSE {teacher_rmse:.3f}", flush=True)
print(f"student truth RMSE {student_truth_rmse:.3f}, R2 {r2_score(y[va], student):.4f}", flush=True)
print(f"student-teacher RMSE {student_teacher_rmse:.3f}", flush=True)
print(f"student critical truth RMSE {critical_rmse:.3f} on {int(critical.sum()):,} rows", flush=True)


def write_values(f, token, values):
    a = np.asarray(values, dtype=np.float32).ravel()
    f.write(token)
    for v in a:
        f.write(f" {float(v):.9g}")
    f.write("\n")


# sklearn stores weights as [input, output]; native dots are output-major.
# Fold centering/scaling into the first layer.  The native evaluator can then
# skip zero-valued card/relic features instead of turning every zero into a
# nonzero standardized value.  Store this first layer input-major so all hidden
# weights touched by one nonzero input are contiguous.
w1_raw = (net.coefs_[0] * x_invstd[:, None]).astype(np.float32)
b1_raw = (net.intercepts_[0]
          - (x_mean * x_invstd).astype(np.float32) @ net.coefs_[0]).astype(np.float32)
with open(OUT, "w") as f:
    f.write("combat_mlp_sparse_v1\n")
    f.write(f"nfeat {len(features)}\n")
    for name in features:
        f.write(f"feat {name}\n")
    f.write(f"y_mean {y_mean:.9g}\n")
    f.write(f"y_scale {y_scale:.9g}\n")
    f.write(f"h1 {H1}\n")
    write_values(f, "w1", w1_raw)
    write_values(f, "b1", b1_raw)
    f.write(f"h2 {H2}\n")
    write_values(f, "w2", net.coefs_[1].T)
    write_values(f, "b2", net.intercepts_[1])
    write_values(f, "w3", net.coefs_[2].reshape(-1))
    f.write(f"b3 {float(net.intercepts_[2][0]):.9g}\n")
print(f"wrote {OUT} ({sum(c.size for c in net.coefs_):,} weights)", flush=True)

# Cross-language parity sample in canonical C++ feature order.
hdr = pd.read_csv(CSV, nrows=0).columns
all_dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in hdr}
sample = pd.read_csv(CSV, dtype=all_dtypes, nrows=200)
canonical = [c for c in sample.columns if c not in ("seed", "fightIdx", "won", "endHp")]
sx = sample[features].to_numpy(np.float32)
sx -= x_mean
sx *= x_invstd
sample_pred = net.predict(sx).astype(np.float32) * y_scale + y_mean
vout = sample[canonical].copy()
vout["pyPred"] = sample_pred
vout.to_csv(VAL, index=False)
print(f"wrote {VAL}: {len(vout)} parity rows", flush=True)
