"""Pre-screen individual columns for the single-feature pass: rms(x_c) * ||W_c|| on the validation fold
(state columns: state_w rows; candidate columns: action_w rows). Not an importance measure.
usage: rank_cols.py ARTIFACT.txt MODEL.pt VAL.npz ENUM.json OUT.json"""
import sys, json, numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g7f_model as G
art, ckpt, valp, enump, out = sys.argv[1:6]
W, names = G.load_artifact(art); E = json.load(open(enump))
z = np.load(valp); n = len(z["r_nedge"])
idx = z["st_idx"].astype(np.int64); v = z["st_val"].astype(np.float64)
sq = np.bincount(idx, weights=v * v, minlength=G.S) / n
nzf = np.bincount(idx, minlength=G.S) / n
wn = np.linalg.norm(W["state_w"].numpy().astype(np.float64), axis=1)
score = np.sqrt(sq) * wn
a = z["e_act"].astype(np.float64)
asc = np.sqrt((a ** 2).mean(0)) * np.linalg.norm(W["action_w"].numpy().astype(np.float64), axis=1)
def pretty(c):
    x = names[c]
    for p, tab in (("hd", "card"), ("dr", "card"), ("ds", "card"), ("ex", "card"), ("pot", "potion"), ("r", "relic")):
        if x.startswith(p) and x[len(p):].isdigit():
            return f"{x}:{E[tab][int(x[len(p):])]}"
    return x
rows = [{"col": names[c], "name": pretty(c), "score": float(score[c]), "nonzero_frac": float(nzf[c])} for c in range(G.S)]
arows = [{"col": names[G.S + c], "score": float(asc[c])} for c in range(22)]
json.dump({"state": sorted(rows, key=lambda r: -r["score"]), "action": sorted(arows, key=lambda r: -r["score"])}, open(out, "w"), indent=0)
for r in sorted(rows, key=lambda r: -r["score"])[:40]: print(r)
for r in sorted(arows, key=lambda r: -r["score"]): print(r)
