#!/usr/bin/env python3
"""X3 part 2 (WORKPLAN-2): does the per-floor HP head follow current HP inside a fight?

usage: nice -n 19 OMP_NUM_THREADS=2 python3 -E x3_part2.py REPO CKPT SLICE_GLOB [out.json]

Rows: the saved replay slices (backup_1p2m_20261127, as W5), in each run's stored order. Consecutive kept combat rows
of the same run and floor (the same fight; act-3 double bosses are on two floors) give pairs (t, t+1). Current HP =
the PLAYER token's float 0 * 100 (AmberEncoder.cpp: curHp / 100). Predicted HP for the current floor = hpf[floor-1]
* 255 (E[HP_f], amber utility). Per pair: dP = change of the predicted current-floor HP, dA = change of the actual
current HP; pooled OLS slope of dP on dA and Pearson correlation, 95% interval by bootstrap over runs (2,000,
seed 20261128); and std(0.5 * dH) against std(dF) over the same pairs (H = amberH, F = E[final floor] / 57).
Memory guard: aborts if MemAvailable < 1.5 GB.
"""
import glob, importlib.util, json, os, random, sys

import numpy as np
import torch

repo, ckpt, pat = sys.argv[1:4]
out = sys.argv[4] if len(sys.argv) > 4 else None
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "2")))
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
am = sp.amber_net
ck = torch.load(ckpt, map_location="cpu", weights_only=False)
a = ck["args"] if isinstance(ck["args"], dict) else vars(ck["args"])
d, layers = am.SIZES.get(a["net"]) or tuple(int(x) for x in a["net"].split("x")[:2])
net = sp.net_like_ckpt(d, layers, 56, a.get("w_soft_policy", 0) > 0, a)
r = net.load_state_dict(ck["net"], strict=False)
if r.missing_keys or r.unexpected_keys:
    sys.exit("missing/unexpected keys")
am.input_options_from_ckpt(net, ck)
net.sdpa = True
net.eval()
del ck
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
NEED = ("tok_type", "ids", "f", "mask", "a_type", "a_src", "a_tgt", "a_f", "a_mask")
PLAYER = 1


def avail():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"):
            return int(l.split()[1]) // 1024


pairs = []   # (run, dP, dA, dF, dHhalf)
runs = 0
for fn in sorted(glob.glob(pat)):
    if avail() < 1500:
        sys.exit("MEMGUARD abort")
    z = np.load(fn)
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    for nm in names:
        run = {k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".")}
        comb = run["combat"].astype(bool)
        if comb.sum() < 2:
            continue
        b = {k: (torch.from_numpy(np.ascontiguousarray(run[k].astype(np.int64))) if k in INT
                 else torch.from_numpy(np.ascontiguousarray(run[k])).float() if run[k].dtype == np.float16
                 else torch.from_numpy(np.ascontiguousarray(run[k]))) for k in NEED}
        with torch.no_grad():
            _, outcome, _, hpf, *_ = net(b)
        p = torch.softmax(outcome.float(), -1).numpy()
        cls = np.arange(p.shape[1], dtype=np.float64)
        cls[0] = 57.0
        F = (p * cls).sum(1) / 57.0
        hpf = hpf.float().clamp(0, 1).numpy()
        floor = run["floor"].astype(int)
        tt = run["tok_type"]
        cur = np.array([float(run["f"][i][np.argmax(tt[i] == PLAYER)][0]) * 100 if (tt[i] == PLAYER).any() else np.nan
                        for i in range(len(tt))])
        fl = np.clip(floor, 1, 56)
        pred = hpf[np.arange(len(fl)), fl - 1] * 255.0
        H = np.array([((f - 1) + hpf[i, f - 1:].sum()) / 56.0 for i, f in enumerate(fl)])
        for i in range(len(fl) - 1):
            if comb[i] and comb[i + 1] and floor[i] == floor[i + 1] and np.isfinite(cur[i]) and np.isfinite(cur[i + 1]):
                pairs.append((runs, pred[i + 1] - pred[i], cur[i + 1] - cur[i], F[i + 1] - F[i], 0.5 * (H[i + 1] - H[i])))
        runs += 1
    print(os.path.basename(fn), runs, "runs", len(pairs), "pairs", flush=True)
P = np.array(pairs)
rid, dP, dA, dF, dHh = P[:, 0].astype(int), P[:, 1], P[:, 2], P[:, 3], P[:, 4]


def stats(idx):
    x, y = dA[idx], dP[idx]
    vx = ((x - x.mean()) ** 2).sum()
    return (((x - x.mean()) * (y - y.mean())).sum() / vx if vx > 0 else np.nan,
            np.corrcoef(x, y)[0, 1] if x.std() > 0 and y.std() > 0 else np.nan)


by = {}
for i, r_ in enumerate(rid):
    by.setdefault(r_, []).append(i)
groups = list(by.values())
rng = random.Random(20261128)
bs, bc = [], []
for _ in range(2000):
    idx = np.array([i for g in (rng.choice(groups) for _ in groups) for i in g])
    s_, c_ = stats(idx)
    bs.append(s_); bc.append(c_)
bs.sort(); bc.sort()
s0, c0 = stats(np.arange(len(dA)))
moved = dA != 0
res = dict(ckpt=os.path.basename(ckpt), slice=pat, runs=runs, pairs=len(pairs), pairs_hp_changed=int(moved.sum()),
           slope_dPred_per_dHP=float(s0), slope_ci=[float(bs[50]), float(bs[1949])],
           corr=float(c0), corr_ci=[float(bc[50]), float(bc[1949])],
           slope_hp_changed_only=float(stats(np.where(moved)[0])[0]),
           std_half_dH=float(dHh.std()), std_dF=float(dF.std()), ratio=float(dHh.std() / dF.std()) if dF.std() > 0 else None)
s = json.dumps(res, indent=1)
print(s)
if out:
    open(out, "w").write(s + "\n")
