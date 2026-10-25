"""Exploratory (not pre-registered) follow-ups to test.json: ties and non-tied pairs. Usage: explore.py OUT"""
import json, os, sys
import numpy as np
import xgboost as xgb
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s0 import dense, boot
out = sys.argv[1]
bst = xgb.Booster(); bst.load_model(os.path.join(out, "head.json"))
best = json.load(open(os.path.join(out, "fit.json")))["bestIteration"]
pairs = [p for p in json.load(open(os.path.join(out, "pairs.json"))) if p["split"] == "test"]
ga = bst.predict(xgb.DMatrix(dense(pairs, "fa")), iteration_range=(0, best + 1))
gb = bst.predict(xgb.DMatrix(dense(pairs, "fb")), iteration_range=(0, best + 1))
same = np.array([sorted(zip(*p["fa"])) == sorted(zip(*p["fb"])) for p in pairs])
tie = ga == gb
seeds = np.array([p["seed"] for p in pairs]); d = np.array([p["ya"] - p["yb"] for p in pairs], float)
s = np.sign(ga - gb); nt = ~tie
rep = {"pairs": len(pairs), "ties": int(tie.sum()), "tiesWithIdenticalFeatures": int((tie & same).sum()),
       "tieRootScreens": {str(k): int(v) for k, v in zip(*np.unique([p["rootScreen"] for p, t in zip(pairs, tie) if t], return_counts=True))},
       "A_h_nonTied": boot(seeds[nt], (d * s)[nt]),
       "accuracyNonTiedDiscordant": boot(seeds[nt & (d != 0)], ((d * s) > 0)[nt & (d != 0)].astype(float)),
       "meanAbsHeadGapNonTied": float(np.abs(ga - gb)[nt].mean())}
json.dump(rep, open(os.path.join(out, "explore.json"), "w"), indent=1); print(json.dumps(rep, indent=1))
