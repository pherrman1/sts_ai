#!/usr/bin/env python3
"""Leaf value head on the frozen g7f_E trunk from the silver-leaf-a20 pack (README analysis steps 3 and 5).

Trunk: relu(policyMlpBase) of g7f_E (state block, monster and encounter embeddings), as in the probe and the capacity
test. Head 128 -> 64 -> 1 on the trunk standardized over the fit folds (units without spread there muted), MSE on
z = score / 100. fold = seed % 5: folds 0-2 fit, 3 stops early, 4 tests; refchg roots are left out. Reports fold-4
RMSE and bias (prediction - actual, Silver points) by act, room, turn, turn start vs mid-turn and variant, next to
Silver's own root value (the most visited edge's Q) and the fit-fold mean; and, descriptively, the fold-4 means of
head, root value and actual score by act, room and turn. Writes the head as silver_value_head_v1 (scale 100) for
exact_combat_solver --leaf-heads.

usage: train_head_a20.py PACK.npz MODEL.pt OUT.txt REPORT.json
"""
import json
import sys
import time

import numpy as np
import torch

torch.set_num_threads(4)
nn = torch.nn
t0 = time.time()
PACK, CK, OUT, REPORT = sys.argv[1:5]
z = np.load(PACK)
st_ptr = z["st_ptr"].astype(np.int64)
st_idx = z["st_idx"].astype(np.int64)
st_val = z["st_val"].astype(np.float32)
R = {k[2:]: z[k] for k in z.files if k.startswith("r_")}
rooms = [str(r) for r in z["rooms"]] + ["OTHER"]
n = len(R["seed"])
fold = R["seed"] % 5
y = R["z"].astype(np.float32)
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

emb = nn.EmbeddingBag(1766, 128, mode="sum")
emb.weight.data = sd["state.weight"]
vin = np.zeros((n, 128), np.float32)
CH = 200000
with torch.no_grad():
    for a in range(0, n, CH):
        b = min(n, a + CH)
        lo, hi = st_ptr[a], st_ptr[b]
        hs = emb(torch.from_numpy(st_idx[lo:hi]), torch.from_numpy(st_ptr[a:b] - lo),
                 per_sample_weights=torch.from_numpy(st_val[lo:hi] * s_scale[st_idx[lo:hi]]))
        mid = torch.from_numpy(mon[a:b, :5]); mint = torch.from_numpy(mon[a:b, 5:])
        present = (mid > 0).float().unsqueeze(2)
        e = torch.cat([sd["monid.weight"][mid], sd["monint.weight"][mint]], 2) * present
        hs = hs + (e @ sd["monproj.weight"].T).sum(1)
        hs = hs + sd["enc.weight"][torch.from_numpy(enc[a:b])] @ sd["encproj.weight"].T
        vin[a:b] = torch.relu(hs + sd["act.bias"]).numpy()
del st_idx, st_val, mon
print(f"trunk done ({time.time() - t0:.0f}s)", flush=True)

# Roots whose gold or max HP moved within the fight (refchg) carry labels off the tree's own reference: left out.
keep = R["refchg"] == 0 if "refchg" in R else np.ones(n, bool)
fit = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep)
stop = np.flatnonzero((fold == 3) & keep)
test = np.flatnonzero((fold == 4) & keep)
print(f"refchg roots left out: {int((~keep).sum())}", flush=True)
# Units that never fire on the fit folds are muted (inv_sd 0), so a rare test state cannot blow them up.
mu, sdv = vin[fit].mean(0), vin[fit].std(0)
inv = np.where(sdv < 1e-3, 0.0, 1.0 / np.maximum(sdv, 1e-3)).astype(np.float32)
print(f"trunk units muted (no spread on the fit folds): {int((inv == 0).sum())}", flush=True)
vin -= mu
vin *= inv
X, Y = torch.from_numpy(vin), torch.from_numpy(y)

torch.manual_seed(0)
net = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))
opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-5)
best, best_state, bad, BS = 1e9, None, 0, 1024
rng = np.random.default_rng(0)
for ep in range(100):
    net.train()
    perm = rng.permutation(fit)
    for a in range(0, len(perm), BS):
        bi = torch.from_numpy(perm[a:a + BS])
        loss = ((net(X[bi]).squeeze(1) - Y[bi]) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    net.eval()
    with torch.no_grad():
        vl = ((net(X[stop]).squeeze(1) - Y[stop]) ** 2).mean().item()
    print(f"  epoch {ep} stop-fold RMSE {100 * vl ** 0.5:.3f} points ({time.time() - t0:.0f}s)", flush=True)
    if vl < best - 1e-7:
        best, bad = vl, 0
        best_state = {k: t.clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= 5:
            break
net.load_state_dict(best_state)
with torch.no_grad():
    pred = np.concatenate([net(X[a:a + 65536]).squeeze(1).numpy() for a in range(0, n, 65536)]) * 100
act100 = y * 100
root = R["qchosen"].astype(np.float64)
const = float(act100[fit].mean())


def summ(ix):
    if len(ix) == 0:
        return None
    eh, er, ec = pred[ix] - act100[ix], root[ix] - act100[ix], const - act100[ix]
    return {"roots": int(len(ix)), "fights": int(len({(R["var"][i], R["seed"][i], R["fight"][i]) for i in ix})),
            "actual": round(float(act100[ix].mean()), 2), "head": round(float(pred[ix].mean()), 2),
            "rootQ": round(float(root[ix].mean()), 2),
            "headRmse": round(float(np.sqrt((eh ** 2).mean())), 2), "headBias": round(float(eh.mean()), 2),
            "rootRmse": round(float(np.sqrt((er ** 2).mean())), 2), "rootBias": round(float(er.mean()), 2),
            "constRmse": round(float(np.sqrt((ec ** 2).mean())), 2)}


groups = {"all": [("all", test)]}
groups["act"] = [(f"act {a}", test[R["act"][test] == a]) for a in sorted(set(R["act"][test].tolist()))]
groups["room"] = [(rooms[r], test[R["room"][test] == r]) for r in sorted(set(R["room"][test].tolist()))]
tt = np.minimum(R["turn"][test], 6)
groups["turn"] = [(f"turn {t}" if t < 6 else "turn 6+", test[tt == t]) for t in range(7)]
groups["turnStart"] = [("turn start", test[R["tstart"][test] == 1]), ("mid-turn", test[R["tstart"][test] == 0])]
groups["variant"] = [("natural", test[R["var"][test] == 0]), ("perturbed", test[R["var"][test] == 1])]
groups["actRoom"] = [(f"act {a} {rooms[r]}", test[(R["act"][test] == a) & (R["room"][test] == r)])
                     for a in sorted(set(R["act"][test].tolist())) for r in sorted(set(R["room"][test].tolist()))]
report = {"pack": PACK, "roots": int(n), "refchgLeftOut": int((~keep).sum()), "fit": int(len(fit)),
          "stop": int(len(stop)), "test": int(len(test)),
          "stopRmse": round(100 * best ** 0.5, 3), "epochs": ep + 1, "fitMean": round(const, 2), "groups": {}}
print(f"best stop-fold RMSE {100 * best ** 0.5:.3f} points; fold 4 (test), Silver points; bias = prediction - actual")
print(f"{'group':24} {'roots':>8} {'fights':>7} {'actual':>7} {'head':>7} {'rootQ':>7} {'headRMSE':>9} {'headBias':>9}"
      f" {'rootRMSE':>9} {'rootBias':>9} {'constRMSE':>9}")
for g, items in groups.items():
    report["groups"][g] = {}
    for name, ix in items:
        s = summ(ix)
        if s is None:
            continue
        report["groups"][g][name] = s
        print(f"{name:24} {s['roots']:8d} {s['fights']:7d} {s['actual']:7.1f} {s['head']:7.1f} {s['rootQ']:7.1f}"
              f" {s['headRmse']:9.2f} {s['headBias']:+9.2f} {s['rootRmse']:9.2f} {s['rootBias']:+9.2f}"
              f" {s['constRmse']:9.2f}")
json.dump(report, open(REPORT, "w"), indent=1)

w1, b1 = net[0].weight.detach().numpy(), net[0].bias.detach().numpy()
w2, b2 = net[2].weight.detach().numpy()[0], net[2].bias.detach().numpy()[0]
with open(OUT, "w") as f:
    f.write("silver_value_head_v1\nin 128\nhidden 64\n")
    for key, v in (("mu", mu), ("inv_sd", inv), ("w1", w1), ("b1", b1), ("w2", w2), ("b2", np.atleast_1d(b2))):
        f.write(key + " " + " ".join(f"{x:.9g}" for x in np.asarray(v, np.float64).ravel()) + "\n")
    f.write("scale 100\noffset 0\n")
print(f"wrote {OUT} and {REPORT} ({time.time() - t0:.0f}s)")
