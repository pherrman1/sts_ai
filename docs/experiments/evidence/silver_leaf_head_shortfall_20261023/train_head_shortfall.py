#!/usr/bin/env python3
"""Shortfall head: how far below its win-now value a fight ends, on the frozen g7f_E trunk (README).

As train_head_a20.py (same trunk, 128 -> 64 -> 1 head, folds, early stopping, refchg roots left out), but the target is
d = (winnow - score) / 100: winnow is the root's win-now value (SilverSearcher::winNowValue, the pack's r_winnow) and
score the fight's end score, so d is what the rest of the fight costs. As a leaf value the head is worth
winnow - 100 max(0, d): never above winning now, which a search could otherwise exploit by not ending fights.
Roots without a win-now value are left out. Reports, on fold 4 and next to the plain head HEAD.txt (and that head
capped at win-now), RMSE and bias of the implied value against the actual score by act, room and turn, the share of
roots whose actual score lies above win-now (healing, Feed), and writes the head as silver_value_head_v1 with
"target shortfall".

usage: train_head_shortfall.py PACK.npz MODEL.pt HEAD.txt OUT.txt REPORT.json
"""
import json
import sys
import time

import numpy as np
import torch

torch.set_num_threads(2)
nn = torch.nn
t0 = time.time()
PACK, CK, HEAD, OUT, REPORT = sys.argv[1:6]
z = np.load(PACK)
st_ptr = z["st_ptr"].astype(np.int64)
st_idx = z["st_idx"].astype(np.int64)
st_val = z["st_val"].astype(np.float32)
R = {k[2:]: z[k] for k in z.files if k.startswith("r_")}
rooms = [str(r) for r in z["rooms"]] + ["OTHER"]
n = len(R["seed"])
fold = R["seed"] % 5
score = R["z"].astype(np.float64) * 100
win = R["winnow"].astype(np.float64)
d = ((win - score) / 100).astype(np.float32)
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


def plain_head(path, x):
    """The plain head's value (Silver points) of trunk rows x, from its silver_value_head_v1 file."""
    tok = open(path).read().split()
    i = 0

    def take(name, cnt):
        nonlocal i
        assert tok[i] == name, (tok[i], name)
        v = np.array(tok[i + 1:i + 1 + cnt], np.float64)
        i += 1 + cnt
        return v
    assert tok[0] == "silver_value_head_v1"
    nin, hid = int(tok[2]), int(tok[4])
    i = 5
    mu_, inv_ = take("mu", nin), take("inv_sd", nin)
    w1 = take("w1", hid * nin).reshape(hid, nin)
    b1, w2, b2 = take("b1", hid), take("w2", hid), take("b2", 1)
    scale, offset = float(tok[i + 1]), float(tok[i + 3])
    h = np.maximum(((x - mu_) * inv_) @ w1.T + b1, 0)
    return scale * (h @ w2 + b2[0]) + offset


plain = np.concatenate([plain_head(HEAD, vin[a:a + 65536].astype(np.float64)) for a in range(0, n, 65536)])

keep = (R["refchg"] == 0) & np.isfinite(win)
fit = np.flatnonzero(np.isin(fold, [0, 1, 2]) & keep)
stop = np.flatnonzero((fold == 3) & keep)
test = np.flatnonzero((fold == 4) & keep)
print(f"left out: refchg {int((R['refchg'] != 0).sum())}, no win-now {int((~np.isfinite(win)).sum())}", flush=True)
mu, sdv = vin[fit].mean(0), vin[fit].std(0)
inv = np.where(sdv < 1e-3, 0.0, 1.0 / np.maximum(sdv, 1e-3)).astype(np.float32)
vin -= mu
vin *= inv
X, Y = torch.from_numpy(vin), torch.from_numpy(d)

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
    print(f"  epoch {ep} stop-fold shortfall RMSE {100 * vl ** 0.5:.3f} points ({time.time() - t0:.0f}s)", flush=True)
    if vl < best - 1e-7:
        best, bad = vl, 0
        best_state = {k: t.clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= 5:
            break
net.load_state_dict(best_state)
with torch.no_grad():
    dhat = np.concatenate([net(X[a:a + 65536]).squeeze(1).numpy() for a in range(0, n, 65536)]).astype(np.float64)
value = win - 100 * np.maximum(0, dhat)
capped = np.minimum(plain, win)


def summ(ix):
    if len(ix) == 0:
        return None
    out = {"roots": int(len(ix)), "actual": round(float(score[ix].mean()), 2),
           "aboveWinNow": round(float((score[ix] > win[ix] + 0.5).mean()), 4)}
    for name, p in (("shortfall", value), ("plain", plain), ("plainCapped", capped)):
        e = p[ix] - score[ix]
        out[name + "Rmse"] = round(float(np.sqrt((e ** 2).mean())), 2)
        out[name + "Bias"] = round(float(e.mean()), 2)
    out["plainAboveWinNow"] = round(float((plain[ix] > win[ix]).mean()), 4)
    return out


groups = {"all": [("all", test)]}
groups["act"] = [(f"act {a}", test[R["act"][test] == a]) for a in sorted(set(R["act"][test].tolist()))]
groups["room"] = [(rooms[r], test[R["room"][test] == r]) for r in sorted(set(R["room"][test].tolist()))]
tt = np.minimum(R["turn"][test], 6)
groups["turn"] = [(f"turn {t}" if t < 6 else "turn 6+", test[tt == t]) for t in range(7)]
report = {"pack": PACK, "head": HEAD, "roots": int(n), "fit": int(len(fit)), "stop": int(len(stop)),
          "test": int(len(test)), "stopShortfallRmse": round(100 * best ** 0.5, 3), "epochs": ep + 1, "groups": {}}
print(f"fold 4 (test), Silver points; bias = prediction - actual; shortfall value = winnow - 100 max(0, d)")
print(f"{'group':12} {'roots':>7} {'actual':>7} {'>win':>6} {'sfRMSE':>7} {'sfBias':>7} {'plRMSE':>7} {'plBias':>7}"
      f" {'capRMSE':>7} {'capBias':>7} {'pl>win':>6}")
for g, items in groups.items():
    report["groups"][g] = {}
    for name, ix in items:
        s = summ(ix)
        if s is None:
            continue
        report["groups"][g][name] = s
        print(f"{name:12} {s['roots']:7d} {s['actual']:7.1f} {s['aboveWinNow']:6.3f} {s['shortfallRmse']:7.2f}"
              f" {s['shortfallBias']:7.2f} {s['plainRmse']:7.2f} {s['plainBias']:7.2f} {s['plainCappedRmse']:7.2f}"
              f" {s['plainCappedBias']:7.2f} {s['plainAboveWinNow']:6.3f}")
json.dump(report, open(REPORT, "w"), indent=1)
W1 = net[0].weight.detach().numpy().astype(np.float64)
b1 = net[0].bias.detach().numpy().astype(np.float64)
w2 = net[2].weight.detach().numpy().astype(np.float64)[0]
b2 = float(net[2].bias.detach().numpy()[0])
with open(OUT, "w") as f:
    f.write(f"silver_value_head_v1 in 128 hidden 64\n")
    for name, arr in (("mu", mu), ("inv_sd", inv), ("w1", W1.reshape(-1)), ("b1", b1), ("w2", w2), ("b2", [b2])):
        f.write(name + " " + " ".join(f"{float(x):.9g}" for x in arr) + "\n")
    f.write("scale 100 offset 0\ntarget shortfall\n")
print(f"wrote {OUT} and {REPORT} ({time.time() - t0:.0f}s)")
