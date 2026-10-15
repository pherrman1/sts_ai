#!/usr/bin/env python3
"""Per-potion keep value: fight HP outcome on held-potion counts, seed and encounter fixed effects."""
import sys, re
import numpy as np, pandas as pd, scipy.sparse as sp
from scipy.sparse.linalg import lsqr

src = open("/home/user/sts_ai/include/constants/Potions.h").read()
enum = re.search(r"enum class Potion[^{]*\{(.*?)\};", src, re.S).group(1)
names = [t.split("=")[0].strip() for t in re.sub(r"//.*", "", enum).split(",") if t.strip()]

df = pd.read_csv(sys.argv[1])
reps = int(sys.argv[2]) if len(sys.argv) > 2 else 0
pre = df.prePot.fillna("").astype(str).str.split()
P = np.zeros((len(df), len(names)), dtype=np.float32)
for i, lst in enumerate(pre):
    for v in lst:
        v = int(v)
        if v > 1: P[i, v] += 1
held = P.sum(0)
keep = [j for j in range(len(names)) if held[j] >= 200]
y = ((df.postHp - df.preHp) + (df.postMax - df.preMax)).to_numpy(float)
death = (df.outcome == 2).to_numpy(float)
ctrl = np.column_stack([df.preHp, df.preMax, df.preHp / df.preMax, df.floor, df.deck, df.relics, df.gold / 100.0])
seed_idx = pd.factorize(df.seed)[0]
enc_idx = pd.factorize(df.enc.astype(str) + "_" + df.act.astype(str))[0]
n = len(df)
X = sp.hstack([sp.csr_matrix(P[:, keep]), sp.csr_matrix(ctrl),
               sp.csr_matrix((np.ones(n), (np.arange(n), seed_idx))),
               sp.csr_matrix((np.ones(n), (np.arange(n), enc_idx)))[:, 1:]]).tocsr()

def fit(target, w=None):
    A, b = X, target
    if w is not None:
        sw = np.sqrt(w); A = sp.diags(sw) @ X; b = target * sw
    return lsqr(A, b, atol=1e-10, btol=1e-10, iter_lim=20000)[0][:len(keep)]

bh, bd = fit(y), fit(death)
rng = np.random.default_rng(0)
boots_h, boots_d = [], []
nseed = seed_idx.max() + 1
for r in range(reps):
    w = rng.poisson(1.0, nseed)[seed_idx].astype(float)
    boots_h.append(fit(y, w)); boots_d.append(fit(death, w))
sh = np.std(boots_h, 0) if reps else np.full(len(keep), np.nan)
sd = np.std(boots_d, 0) if reps else np.full(len(keep), np.nan)
res = pd.DataFrame({"potion": [names[j] for j in keep], "held": held[keep].astype(int),
                    "hp": bh, "hp_se": sh, "death": bd, "death_se": sd}).sort_values("hp", ascending=False)
print(f"fights {n}  seeds {nseed}  encounters {enc_idx.max()+1}  mean y {y.mean():.2f}  death {death.mean():.4f}")
print(res.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
res.to_csv(sys.argv[1].replace(".csv.gz", "-fit.csv"), index=False)
