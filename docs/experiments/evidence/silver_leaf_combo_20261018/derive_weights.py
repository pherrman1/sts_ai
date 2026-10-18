#!/usr/bin/env python3
"""Derive this campaign's per-type Silver potion weights from the concave-HP probe CSVs (§TBD, PR #665).

Each probe state was continued for 3 fights as `base`, `hp:-12` and `pot:<TYPE>` (one held potion removed), scored by
the A20 floor model (altFloor). Price of type T in HP = mean(base - pot:T) / (mean(base - hp:-12) / 12), per state,
seed-bootstrap SE (2,000 resamples, RNG 665). Empirical-Bayes shrinkage toward the pooled non-Fairy price as in
silver_potion_weights_20261017/derive_weights.py; Fairy (death-save term) and Smoke Bomb (escape option) stay at 11.
Usage: derive_weights.py DIR...  (directories holding the probe s<seed>.csv files) -> spec on stdout, table on stderr.
"""
import csv, glob, os, random, statistics as st, sys
from collections import defaultdict

PINNED = {"FAIRY_POTION": 11.0, "SMOKE_BOMB": 11.0}
states = defaultdict(dict)
for root in sys.argv[1:]:
    for f in glob.glob(os.path.join(root, "**", "s*.csv"), recursive=True):
        for r in csv.DictReader(open(f)):
            if r["valid"] == "1":
                states[(int(r["seed"]), int(r["battleIdx"]))][r["variant"]] = float(r["altFloor"])
per_seed = defaultdict(list)            # seed -> [(kind, delta)]
for (seed, _), v in states.items():
    if "base" not in v:
        continue
    for name, x in v.items():
        if name == "hp:-12" or name.startswith("pot:"):
            per_seed[seed].append((name, v["base"] - x))
seeds = sorted(per_seed)


def prices(sample):
    hp, pot = [], defaultdict(list)
    for s in sample:
        for k, d in per_seed[s]:
            (hp.append(d) if k == "hp:-12" else pot[k[4:]].append(d))
    slope = st.mean(hp) / 12
    out = {k: (st.mean(v) / slope, len(v)) for k, v in pot.items()}
    pool = [d for k, v in pot.items() if k != "FAIRY_POTION" for d in v]
    out["ALL_EXCEPT_FAIRY"] = (st.mean(pool) / slope, len(pool))
    return out


est = prices(seeds)
rng = random.Random(665)
reps = defaultdict(list)
for _ in range(2000):
    for k, (p, _) in prices([rng.choice(seeds) for _ in seeds]).items():
        reps[k].append(p)
mu = est["ALL_EXCEPT_FAIRY"][0]
rows = {k: (e, st.pstdev(reps[k]), n) for k, (e, n) in est.items()
        if k != "ALL_EXCEPT_FAIRY" and k not in PINNED and n >= 30}
big = [r for r in rows.values() if r[2] >= 100]
tau2 = max(0.0, st.pvariance([r[0] for r in big]) - st.mean([r[1] ** 2 for r in big]))
w = dict(PINNED)
for k, (e, se, n) in rows.items():
    b = tau2 / (tau2 + se * se)
    w[k] = round(max(0.0, mu + b * (e - mu)), 1)
print(f"# states={len(states)} seeds={len(seeds)} mu={mu:.2f} tau2={tau2:.2f} big={len(big)}", file=sys.stderr)
for k in sorted(est, key=lambda k: -est[k][0]):
    e, n = est[k]
    print(f"# {k:22s} w {w.get(k, round(mu, 1)) if k != 'ALL_EXCEPT_FAIRY' else '':>5}  est {e:6.1f} "
          f"se {st.pstdev(reps[k]):4.1f} n {n}", file=sys.stderr)
print(",".join(f"{k}={w[k]}" for k in sorted(w)) + f",*={round(mu, 1)}")
