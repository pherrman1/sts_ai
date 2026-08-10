#!/usr/bin/env python3
"""Export the XGBoost V_win model to a compact trees.txt for native C++ tree-walk
inference (eliminates the v_server socket for OOC V_win decisions). Same tree format
as export_combat_model.py, plus a `logistic 1` marker so C++ applies sigmoid.
Usage: export_win_model.py [model.json] [out_trees.txt] [maxtrees]"""
import sys, json, xgboost as xgb

MODEL    = sys.argv[1] if len(sys.argv) > 1 else "models/v_win_xgb.json"
OUT      = sys.argv[2] if len(sys.argv) > 2 else "build/v_win_trees.txt"
MAXTREES = int(sys.argv[3]) if len(sys.argv) > 3 else 0

bst = xgb.Booster(); bst.load_model(MODEL)
feats = bst.feature_names
cfg = json.loads(bst.save_config())
base_score = float(str(cfg["learner"]["learner_model_param"]["base_score"]).strip("[]"))
obj = cfg["learner"]["objective"]["name"]
logistic = 1 if "logistic" in obj else 0
dumps = bst.get_dump(dump_format="json")
if MAXTREES > 0: dumps = dumps[:MAXTREES]
fidx = {n: i for i, n in enumerate(feats)}

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
            out.append(("S", fidx[nd["split"]], float(nd["split_condition"]), ci[nd["yes"]], ci[nd["no"]]))
    return out

with open(OUT, "w") as f:
    f.write(f"nfeat {len(feats)}\n")
    for n in feats: f.write(f"feat {n}\n")
    f.write(f"logistic {logistic}\n")
    f.write(f"base_score {base_score}\n")
    f.write(f"ntrees {len(dumps)}\n")
    for t, d in enumerate(dumps):
        nodes = flatten(json.loads(d))
        f.write(f"tree {t} {len(nodes)}\n")
        for nd in nodes:
            if nd[0] == "L": f.write(f"L {nd[1]:.7g}\n")
            else:            f.write(f"S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n")
print(f"wrote {OUT}: {len(feats)} feats, {len(dumps)} trees, base_score {base_score}, logistic {logistic}")
