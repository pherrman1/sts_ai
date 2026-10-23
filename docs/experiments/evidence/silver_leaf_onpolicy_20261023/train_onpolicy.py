#!/usr/bin/env python3
"""On-policy leaf round 1 (README analysis steps 3-4): the searched-value head on production states and on the
states the head's own play reaches.

PACK is the production-combat pack (a20prod, `../silver_leaf_label_data_20261023/build_pack.sh prod`), ONPOL the
pack of this campaign (`../silver_leaf_a20_data_20261022/pack_a20.py` on its units: root rows whose `edges` are the
production label search's). Both are labelled with Silver's root value (`qchosen`, the most visited edge's Q of the
production search, / 100), folds seed % 5 (0-2 fit, 3 early stop, 4 test), reference-change roots left out.
Recipe, layers and initialisation are diag2.py's `e2e` with LABEL=q (the `qe2e` net of §664): head 128-64-1 on the
g7f_E trunk, trunk trained too, started from g7f_E. Variants (VARIANTS env, comma list; default all three):
  qe2e      the saved §664 checkpoint (QE2E env, checkpoints/q_e2e.pt on the share), evaluated only
  ref       the qe2e recipe refit on PACK's folds (stop on PACK's fold 3): the retrain noise of the reference
  onpolicy  the same recipe fit on both packs' folds 0-2, early stop on both packs' fold 3
Each is reported on fold 4 of each pack separately (RMSE and bias against the label, Silver points, by act, room and
turn). SAVE=1 writes OUTDIR/<variant>.pt as diag2.py does (export with ../silver_leaf_label_data_20261023/
export_e2e.py).

usage: train_onpolicy.py PACK.npz ONPOL.npz MODEL.pt OUTDIR
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
PACK, ONPOL, CK, OUTDIR = sys.argv[1:5]
os.makedirs(OUTDIR, exist_ok=True)
VARIANTS = os.environ.get("VARIANTS", "qe2e,ref,onpolicy").split(",")


def load(path):
    z = np.load(path)
    return (z["st_ptr"].astype(np.int64), z["st_idx"].astype(np.int64), z["st_val"].astype(np.float32),
            {k[2:]: z[k] for k in z.files if k.startswith("r_") and k != "r_enc"}, [str(r) for r in z["rooms"]])


st_ptr, st_idx, st_val, R, rooms = load(PACK)
R["src"] = np.ones(len(R["seed"]), np.int64)
p2, i2, v2, R2, rooms2 = load(ONPOL)
assert rooms2 == rooms
R2["src"] = np.full(len(R2["seed"]), 2, np.int64)
assert not set(np.unique(R["seed"]).tolist()) & set(np.unique(R2["seed"]).tolist()), "packs share seeds"
st_ptr = np.concatenate([st_ptr, p2[1:] + st_ptr[-1]])
st_idx = np.concatenate([st_idx, i2]); st_val = np.concatenate([st_val, v2])
R = {k: np.concatenate([R[k], R2[k]]) for k in R}
del p2, i2, v2, R2
rooms = rooms + ["OTHER"]
n = len(R["seed"])
fold = R["seed"] % 5
y = (R["qchosen"] / 100.0).astype(np.float32)
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


keep = R["refchg"] == 0
fit_prod = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep & (R["src"] == 1))
fit_both = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep)
stop_prod = np.flatnonzero((fold == 3) & keep & (R["src"] == 1))
stop_both = np.flatnonzero((fold == 3) & keep)
tests = {"prod": np.flatnonzero((fold == 4) & keep & (R["src"] == 1)),
         "onpolicy": np.flatnonzero((fold == 4) & keep & (R["src"] == 2))}
print(f"fit {len(fit_prod)} / both {len(fit_both)}, stop {len(stop_prod)} / both {len(stop_both)}, "
      f"test prod {len(tests['prod'])}, test on-policy {len(tests['onpolicy'])}", flush=True)
base = Trunk()
with torch.no_grad():
    vin = np.concatenate([base(np.arange(a, min(n, a + 100000))).numpy() for a in range(0, n, 100000)])
print(f"trunk done ({time.time() - t0:.0f}s)", flush=True)
Y = torch.from_numpy(y)


def make_head():
    return nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))


def predictor(head, trunk, mu, inv):
    def predict(ix):
        with torch.no_grad():
            return np.concatenate([head((trunk(ix[a:a + 32768]) - mu) * inv).squeeze(1).numpy()
                                   for a in range(0, len(ix), 32768)])
    return predict


def train(name, fit, stop):
    """diag2.py's e2e: Adam, head lr 1e-3, trunk lr 3e-4 (weight decay 1e-5), batch 1024, patience 5."""
    torch.manual_seed(0)
    mu, sdv = vin[fit].mean(0), vin[fit].std(0)
    inv = torch.from_numpy(np.where(sdv < 1e-3, 0.0, 1.0 / np.maximum(sdv, 1e-3)).astype(np.float32))
    mu = torch.from_numpy(mu)
    head, trunk = make_head(), Trunk()
    opt = torch.optim.Adam([{"params": head.parameters(), "lr": 1e-3},
                            {"params": trunk.parameters(), "lr": 3e-4, "weight_decay": 1e-5}], weight_decay=1e-5)
    predict = predictor(head, trunk, mu, inv)
    best, best_state, bad, BS = 1e9, None, 0, 1024
    rng = np.random.default_rng(0)
    ep = 0
    for ep in range(100):
        head.train()
        perm = rng.permutation(fit)
        for a in range(0, len(perm), BS):
            bi = perm[a:a + BS]
            loss = ((head((trunk(bi) - mu) * inv).squeeze(1) - Y[torch.from_numpy(bi)]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        head.eval()
        vl = float(((predict(stop) - y[stop]) ** 2).mean())
        print(f"  {name} epoch {ep} stop-fold RMSE {100 * vl ** 0.5:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if vl < best - 1e-7:
            best, bad = vl, 0
            best_state = ({k: t.clone() for k, t in head.state_dict().items()},
                          {k: t.clone() for k, t in trunk.state_dict().items()})
        else:
            bad += 1
            if bad >= 5:
                break
    head.load_state_dict(best_state[0])
    trunk.load_state_dict(best_state[1])
    if os.environ.get("SAVE"):
        torch.save({"head": head.state_dict(), "trunk": trunk.state_dict(), "mu": mu.numpy(), "inv": inv.numpy(),
                    "head_sizes": [64], "reg": False}, os.path.join(OUTDIR, name + ".pt"))
    return predict, {"fit": int(len(fit)), "fitRuns": int(len(np.unique(R["seed"][fit]))), "epochs": ep + 1,
                     "stopRoots": int(len(stop)), "stopRmse": round(100 * best ** 0.5, 3)}


def saved(path):
    """A diag2.py SAVE=1 checkpoint (head 128-64-1 and trunk), evaluated only."""
    c = torch.load(path, map_location="cpu", weights_only=False)
    head, trunk = make_head(), Trunk()
    head.load_state_dict(c["head"]); trunk.load_state_dict(c["trunk"])
    head.eval()
    return predictor(head, trunk, torch.from_numpy(c["mu"]), torch.from_numpy(c["inv"])), {"checkpoint": path}


def groups(test):
    tt = np.minimum(R["turn"][test], 6)
    out = [("all", test)]
    out += [(f"act {a}", test[R["act"][test] == a]) for a in sorted(set(R["act"][test].tolist()))]
    out += [(rooms[r], test[R["room"][test] == r]) for r in sorted(set(R["room"][test].tolist()))]
    out += [(f"turn {t}" if t < 6 else "turn 6+", test[tt == t]) for t in range(7)]
    out += [(f"act {a} {rooms[r]}", test[(R["act"][test] == a) & (R["room"][test] == r)])
            for a in sorted(set(R["act"][test].tolist())) for r in (1, 2)]
    return [(g, ix) for g, ix in out if len(ix)]


def report(name, predict):
    out = {}
    for t, test in tests.items():
        pred = predict(test) * 100
        if os.environ.get("SAVE"):
            np.savez(os.path.join(OUTDIR, f"{name}_{t}_test_pred.npz"), idx=test, pred=pred)
        full = np.zeros(n); full[test] = pred
        out[t] = {}
        for g, ix in groups(test):
            e = full[ix] - y[ix] * 100
            out[t][g] = {"roots": int(len(ix)), "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
                         "bias": round(float(e.mean()), 2)}
    return out


results = {}
for name in VARIANTS:
    if name == "qe2e":
        predict, meta = saved(os.environ["QE2E"])
    elif name == "ref":
        predict, meta = train(name, fit_prod, stop_prod)
    elif name == "onpolicy":
        predict, meta = train(name, fit_both, stop_both)
    else:
        raise SystemExit(f"unknown variant {name}")
    results[name] = {"meta": meta, "test": report(name, predict)}
    json.dump(results, open(os.path.join(OUTDIR, "onpolicy.json"), "w"), indent=1)
    print(f"{name}: {meta} prod {results[name]['test']['prod']['all']} "
          f"on-policy {results[name]['test']['onpolicy']['all']}", flush=True)

names = list(results)
for t in tests:
    print(f"\nfold 4 of the {t} pack, RMSE against the production label, Silver points")
    print(f"{'group':18} {'roots':>7} " + " ".join(f"{v:>9}" for v in names))
    for g, _ in groups(tests[t]):
        s0 = results[names[0]]["test"][t][g]
        print(f"{g:18} {s0['roots']:7d} " + " ".join(f"{results[v]['test'][t][g]['rmse']:9.2f}" for v in names))
print(f"done ({time.time() - t0:.0f}s)")
