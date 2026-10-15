"""Fit a per-(card id, upgraded) score table to Silver's card-play choices; compare to the greedy table.

Usage: python3 -I fit_card_table.py CHOICES.json OUT.json
Train on workers w01-w06, test on w07-w08 (split by worker = by seed block).
"""
import json, sys
import numpy as np

d = json.load(open(sys.argv[1]))
play_map = {int(k): v for k, v in d["play_map"].items()}
rows = d["rows"]
K = 400 * 2
def key(o): return o[0] * 2 + int(o[1])
def greedy_prio(o): return 2 * play_map.get(o[0], 0) - (1 if o[1] else 0)   # lower plays first

M = max(len(r["opts"]) for r in rows)
def arrays(rs):
    n = len(rs)
    keys = np.zeros((n, M), np.int64); mask = np.zeros((n, M), bool); lab = np.zeros(n, np.int64)
    gp = np.full((n, M), 1e9)
    for i, r in enumerate(rs):
        for j, o in enumerate(r["opts"]):
            keys[i, j] = key(o); mask[i, j] = True; gp[i, j] = greedy_prio(o)
            if o == r["label"]: lab[i] = j
    return keys, mask, lab, gp

test_w = {"gen6-out-w07", "gen6-out-w08"}
tr = [r for r in rows if r["w"] not in test_w]; te = [r for r in rows if r["w"] in test_w]
ktr, mtr, ltr, _ = arrays(tr); kte, mte, lte, gte = arrays(te)

w = np.zeros(K); g2 = np.full(K, 1e-8); lr = 0.5
for ep in range(40):
    s = np.where(mtr, w[ktr], -np.inf)
    s -= s.max(1, keepdims=True); p = np.exp(s); p /= p.sum(1, keepdims=True)
    grad_rows = -p; grad_rows[np.arange(len(ltr)), ltr] += 1
    grad = np.zeros(K); np.add.at(grad, ktr[mtr], grad_rows[mtr])
    grad -= 1e-4 * len(ltr) * w            # L2
    g2 += grad ** 2; w += lr * grad / np.sqrt(g2)

def acc_learned(keys, mask, lab):
    s = np.where(mask, w[keys], -np.inf); return float((s.argmax(1) == lab).mean())
def acc_greedy(gp, lab):
    return float((gp.argmin(1) == lab).mean())
def acc_freq(keys, mask, lab):   # baseline: always pick the option Silver picks most often overall
    cnt = np.bincount(ktr[np.arange(len(ltr)), ltr], minlength=K).astype(float)
    s = np.where(mask, cnt[keys], -np.inf); return float((s.argmax(1) == lab).mean())

nopt = mte.sum(1)
res = {"train_rows": len(tr), "test_rows": len(te),
       "test_top1_greedy_table": acc_greedy(gte, lte),
       "test_top1_learned_table": acc_learned(kte, mte, lte),
       "test_top1_pick_frequency": acc_freq(kte, mte, lte),
       "test_top1_random": float((1.0 / nopt).mean()),
       "test_mean_options": float(nopt.mean())}
by_act = {}
for a in (1, 2, 3, 4):
    idx = np.array([r["act"] == a for r in te])
    if idx.sum() > 0:
        by_act[a] = {"n": int(idx.sum()), "greedy": float((gte[idx].argmin(1) == lte[idx]).mean()),
                     "learned": acc_learned(kte[idx], mte[idx], lte[idx])}
res["by_act"] = by_act
json.dump({"result": res, "weights": {int(i): float(w[i]) for i in np.nonzero(w)[0]}}, open(sys.argv[2], "w"))
print(json.dumps(res, indent=1))
