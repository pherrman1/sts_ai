#!/usr/bin/env python3
"""AlphaZero-lite policy net: a COMPARATOR net(state, action) -> logit whose
softmax over a decision's legal edges approximates the MCTS visit distribution π.
Trained on build/vpolicy.csv (one row per root edge: state feats ++ action feats,
+ visit + total) from `one_combat.elf policygen`.

Target = log(visit + 1). Because the datagen sim budget (`total`) is ~constant
across decisions, this is a consistent logit: the C++ side softmaxes the net's
per-action scores over a node's edges (softmax is shift-invariant within a group),
recovering a calibrated prior. That prior steers PUCT selection.

Metric that matters for a prior = TOP-1 agreement (does argmax(pred) pick the
most-visited action?) and top-1 visit-share captured. Exports the compact tree
text the C++ CombatValueNet(isPolicy=true) reads.

Usage: train_policy.py [vpolicy.csv] [out_model.json] [out_trees.txt]
"""
import sys, os, json, shutil, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vpolicy.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/policy.json"
TREES = sys.argv[3] if len(sys.argv) > 3 else "build/policy_trees.txt"

print(f"loading {CSV} ...", flush=True)
KEYS = ("seed", "fightIdx", "decIdx", "visit", "total")
# The policy CSV is ALL integers (combat state + visit counts). float32 wastes 2x
# RAM and OOMs on big buffers. Load feature cols as int16 (range -32768..32767,
# ample for HP/block/counts/str) and the key cols (seed ~1e6) as int32. ~2x less RAM.
_hdr = pd.read_csv(CSV, nrows=0).columns
dtypes = {c: (np.int32 if c in KEYS else np.int16) for c in _hdr}
df = pd.read_csv(CSV, dtype=dtypes)
N = len(df)
feat_cols = [c for c in df.columns if c not in KEYS and df[c].std() > 1e-9]

# unique decision-group id (edges of one decision must not straddle train/val)
g = (df["seed"].astype(np.int64) * 100000
     + df["fightIdx"].astype(np.int64) * 1000
     + df["decIdx"].astype(np.int64))
group = g.to_numpy(); del g
# WINDOW growth: the replay buffer grows ~linearly in iterations, so cap total rows
# by DROPPING whole decision-groups (keeps each decision's edges intact) -> bounded
# peak RAM regardless of window size. Default 4M (~today's footprint); env override.
MAXROWS = int(os.environ.get("STS_POLICY_MAXROWS", "4000000"))
if N > MAXROWS:
    rng = np.random.default_rng(0)
    uniq = np.unique(group)
    keep = uniq[rng.random(len(uniq)) < (MAXROWS / N)]
    mask = np.isin(group, keep)
    df = df[mask]; group = group[mask]; N = len(group)
    print(f"subsampled: {N} rows / {len(keep)} decisions (cap {MAXROWS})", flush=True)
visit = df["visit"].to_numpy(np.float32)
y = np.log(visit + 1.0).astype(np.float32)      # logit target
# extract features, then free the frame before the big DMatrix build to cap peak RAM
X = df[feat_cols].to_numpy(np.float32)
del df; import gc; gc.collect()
ndec = len(np.unique(group))
print(f"policy data: {N} edge-rows, {ndec} decisions ({N/ndec:.1f} edges/dec), "
      f"{len(feat_cols)} features", flush=True)

tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))
dtr = xgb.QuantileDMatrix(X[tr], label=y[tr], feature_names=feat_cols)
dva = xgb.QuantileDMatrix(X[va], label=y[va], ref=dtr, feature_names=feat_cols)
# GPU if available (local), else CPU (e.g. a many-core cloud box). STS_XGB_DEVICE overrides.
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
N_TREES = max(1, int(os.environ.get("STS_POLICY_TREES", "100")))
params = dict(objective="reg:squarederror", tree_method="hist", device=DEVICE,
              max_depth=6, eta=0.06, subsample=0.8, colsample_bytree=0.8,
              min_child_weight=20, max_bin=256)
print(f"training on {DEVICE} (max {N_TREES} trees) ...", flush=True)
bst = xgb.train(params, dtr, num_boost_round=N_TREES, evals=[(dva, "val")],
                early_stopping_rounds=40, verbose_eval=100)
best = bst.best_iteration
bst.save_model(MODEL)
print(f"saved -> {MODEL} (best_iter {best})", flush=True)

# ---- prior-quality metrics on val decisions (softmax within each group) ----
pv = bst.predict(dva, iteration_range=(0, best + 1))
gva = group[va]
vva = visit[va]
order = np.argsort(gva, kind="stable")
gs, ps, vs = gva[order], pv[order], vva[order]
bounds = np.flatnonzero(np.diff(gs)) + 1
starts = np.concatenate(([0], bounds))
ends = np.concatenate((bounds, [len(gs)]))

top1_hit = 0; captured = 0.0; policy_mass = 0.0; ngrp = 0; unif_hit = 0
for s, e in zip(starts, ends):
    if e - s < 2:
        continue
    ngrp += 1
    p = ps[s:e]; v = vs[s:e]
    vtot = v.sum()
    pred_pick = np.argmax(p)
    true_pick = np.argmax(v)
    if pred_pick == true_pick:
        top1_hit += 1
    unif_hit += 1.0 / (e - s)                      # random-guess baseline
    captured += v[pred_pick] / vtot                # visit share the prior's top choice got
    # softmax prior mass placed on the truly best action (calibration)
    pe = np.exp(p - p.max()); pe /= pe.sum()
    policy_mass += pe[true_pick]

print(f"\nval decisions (>=2 edges): {ngrp}")
print(f"  top-1 agreement:        {top1_hit/ngrp:.3f}   (uniform baseline {unif_hit/ngrp:.3f})")
print(f"  visit-share captured:   {captured/ngrp:.3f}   (prior's top pick's actual visit fraction)")
print(f"  softmax mass on best:   {policy_mass/ngrp:.3f}")

# ---- compact tree-text export for C++ CombatValueNet(isPolicy=true) ----
feats = list(bst.feature_names)
fidx = {n: i for i, n in enumerate(feats)}
cfg = json.loads(bst.save_config())
base_score = float(cfg["learner"]["learner_model_param"]["base_score"].strip("[] "))
dumps = bst.get_dump(dump_format="json")[: best + 1]

def flatten(tree):
    byid = {}
    def walk(nd):
        byid[nd["nodeid"]] = nd
        for c in nd.get("children", []): walk(c)
    walk(tree)
    ids = sorted(byid)
    ci = {nid: i for i, nid in enumerate(ids)}
    out = []
    for nid in ids:
        nd = byid[nid]
        if "leaf" in nd:
            out.append(("L", float(nd["leaf"])))
        else:
            out.append(("S", fidx[nd["split"]], float(nd["split_condition"]),
                        ci[nd["yes"]], ci[nd["no"]]))
    return out

with open(TREES, "w") as f:
    f.write(f"nfeat {len(feats)}\n")
    for n in feats: f.write(f"feat {n}\n")
    f.write(f"base_score {base_score}\n")
    f.write(f"ntrees {len(dumps)}\n")
    for t, d in enumerate(dumps):
        nodes = flatten(json.loads(d))
        f.write(f"tree {t} {len(nodes)}\n")
        for nd in nodes:
            if nd[0] == "L":
                f.write(f"L {nd[1]:.7g}\n")
            else:
                f.write(f"S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n")
print(f"wrote {TREES}: {len(dumps)} trees, {len(feats)} features", flush=True)
