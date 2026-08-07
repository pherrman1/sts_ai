#!/usr/bin/env python3
"""Train the §132 quantile-R GBM and export it in the native combat_quantile_v1
format (9 tree sets over R = won ? 50+endHp : 0; C++ leafValue = mean of
quantiles = EV, on the terminal scale).

Usage: train_export_vcombat_quantile.py [vcombat.csv] [out.txt]
"""
import os, sys, json, time, shutil
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat_honest.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_quantile.txt"
TAUS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
ROUNDS = int(os.environ.get("QGB_ROUNDS", "150"))
WIN_BONUS = 50.0
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")

print(f"loading {CSV} ...", flush=True)
df = pd.read_csv(CSV)
meta = {"seed", "fightIdx", "won", "endHp"}
feat_cols = [c for c in df.columns if c not in meta and df[c].std() > 1e-9]
won = df["won"].to_numpy(np.float32)
endHp = df["endHp"].to_numpy(np.float32)
R = np.where(won >= 0.5, WIN_BONUS + endHp, 0.0).astype(np.float32)
group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
X = df[feat_cols].to_numpy(np.float32)
del df
tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, won, groups=group))
print(f"{len(X)} rows, {len(feat_cols)} features, {len(tr)} train / {len(va)} val", flush=True)

dtr = xgb.DMatrix(X[tr], label=R[tr], feature_names=feat_cols)
dva = xgb.DMatrix(X[va], label=R[va], feature_names=feat_cols)
t0 = time.time()
boosters = []
for tau in TAUS:
    params = dict(objective="reg:quantileerror", quantile_alpha=float(tau),
                  tree_method="hist", device=DEVICE, max_depth=6, eta=0.1,
                  subsample=0.8, colsample_bytree=0.7, min_child_weight=20, max_bin=256)
    bst = xgb.train(params, dtr, num_boost_round=ROUNDS)
    boosters.append(bst)
    print(f"  tau={tau:.1f} done ({time.time()-t0:.0f}s)", flush=True)

q = np.stack([b.predict(dva) for b in boosters], axis=1)   # (n_val, 9)
ev = q.mean(axis=1)
print(f"val: EV-MAE(vs R) {np.abs(ev - R[va]).mean():.2f} | "
      f"coverage L2 {np.sqrt(np.mean(((R[va][:,None] <= q).mean(0) - np.array(TAUS))**2)):.4f}",
      flush=True)

# ── Native export (combat_quantile_v1) ──────────────────────────────────────
with open(OUT, "w") as f:
    f.write("combat_quantile_v1\n")
    f.write(f"nquantiles {len(TAUS)}\n")
    f.write(f"nfeat {len(feat_cols)}\n")
    for n in feat_cols:
        f.write(f"feat {n}\n")
    for qidx, bst in enumerate(boosters):
        cfg = json.loads(bst.save_config())
        base_score = float(cfg["learner"]["learner_model_param"]["base_score"].strip("[] "))
        dumps = bst.get_dump(dump_format="json")
        f.write(f"base_score {base_score:.7g}\n")
        f.write(f"ntrees {len(dumps)}\n")
        for t, d in enumerate(dumps):
            nodes = json.loads(d)
            byid = {}
            def walk(nd):
                byid[nd["nodeid"]] = nd
                for c in nd.get("children", []):
                    walk(c)
            walk(nodes)
            ids = sorted(byid)
            ci = {nid: i for i, nid in enumerate(ids)}
            f.write(f"tree {t} {len(ids)}\n")
            for nid in ids:
                nd = byid[nid]
                if "leaf" in nd:
                    f.write(f"L {float(nd['leaf']):.7g}\n")
                else:
                    f.write(f"S {feat_cols.index(nd['split'])} "
                            f"{float(nd['split_condition']):.7g} "
                            f"{ci[nd['yes']]} {ci[nd['no']]}\n")
print(f"wrote {OUT}", flush=True)
