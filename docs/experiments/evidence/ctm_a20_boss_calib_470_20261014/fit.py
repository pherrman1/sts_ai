#!/usr/bin/env python3
"""§470: MLE boss logit shift on scored rows (p' = sigmoid(logit p_death + d)); prints bias before/after per class."""
import csv, json, sys
import numpy as np
def load(p):
    r = [x for x in csv.DictReader(open(p)) if x["scored"] == "1"]
    return (np.array([x["room_class"] for x in r]), np.clip(np.array([float(x["p_death"]) for x in r]), 1e-7, 1 - 1e-7),
            np.array([int(x["combat_outcome"]) != 1 for x in r], float))
def shift(p, d): return 1 / (1 + np.exp(-(np.log(p / (1 - p)) + d)))
cls, p, died = load(sys.argv[1]); b = cls == "BOSS"
lo, hi = -2.0, 2.0
for _ in range(100):                               # bias(d) is increasing in d: bisect on mean(p' - y) = 0
    m = (lo + hi) / 2
    lo, hi = (m, hi) if (shift(p[b], m) - died[b]).mean() < 0 else (lo, m)
d = (lo + hi) / 2
nll = lambda q, y: float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())
out = {"rows": int(len(p)), "boss_rows": int(b.sum()), "boss_deaths": int(died[b].sum()), "delta": d,
       "boss_bias_before": float((p[b] - died[b]).mean()), "boss_bias_after": float((shift(p[b], d) - died[b]).mean()),
       "boss_nll_before": nll(p[b], died[b]), "boss_nll_after": nll(shift(p[b], d), died[b]),
       "bias_by_class": {c: float((p[cls == c] - died[cls == c]).mean()) for c in ("NORMAL", "ELITE", "BOSS")}}
print(json.dumps(out, indent=1))
