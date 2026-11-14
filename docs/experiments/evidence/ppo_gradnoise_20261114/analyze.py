"""Gram-matrix analysis of per-game policy gradients.

usage: analyze.py OUT TAG [TAG ...]   -> OUT/analysis-<tags>.json
Per game i: G_i (policy-gradient vector). Signal mu = E G_i, per-game covariance Sigma.
  |mu|^2 unbiased = sum_{i!=j} K_ij / (n(n-1));  tr Sigma = (sum K_ii - sum_ij K_ij / n) / (n-1)
  B_noise = tr Sigma / |mu|^2  (games per update at which noise energy = signal energy)
Two metrics: raw (Euclidean) and Adam-like diagonal preconditioning (w_j = 1/sqrt(mean_i G_ij^2)).
"""
import json, os, sys
import numpy as np

out, tags = sys.argv[1], sys.argv[2:]
metas = [json.load(open(os.path.join(out, f"{t}.meta.json"))) for t in tags]
arrs = [np.load(os.path.join(out, f"{t}.grads.npy"), mmap_mode="r") for t in tags]
ns = [a.shape[0] for a in arrs]
N, P = sum(ns), arrs[0].shape[1]
groups = {}
for name, grp, lo, hi in metas[0]["groups"]:
    groups.setdefault(grp, []).append((lo, hi))
CH = 131072
# pass 1: per-coordinate second moment (per tag, Adam-like v of that update)
sq = np.zeros(P, dtype=np.float64)
for lo in range(0, P, CH):
    hi = min(P, lo + CH)
    for a in arrs:
        x = np.asarray(a[:, lo:hi], dtype=np.float32)
        sq[lo:hi] += (x.astype(np.float64) ** 2).sum(0)
sq /= N
w = 1.0 / np.sqrt(sq + 1e-12 * sq.max())
w[sq == 0] = 0.0
grp_of = np.empty(P, dtype=object)
Ks = {g: np.zeros((N, N)) for g in groups}
Kw = np.zeros((N, N))
for g, rng in groups.items():
    for lo0, hi0 in rng:
        for lo in range(lo0, hi0, CH):
            hi = min(hi0, lo + CH)
            x = np.concatenate([np.asarray(a[:, lo:hi], dtype=np.float32) for a in arrs])
            Ks[g] += (x @ x.T).astype(np.float64)
            xw = x * w[lo:hi].astype(np.float32)
            Kw += (xw @ xw.T).astype(np.float64)
    print("group", g, flush=True)
K = sum(Ks.values())
np.save(os.path.join(out, "K-" + "+".join(tags) + ".npy"), K)
np.save(os.path.join(out, "Kw-" + "+".join(tags) + ".npy"), Kw)
for g in Ks:
    np.save(os.path.join(out, f"K{g}-" + "+".join(tags) + ".npy"), Ks[g])

def stats(K, idx=None, c=None):
    """c: bootstrap counts over idx."""
    if idx is not None:
        K = K[np.ix_(idx, idx)]
    n = K.shape[0]
    if c is None:
        c = np.ones(n)
    m = c.sum()
    tot = c @ K @ c
    diag = (c * np.diag(K)).sum()
    mu2 = (tot - diag) / (m * (m - 1))
    trS = (diag - tot / m) / (m - 1)
    return mu2, trS

def summary(K, idx, rng, nboot=2000):
    mu2, trS = stats(K, idx)
    n = len(idx)
    boots = []
    for _ in range(nboot):
        c = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        boots.append(stats(K, idx, c))
    boots = np.array(boots)
    lo, hi = np.percentile(boots[:, 0], [2.5, 97.5])
    # B_noise interval from the bootstrap of mu2 (trS is tight)
    bl = trS / hi if hi > 0 else float("inf")
    bh = trS / lo if lo > 0 else float("inf")
    # random half splits: cosine between the two half sums
    cos = []
    Ksub = K[np.ix_(idx, idx)]
    for _ in range(500):
        p = rng.permutation(n)
        A, B = p[: n // 2], p[n // 2:]
        ab = Ksub[np.ix_(A, B)].sum(); aa = Ksub[np.ix_(A, A)].sum(); bb = Ksub[np.ix_(B, B)].sum()
        cos.append(ab / np.sqrt(aa * bb))
    cos = np.array(cos)
    snr520 = 520 * mu2 / trS
    return {"n": n, "mu2": mu2, "mu2_95": [lo, hi], "trSigma": trS, "B_noise_games": trS / mu2 if mu2 > 0 else None,
            "B_noise_95": [bl, bh], "z_mu2": mu2 / boots[:, 0].std(), "snr_per_520_game_update": snr520,
            "half_split_cos_mean": cos.mean(), "half_split_cos_sd": cos.std(),
            "half_split_cos_expected": (n / 2) * mu2 / ((n / 2) * mu2 + trS),
            "cos_520_batch_vs_truth_expected": float(np.sqrt(snr520 / (1 + snr520))) if mu2 > 0 else 0.0}

rng = np.random.default_rng(20261114)
res = {"tags": tags, "n": ns, "P": P}
offs = np.cumsum([0] + ns)
sets = {t: np.arange(offs[i], offs[i + 1]) for i, t in enumerate(tags)}
if len(tags) > 1:
    sets["pooled"] = np.arange(N)
for name, idx in sets.items():
    res[name] = {"raw": summary(K, idx, rng), "adam_diag": summary(Kw, idx, rng),
                 "raw_by_group": {g: dict(zip(("mu2", "trSigma"), stats(Ks[g], idx))) for g in Ks}}
if len(tags) == 2:
    A, B = sets[tags[0]], sets[tags[1]]
    for lab, KK in (("raw", K), ("adam_diag", Kw)):
        ab = KK[np.ix_(A, B)].sum(); aa = KK[np.ix_(A, A)].sum(); bb = KK[np.ix_(B, B)].sum()
        res[f"cross_iteration_cos_{lab}"] = ab / np.sqrt(aa * bb)
        # signal correlation between the two iterations: E[S_A.S_B] / sqrt(n_a^2 mu_a^2 n_b^2 mu_b^2)
        mua, _ = stats(KK, A); mub, _ = stats(KK, B)
        res[f"cross_iteration_signal_corr_{lab}"] = (ab / (len(A) * len(B))) / np.sqrt(max(mua, 1e-300) * max(mub, 1e-300))
# per-game advantage stats
g_all = [g for m in metas for g in m["games"]]
h = np.array([g["heart"] for g in g_all]); sA = np.array([g["sumA"] for g in g_all]); npd = np.array([g["np"] for g in g_all])
gn = np.array([g["gnorm2"] for g in g_all])
res["games"] = {"heart_rate": h.mean(), "policy_decisions_per_game": npd.mean(),
                "sumA_per_game_sd": sA.std(), "corr_sumA_heart": float(np.corrcoef(sA, h)[0, 1]),
                "mean_abs_A_over_game_mean": float(np.mean(np.abs(sA) / npd)),
                "gnorm2_mean": gn.mean(), "value_ev": [m["value_ev"] for m in metas]}
# share of tr Sigma explained by the outcome: regress G_i on heart (two-class means)
for lab, KK in (("raw", K),):
    i1, i0 = np.where(h == 1)[0], np.where(h == 0)[0]
    d2 = KK[np.ix_(i1, i1)].mean() + KK[np.ix_(i0, i0)].mean() - 2 * KK[np.ix_(i1, i0)].mean()
    res["outcome_split_sq_dist_raw"] = d2
fn = os.path.join(out, "analysis-" + "+".join(tags) + ".json")
json.dump(res, open(fn, "w"), indent=1, default=float)
print(json.dumps(res, indent=1, default=float))
