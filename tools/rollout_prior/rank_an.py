#!/usr/bin/env python3
"""Sibling-ordering measure (#1053): do an arm's per-child playout means order the root edges like the recorded
16k G16 search's qBacked? Per root (edges with >= MINV visits, >= 3 such edges): Spearman rho, top-1 agreement,
regret = max q - q[argmax child mean]. Paired vs a base arm with seed bootstrap."""
import json, sys, glob, collections
import numpy as np

def spearmanr_(a, b):
    ra = np.argsort(np.argsort(a, kind="stable"), kind="stable").astype(float)
    rb = np.argsort(np.argsort(b, kind="stable"), kind="stable").astype(float)
    # average ranks for ties
    def avg(x, r):
        out = r.copy()
        for v in np.unique(x):
            m = x == v
            out[m] = r[m].mean()
        return out
    ra, rb = avg(a, ra), avg(b, rb)
    if ra.std() == 0 or rb.std() == 0: return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])
MINV = int(sys.argv[2]) if len(sys.argv) > 2 else 100
rows = {}
res = collections.defaultdict(dict)
for p in sorted(glob.glob(sys.argv[1] + "/out.*.jsonl")):
    for l in open(p):
        r = json.loads(l)
        if "error" in r or "children" not in r: continue
        key = (int(r["seed"]), int(r["fight"]), int(r["decision"]))
        arm = r["arm"].split("/")[-1].replace(".txt", "").replace("st=", "")
        rows[key] = r["k"]
        res[key][arm] = {c["bits"]: float(np.mean(c["scores"])) for c in r["children"]}
arms = sorted({a for v in res.values() for a in v})
met = collections.defaultdict(dict)
for key, by in res.items():
    if len(by) != len(arms): continue
    e = [(b, q, v) for b, q, v in rows[key]["edges"] if v is not None and v >= MINV and q is not None]
    if len(e) < 3: continue
    bits = [b for b, _, _ in e]; q = np.array([x for _, x, _ in e])
    if q.max() - q.min() < 1e-6: continue
    for a in arms:
        if not all(b in by[a] for b in bits): break
        m = np.array([by[a][b] for b in bits])
        rho = spearmanr_(m, q)
        j = int(np.argmax(m))
        met[key][a] = (0.0 if np.isnan(rho) else rho, float(j == int(np.argmax(q))), float(q.max() - q[j]))
keys = [k for k in met if len(met[k]) == len(arms)]
seeds = np.array([k[0] for k in keys]); u, inv = np.unique(seeds, return_inverse=True)
rng = np.random.default_rng(1); W = [np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u)) for _ in range(2000)]
def ci(x):
    S = np.bincount(inv, x); N = np.bincount(inv)
    bs = [(w * S).sum() / (w * N).sum() for w in W]
    return np.percentile(bs, 2.5), np.percentile(bs, 97.5)
base = sys.argv[3] if len(sys.argv) > 3 else "rp_V"
print(f"roots {len(keys)} (edges >= {MINV} visits, >= 3 edges); base {base}")
print(f"{'arm':12s} {'rho':>7s} {'top1':>7s} {'regret':>7s}   d_rho vs base          d_regret vs base")
for a in arms:
    X = np.array([met[k][a] for k in keys]); B = np.array([met[k][base] for k in keys])
    dr = X[:, 0] - B[:, 0]; dg = X[:, 2] - B[:, 2]
    lo, hi = ci(dr); lo2, hi2 = ci(dg)
    print(f"{a:12s} {X[:,0].mean():7.3f} {X[:,1].mean():7.3f} {X[:,2].mean():7.2f}   {dr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]   {dg.mean():+.2f} [{lo2:+.2f},{hi2:+.2f}]")
