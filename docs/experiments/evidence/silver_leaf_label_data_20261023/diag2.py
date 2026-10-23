#!/usr/bin/env python3
"""Offline leaf-head diagnostics on a silver-leaf-a20 pack: is the head limited by data or by its inputs?

Same pack, folds, label (z = score / 100), refchg exclusion, optimizer and early stopping as train_head_a20.py.
Variants (VARIANTS env, comma list; default all):
  frozen        the a20 recipe: head 128-64-1 on the frozen g7f_E trunk (reproduces the committed report)
  frozen50/25   the same on a random 50% / 25% of the fit-fold runs (by seed); stop and test folds unchanged
  frozenbig     a bigger head (128-256-256-1) on the frozen trunk: head capacity
  e2e           the same layers as `frozen`, but the trunk (state embedding, monster and encounter embeddings) is
                trained too, initialised from g7f_E: the inputs the head can use
  e2e50         e2e on the 50% subset: does the better model want more data?
Reports fold-4 RMSE and bias (Silver points) by act, room, turn, act x room, next to Silver's own root value.

Second round (diag2.py): PACK2 (env) adds the first campaign's pack (a20, weaker-combat labels) to the fit folds;
stop and test stay on PACK's folds 3 and 4. Extra variants:
  e2e_reg       e2e with trunk lr 1e-4, trunk weight decay 1e-4 and dropout 0.1 on the trunk output
  e2e_both      e2e fit on both packs' folds 0-2
  e2e_reg_both  e2e_reg fit on both packs' folds 0-2
  frozen_both   frozen fit on both packs' folds 0-2

Later additions (env): SAVE=1 also writes OUTDIR/<variant>.pt (head, trunk, standardizer) and the fold-4
predictions <variant>_test_pred.npz; LABEL=q trains on Silver's root value instead of the end score.

usage: diag2.py PACK.npz MODEL.pt OUTDIR
"""
import json
import os
import sys
import time

import numpy as np
import torch

torch.set_num_threads(4)
nn = torch.nn
t0 = time.time()
PACK, CK, OUTDIR = sys.argv[1:4]
os.makedirs(OUTDIR, exist_ok=True)
VARIANTS = os.environ.get("VARIANTS", "frozen,frozen50,frozen25,frozenbig,e2e,e2e50").split(",")

def load(path):
    z = np.load(path)
    return (z["st_ptr"].astype(np.int64), z["st_idx"].astype(np.int64), z["st_val"].astype(np.float32),
            {k[2:]: z[k] for k in z.files if k.startswith("r_") and k != "r_enc"}, [str(r) for r in z["rooms"]])


st_ptr, st_idx, st_val, R, rooms = load(PACK)
R["src"] = np.ones(len(R["seed"]), np.int64)
if os.environ.get("PACK2"):
    p2, i2, v2, R2, rooms2 = load(os.environ["PACK2"])
    assert rooms2 == rooms
    R2["src"] = np.zeros(len(R2["seed"]), np.int64)
    st_ptr = np.concatenate([st_ptr, p2[1:] + st_ptr[-1]])
    st_idx = np.concatenate([st_idx, i2]); st_val = np.concatenate([st_val, v2])
    R = {k: np.concatenate([R[k], R2[k]]) for k in R}
    del p2, i2, v2, R2
rooms = rooms + ["OTHER"]
n = len(R["seed"])
fold = R["seed"] % 5
# LABEL (env): z = the fight's end score (default); q = Silver's own root value (the most visited edge's Q after
# the 10,000-simulation search), a per-state label; test RMSE is then against q too.
LABEL = os.environ.get("LABEL", "z")
y = (R["z"] if LABEL == "z" else R["qchosen"] / 100.0).astype(np.float32)
y = np.where(np.isfinite(y), y, 0).astype(np.float32)
print(f"loaded {n} roots, {len(np.unique(R['seed']))} runs ({time.time() - t0:.0f}s)", flush=True)

ck = torch.load(CK, map_location="cpu", weights_only=False)
sd = {k: v.float() for k, v in ck["state"].items()}
s_scale = np.asarray(ck["scales"][0], np.float32)
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INT_COLS = [1668, 1677, 1686, 1695, 1704]
st_root = np.repeat(np.arange(n, dtype=np.int64), np.diff(st_ptr))
mon = np.zeros((n, 10), np.int64)
for k, c in enumerate(ID_COLS + INT_COLS):
    m = st_idx == c
    mon[st_root[m], k] = np.rint(st_val[m]).astype(np.int64) + (1 if k < 5 else 0)
mon = np.clip(mon, 0, 127)
enc = np.zeros(n, np.int64)
m = st_idx == 1
enc[st_root[m]] = np.rint(st_val[m]).astype(np.int64)
enc = np.clip(enc, 0, 127)
del st_root, m
wval = (st_val * s_scale[st_idx]).astype(np.float32)  # per-sample weights as the trunk sees them


class Trunk(nn.Module):
    """relu(policyMlpBase) of g7f_E: state embedding bag + monster and encounter embeddings + act.bias."""

    def __init__(self):
        super().__init__()
        self.emb = nn.EmbeddingBag(1766, 128, mode="sum")
        self.emb.weight.data = sd["state.weight"].clone()
        self.monid = nn.Parameter(sd["monid.weight"].clone())
        self.monint = nn.Parameter(sd["monint.weight"].clone())
        self.monproj = nn.Parameter(sd["monproj.weight"].clone())
        self.encw = nn.Parameter(sd["enc.weight"].clone())
        self.encproj = nn.Parameter(sd["encproj.weight"].clone())
        self.bias = nn.Parameter(sd["act.bias"].clone())

    def forward(self, roots):
        roots = np.asarray(roots, np.int64)
        lo, hi = st_ptr[roots], st_ptr[roots + 1]
        ln = hi - lo
        off = np.concatenate([[0], np.cumsum(ln)[:-1]])
        pos = np.repeat(lo - off, ln) + np.arange(int(ln.sum()))
        hs = self.emb(torch.from_numpy(st_idx[pos]), torch.from_numpy(off),
                      per_sample_weights=torch.from_numpy(wval[pos]))
        mid = torch.from_numpy(mon[roots, :5]); mint = torch.from_numpy(mon[roots, 5:])
        present = (mid > 0).float().unsqueeze(2)
        e = torch.cat([self.monid[mid], self.monint[mint]], 2) * present
        hs = hs + (e @ self.monproj.T).sum(1)
        hs = hs + self.encw[torch.from_numpy(enc[roots])] @ self.encproj.T
        return torch.relu(hs + self.bias)


base_trunk = Trunk()
with torch.no_grad():
    vin = np.concatenate([base_trunk(np.arange(a, min(n, a + 100000))).numpy() for a in range(0, n, 100000)])
print(f"trunk done ({time.time() - t0:.0f}s)", flush=True)

keep = R["refchg"] == 0
fit_both = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep)
fit_all = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep & (R["src"] == 1))
stop = np.flatnonzero((fold == 3) & keep & (R["src"] == 1))
test = np.flatnonzero((fold == 4) & keep & (R["src"] == 1))
print(f"fit {len(fit_all)} (both packs {len(fit_both)}), stop {len(stop)}, test {len(test)}", flush=True)
fit_seeds = np.unique(R["seed"][fit_all])
rs = np.random.default_rng(12345)
perm_seeds = rs.permutation(fit_seeds)


def subset(frac):
    if frac == "both":
        return fit_both
    if frac >= 1:
        return fit_all
    chosen = set(perm_seeds[: int(round(frac * len(perm_seeds)))].tolist())
    return fit_all[np.fromiter((s in chosen for s in R["seed"][fit_all]), bool, len(fit_all))]


act100 = y * 100
root = R["qchosen"].astype(np.float64)


def standardizer(fit):
    mu, sdv = vin[fit].mean(0), vin[fit].std(0)
    inv = np.where(sdv < 1e-3, 0.0, 1.0 / np.maximum(sdv, 1e-3)).astype(np.float32)
    return torch.from_numpy(mu), torch.from_numpy(inv)


def train(name, fit, head_sizes, trunk_trainable, reg=False):
    torch.manual_seed(0)
    mu, inv = standardizer(fit)
    layers, d = ([nn.Dropout(0.1)] if reg else []), 128
    for h in head_sizes:
        layers += [nn.Linear(d, h), nn.ReLU()]
        d = h
    layers.append(nn.Linear(d, 1))
    head = nn.Sequential(*layers)
    trunk = Trunk() if trunk_trainable else None
    params = [{"params": head.parameters(), "lr": 1e-3}]
    if trunk is not None:
        params.append({"params": trunk.parameters(), "lr": 1e-4 if reg else 3e-4,
                       "weight_decay": 1e-4 if reg else 1e-5})
    opt = torch.optim.Adam(params, weight_decay=1e-5)
    X = torch.from_numpy(vin)
    Y = torch.from_numpy(y)

    def feats(ix):
        if trunk is None:
            return (X[torch.from_numpy(ix)] - mu) * inv
        return (trunk(ix) - mu) * inv

    def predict(ix):
        with torch.no_grad():
            return np.concatenate([head(feats(ix[a:a + 32768])).squeeze(1).numpy() for a in range(0, len(ix), 32768)])

    best, best_state, bad, BS = 1e9, None, 0, 1024
    rng = np.random.default_rng(0)
    ep = 0
    for ep in range(100):
        head.train()
        perm = rng.permutation(fit)
        for a in range(0, len(perm), BS):
            bi = perm[a:a + BS]
            loss = ((head(feats(bi)).squeeze(1) - Y[torch.from_numpy(bi)]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        head.eval()
        vl = float(((predict(stop) - y[stop]) ** 2).mean())
        print(f"  {name} epoch {ep} stop-fold RMSE {100 * vl ** 0.5:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if vl < best - 1e-7:
            best, bad = vl, 0
            best_state = ({k: t.clone() for k, t in head.state_dict().items()},
                          {k: t.clone() for k, t in trunk.state_dict().items()} if trunk is not None else None)
        else:
            bad += 1
            if bad >= 5:
                break
    head.load_state_dict(best_state[0])
    if trunk is not None:
        trunk.load_state_dict(best_state[1])
    if os.environ.get("SAVE"):
        torch.save({"head": head.state_dict(), "trunk": trunk.state_dict() if trunk is not None else None,
                    "mu": mu.numpy(), "inv": inv.numpy(), "head_sizes": head_sizes, "reg": reg},
                   os.path.join(OUTDIR, name + ".pt"))
    pred = np.zeros(n, np.float64)
    pred[test] = predict(test) * 100
    if os.environ.get("SAVE"):
        np.savez(os.path.join(OUTDIR, name + "_test_pred.npz"), idx=test, pred=pred[test])
    return pred, {"fit": int(len(fit)), "fitRuns": int(len(np.unique(R["seed"][fit]))), "epochs": ep + 1,
                  "stopRmse": round(100 * best ** 0.5, 3)}


tt = np.minimum(R["turn"][test], 6)
groups = [("all", test)]
groups += [(f"act {a}", test[R["act"][test] == a]) for a in sorted(set(R["act"][test].tolist()))]
groups += [(rooms[r], test[R["room"][test] == r]) for r in sorted(set(R["room"][test].tolist()))]
groups += [(f"turn {t}" if t < 6 else "turn 6+", test[tt == t]) for t in range(7)]
groups += [(f"act {a} {rooms[r]}", test[(R["act"][test] == a) & (R["room"][test] == r)])
           for a in sorted(set(R["act"][test].tolist())) for r in (1, 2)]


def report(pred):
    out = {}
    for g, ix in groups:
        if len(ix) == 0:
            continue
        e = pred[ix] - act100[ix]
        er = root[ix] - act100[ix]
        out[g] = {"roots": int(len(ix)), "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
                  "bias": round(float(e.mean()), 2), "rootDebiasedRmse": round(float(er.std()), 2)}
    return out


SPEC = {"frozen": (1.0, [64], False), "frozen50": (0.5, [64], False), "frozen25": (0.25, [64], False),
        "frozenbig": (1.0, [256, 256], False), "e2e": (1.0, [64], True), "e2e50": (0.5, [64], True),
        "e2e_reg": (1.0, [64], True, True), "e2e_both": ("both", [64], True), "e2e_reg_both": ("both", [64], True, True),
        "frozen_both": ("both", [64], False), "e2e_reg50": (0.5, [64], True, True)}
results = {}
for v in VARIANTS:
    frac, hs, tr = SPEC[v][:3]
    pred, meta = train(v, subset(frac), hs, tr, reg=len(SPEC[v]) > 3)
    results[v] = {"meta": meta, "groups": report(pred)}
    json.dump(results, open(os.path.join(OUTDIR, "diag.json"), "w"), indent=1)
    print(f"{v}: {meta} all {results[v]['groups']['all']}", flush=True)

names = list(results)
print(f"\nfold 4 (test) RMSE, Silver points; rootDeb = Silver's root value with its group bias removed (bounds label noise)")
print(f"{'group':18} {'roots':>7} {'rootDeb':>7} " + " ".join(f"{v:>9}" for v in names))
for g, _ in groups:
    if g not in results[names[0]]["groups"]:
        continue
    s0 = results[names[0]]["groups"][g]
    print(f"{g:18} {s0['roots']:7d} {s0['rootDebiasedRmse']:7.1f} "
          + " ".join(f"{results[v]['groups'][g]['rmse']:9.2f}" for v in names))
print(f"done ({time.time() - t0:.0f}s)")
