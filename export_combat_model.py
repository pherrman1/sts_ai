#!/usr/bin/env python3
"""Export the trained V_combat XGBoost model to a compact flat text format that
the C++ CombatValueNet evaluator reads, plus a validation CSV (canonical feature
vectors + this model's predictions) so the C++ eval can be checked to match.

Usage: export_combat_model.py [model.json] [out_trees.txt] [train.csv] [val.csv]
"""
import sys, json, numpy as np, pandas as pd, xgboost as xgb

MODEL = sys.argv[1] if len(sys.argv) > 1 else "build/v_combat.json"
OUT   = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_trees.txt"
CSV   = sys.argv[3] if len(sys.argv) > 3 else "build/vcombat.csv"
VAL   = sys.argv[4] if len(sys.argv) > 4 else "build/v_combat_val.csv"
MAXTREES = int(sys.argv[5]) if len(sys.argv) > 5 else 0   # 0 = all; else keep first N (boosting is additive)

bst = xgb.Booster(); bst.load_model(MODEL)
feats = list(bst.feature_names)
fidx = {n: i for i, n in enumerate(feats)}
cfg = json.loads(bst.save_config())
base_score = float(cfg["learner"]["learner_model_param"]["base_score"].strip("[] "))
dumps = bst.get_dump(dump_format="json")
NTREE = len(dumps) if MAXTREES <= 0 else min(MAXTREES, len(dumps))
dumps = dumps[:NTREE]
print(f"model: {len(feats)} features, keeping {NTREE} trees, base_score={base_score}")

def flatten(tree):
    """xgboost json tree -> (nodes list in compact index order, root_index=0).
    node = ('S', featIdx, thresh, yes_ci, no_ci) or ('L', value)."""
    byid = {}
    def walk(nd):
        byid[nd["nodeid"]] = nd
        for c in nd.get("children", []): walk(c)
    walk(tree)
    ids = sorted(byid)                      # nodeid 0 (root) sorts first
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

with open(OUT, "w") as f:
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
print(f"wrote {OUT}")

# ---- validation file: 200 sampled rows' canonical features + model prediction ----
# This file only checks that the C++ evaluator matches Python.  A small prefix is
# sufficient and avoids re-reading the multi-gigabyte replay window after every
# training run.
_hdr = pd.read_csv(CSV, nrows=0).columns
_dt = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
df = pd.read_csv(CSV, dtype=_dt, nrows=200)
canon = [c for c in df.columns if c not in ("seed", "fightIdx", "won", "endHp")]
samp = df.sample(frac=1, random_state=1).reset_index(drop=True)
Xmodel = samp[feats].to_numpy(np.float32)          # model-ordered features
pred = bst.predict(xgb.DMatrix(Xmodel, feature_names=feats), iteration_range=(0, NTREE))
out = samp[canon].copy()
out["pyPred"] = pred
out.to_csv(VAL, index=False)
print(f"wrote {VAL}: {len(out)} rows, {len(canon)} canonical features "
      f"(pred mean {pred.mean():.2f})")
print("canonical feature order matches C++ combatFeatureNames():")
print("  " + ",".join(canon))
