#!/usr/bin/env python3
"""X3 part 2, replacement (X3-HALLWAY-FOLLOWUP item 1): HP perturbation of saved combat rows.

usage: nice -n 19 OMP_NUM_THREADS=2 python3 -E x3_part2b.py REPO CKPT SLICE_GLOB [out.json]

On every combat row of the slice, the player's current HP in the input is lowered by d = 1, 5, 10 (rows where the HP
would go below 1 are skipped for that d). Changed input fields: the PLAYER token's float 0 (curHp / 100) and float 2
(curHp / maxHp) (AmberEncoder.cpp); nothing else (the consequence features are HP differences, not levels). The net
is re-evaluated and, per HP removed, the change of
  (a) predicted HP at the end of the current floor (hpf[floor-1] * 255),
  (b) the summed predicted HP over all later floors (sum of hpf[f-1] * 255 for f > floor),
  (c) F = E[final floor] / 57, (d) U = (F + 0.5 H) / 1.5 with H = amberH(floor, hpf)
is reported: mean and median over rows, 95% interval of the mean by bootstrap over runs (2,000, seed 20261128),
overall and by act (floor 1-17 / 18-34 / 35-51 / 52+).
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
d_, layers = am.SIZES.get(a["net"]) or tuple(int(x) for x in a["net"].split("x")[:2])
net = sp.net_like_ckpt(d_, layers, 56, a.get("w_soft_policy", 0) > 0, a)
r = net.load_state_dict(ck["net"], strict=False)
if r.missing_keys or r.unexpected_keys:
    sys.exit("missing/unexpected keys")
am.input_options_from_ckpt(net, ck)
net.sdpa = True
net.eval()
del ck
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
NEED = ("tok_type", "ids", "f", "mask", "a_type", "a_src", "a_tgt", "a_f", "a_mask")
PLAYER, DS = 1, (1, 5, 10)
cls = np.arange(57, dtype=np.float64)
cls[0] = 57.0


def avail():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"):
            return int(l.split()[1]) // 1024


def evaluate(run, f):
    b = {k: (torch.from_numpy(np.ascontiguousarray(run[k].astype(np.int64))) if k in INT
             else torch.from_numpy(np.ascontiguousarray(run[k])).float() if run[k].dtype == np.float16
             else torch.from_numpy(np.ascontiguousarray(run[k]))) for k in NEED}
    b["f"] = torch.from_numpy(np.ascontiguousarray(f)).float()
    with torch.no_grad():
        _, outcome, _, hpf, *_ = net(b)
    p = torch.softmax(outcome.float(), -1).numpy()
    F = (p * cls).sum(1) / 57.0
    return F, hpf.float().clamp(0, 1).numpy()


def metrics(F, hpf, fl):
    n = len(fl)
    cur = hpf[np.arange(n), fl - 1] * 255.0
    later = np.array([hpf[i, fl[i]:].sum() * 255.0 for i in range(n)])
    H = np.array([((fl[i] - 1) + hpf[i, fl[i] - 1:].sum()) / 56.0 for i in range(n)])
    return cur, later, F, (F + 0.5 * H) / 1.5


rows = {d: [] for d in DS}   # (run, act, da, db, dc, dd) per HP removed
runs = 0
for fn in sorted(glob.glob(pat)):
    if avail() < 1500:
        sys.exit("MEMGUARD abort")
    z = np.load(fn)
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    for nm in names:
        run = {k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".")}
        comb = np.where(run["combat"].astype(bool))[0]
        if len(comb) == 0:
            runs += 1
            continue
        sub = {k: run[k][comb] for k in NEED}
        sub_fl = np.clip(run["floor"][comb].astype(int), 1, 56)
        tt = sub["tok_type"]
        pidx = np.array([int(np.argmax(tt[i] == PLAYER)) if (tt[i] == PLAYER).any() else -1 for i in range(len(tt))])
        ok = pidx >= 0
        f0 = sub["f"].astype(np.float32)
        hp = np.where(ok, np.round(f0[np.arange(len(tt)), np.maximum(pidx, 0), 0] * 100), np.nan)
        ratio = f0[np.arange(len(tt)), np.maximum(pidx, 0), 2]
        mx = np.where(ratio > 0, hp / np.maximum(ratio, 1e-6), np.nan)
        base = metrics(*evaluate(sub, f0), sub_fl)
        act = np.where(sub_fl <= 17, 1, np.where(sub_fl <= 34, 2, np.where(sub_fl <= 51, 3, 4)))
        for d in DS:
            keep = ok & (hp - d >= 1) & np.isfinite(mx)
            if not keep.any():
                continue
            f1 = f0.copy()
            ii = np.where(keep)[0]
            f1[ii, pidx[ii], 0] = (hp[ii] - d) / 100.0
            f1[ii, pidx[ii], 2] = (hp[ii] - d) / mx[ii]
            f1 = f1.astype(np.float16).astype(np.float32)   # the stored precision
            pert = metrics(*evaluate(sub, f1), sub_fl)
            for i in ii:
                rows[d].append((runs, act[i], *[(base[k][i] - pert[k][i]) / d for k in range(4)]))
        runs += 1
    print(os.path.basename(fn), runs, "runs", {d: len(v) for d, v in rows.items()}, flush=True)

NAMES = ("a_cur_floor_hp", "b_later_floors_hp", "c_F", "d_U")


def summ(R):
    R = np.array(R)
    if len(R) == 0:
        return None
    by = {}
    for i, r_ in enumerate(R[:, 0].astype(int)):
        by.setdefault(r_, []).append(i)
    groups = list(by.values())
    rng = random.Random(20261128)
    boots = []
    for _ in range(2000):
        idx = np.array([i for g in (rng.choice(groups) for _ in groups) for i in g])
        boots.append(R[idx, 2:].mean(0))
    boots = np.sort(np.array(boots), 0)
    return {nm: dict(mean=float(R[:, 2 + k].mean()), median=float(np.median(R[:, 2 + k])),
                     ci=[float(boots[50, k]), float(boots[1949, k])]) for k, nm in enumerate(NAMES)} | dict(rows=len(R))


res = dict(ckpt=os.path.basename(ckpt), slice=pat, runs=runs,
           note="per HP removed: (base - perturbed) / d; positive = less predicted HP / value at lower HP")
for d in DS:
    R = rows[d]
    res[f"d{d}"] = dict(all=summ(R), **{f"act{a_}": summ([x for x in R if x[1] == a_]) for a_ in (1, 2, 3, 4)})
s = json.dumps(res, indent=1)
print(s)
if out:
    open(out, "w").write(s + "\n")
