"""Gradient noise scale (McCandlish et al. 2018, B_simple = tr(Sigma) / |G|^2) of the live stage-1 AZ training loss,
on CPU, from gathered replay batches (slice_replay.py) and a checkpoint. Read-only: no training step is taken.

For each micro-batch i (b rows drawn uniformly from the window) the gradient g_i of selfplay.losses (the live
weights) is taken at the checkpoint's weights. With M micro-batches:
  |G|^2  ~ (|sum g_i|^2 - sum |g_i|^2) / (M (M - 1))          (unbiased)
  tr S_b ~ (sum |g_i|^2 - M |mean g|^2) / (M - 1)             (covariance trace of a b-row gradient)
  B_simple = b tr S_b / |G|^2                                  (per-sample noise / signal)
Raw gradients and Adam-preconditioned ones (g / (sqrt(v_hat) + eps), v from the checkpoint's optimizer state).
CI: delete-one-group jackknife over groups of micro-batches.

usage: python3 gradnoise_az.py REPO CKPT SLICE_DIR OUT_JSON [MAX_BATCHES] [THREADS]
"""
import glob
import importlib.util
import json
import math
import os
import sys
import time

import numpy as np
import torch

repo, ckpt_path, sdir, out_json = sys.argv[1:5]
MAXB = int(sys.argv[5]) if len(sys.argv) > 5 else 10 ** 9
torch.set_num_threads(int(sys.argv[6]) if len(sys.argv) > 6 else os.cpu_count())

spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
amber_net = sp.amber_net

ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netload  # noqa: E402
net, params, pnames, W, A = netload.build(sp, ck)
net.train()
opt_state = ck["opt"]["state"]
groups = ck["opt"]["param_groups"]
ids = [i for g in groups for i in g["params"]]
assert len(ids) == len(params), (len(ids), len(params))
b2, eps = groups[0]["betas"][1], groups[0]["eps"]
pre = []
for i, p in zip(ids, params):
    s = opt_state.get(i, opt_state.get(str(i)))
    t = float(s["step"])
    v = s["exp_avg_sq"].float() / (1 - b2 ** t)
    pre.append((1.0 / (v.sqrt() + eps)).reshape(-1))
pre = torch.cat(pre)
P = pre.numel()
print(f"# params {P:,}; weights {W}; step {ck['counters']['step']}; run_log_slots {net.run_log_slots}", flush=True)

INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
files = sorted(glob.glob(os.path.join(sdir, "part*.npz")))
gsum = {"raw": [], "pre": []}     # per file (group): sum of g_i
gsq = {"raw": [], "pre": []}      # per file: sum |g_i|^2
gm = []                           # per file: micro-batches
parts_acc = {}
b_rows = None
t0 = time.time()
done = 0
TRANSFORM = os.environ.get("GN_TRANSFORM", "")   # "", "clamp20" or "symlog"
TR_SLOTS = [int(x) for x in os.environ.get("GN_SLOTS", "7").split(",")]
norms_all = []
DUMP = os.environ.get("GN_DUMP")   # optional: every micro-batch's raw gradient (float32 [batches, P]) for re-analysis
dump = np.lib.format.open_memmap(DUMP, mode="w+", dtype=np.float32, shape=(min(MAXB, 1024), P)) if DUMP else None
for fn in files:
    z = np.load(fn)
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    S = {k: torch.zeros(P, dtype=torch.float64) for k in gsum}
    Q = {k: 0.0 for k in gsum}
    m = 0
    for nm in names:
        if done >= MAXB:
            break
        bt = {}
        for k in z.files:
            if not k.startswith(nm + "."):
                continue
            key = k.split(".", 1)[1]
            if key == "abs":
                continue
            v = z[k]
            t = torch.from_numpy(v.astype(np.int64) if (v.dtype.kind in "iu" and key not in ("aux_target",)) else v)
            bt[key] = t.float() if t.dtype == torch.float16 else t
        b_rows = int(bt["outcome"].shape[0])
        if TRANSFORM:   # GN_TRANSFORM: change RUN-token float slots before the forward (offline test)
            run = (bt["tok_type"] == 0) & bt["mask"]
            f = bt["f"].clone()
            for sl in TR_SLOTS:
                x = f[..., sl]
                y = x.clamp(max=20.0) if TRANSFORM == "clamp20" else torch.sign(x) * torch.log1p(x.abs())
                f[..., sl] = torch.where(run, y, x)
            bt["f"] = f
        net.zero_grad(set_to_none=True)
        loss, parts = sp.losses(net, bt, **W)
        loss.backward()
        g = torch.cat([(p.grad if p.grad is not None else torch.zeros_like(p)).reshape(-1) for p in params]).double()
        if not torch.isfinite(g).all():
            print(f"# {nm}: non-finite gradient, skipped", flush=True)
            continue
        if dump is not None and done < len(dump):
            dump[done] = g.float().numpy()
        norms_all.append(float(g @ g))
        gp = g * pre.double()
        for k, x in (("raw", g), ("pre", gp)):
            S[k] += x
            Q[k] += float(x @ x)
        for k, v in parts.items():
            parts_acc[k] = parts_acc.get(k, 0.0) + float(v)
        m += 1
        done += 1
    for k in gsum:
        gsum[k].append(S[k])
        gsq[k].append(Q[k])
    gm.append(m)
    print(f"{os.path.basename(fn)}: {m} batches, total {done} ({time.time() - t0:.0f} s)", flush=True)
    if done >= MAXB:
        break


def est(sums, sqs, ms):
    M = sum(ms)
    St = sum(sums)
    Qt = sum(sqs)
    s2 = float(St @ St)
    G2 = (s2 - Qt) / (M * (M - 1))
    trS = (Qt - s2 / M) / (M - 1)
    return {"G2": G2, "trS_b": trS, "B_simple": b_rows * trS / G2 if G2 > 0 else float("inf"), "M": M}


res = {"ckpt": ckpt_path, "step": ck["counters"]["step"], "b": b_rows, "batches": done,
       "secs": round(time.time() - t0, 1), "loss_parts_mean": {k: v / max(done, 1) for k, v in parts_acc.items()},
       "weights": W, "train_batch_live": A("train_batch"), "lr_live": A("lr")}
na = np.sort(np.array(norms_all))[::-1]
res["transform"] = {"kind": TRANSFORM, "slots": TR_SLOTS}
res["raw_norm2"] = {"median": float(np.median(na)), "max": float(na[0]), "top10_share": float(na[:10].sum() / na.sum())}
for k in gsum:
    full = est(gsum[k], gsq[k], gm)
    G = len(gm)
    if G > 2 and full["G2"] > 0:
        jk = []
        for i in range(G):
            sel = [j for j in range(G) if j != i]
            e = est([gsum[k][j] for j in sel], [gsq[k][j] for j in sel], [gm[j] for j in sel])
            jk.append(math.log(e["B_simple"]) if e["G2"] > 0 else float("nan"))
        jk = np.array(jk)
        if np.isfinite(jk).all():
            se = math.sqrt((G - 1) / G * ((jk - jk.mean()) ** 2).sum())
            full["B_simple_ci95_jackknife"] = [math.exp(math.log(full["B_simple"]) - 1.96 * se),
                                               math.exp(math.log(full["B_simple"]) + 1.96 * se)]
        else:
            full["B_simple_ci95_jackknife"] = "a leave-one-group-out |G|^2 estimate was <= 0"
    res[k] = full
print(json.dumps(res, indent=1), flush=True)
with open(out_json, "w") as fh:
    json.dump(res, fh, indent=1)
