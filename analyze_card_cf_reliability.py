#!/usr/bin/env python3
"""Compare two independent counterfactual outcome panels for identical card decisions."""
import json
import sys

import numpy as np
import pandas as pd


if len(sys.argv) < 4:
    raise SystemExit("usage: analyze_card_cf_reliability.py PANEL_A.csv PANEL_B.csv OUT.json")

pa, pb, out = sys.argv[1:4]
a = pd.read_csv(pa)
b = pd.read_csv(pb)
keys = ["seed", "decisionIdx", "actionIdx", "candidateId", "candidateUpgraded"]
value = ["branchWon", "branchFloor"]
if a.duplicated(keys).any() or b.duplicated(keys).any():
    raise ValueError("duplicate action keys in a reliability panel")
m = a[keys + value].merge(b[keys + value], on=keys, suffixes=("A", "B"), validate="one_to_one")
if len(m) != len(a) or len(m) != len(b):
    raise ValueError(f"panels do not contain identical actions: A={len(a)} B={len(b)} joined={len(m)}")
m["scoreA"] = m.branchFloorA + 10.0 * m.branchWonA
m["scoreB"] = m.branchFloorB + 10.0 * m.branchWonB

records = []
adv_a, adv_b = [], []
pair_agree, pair_total = 0, 0
pair_by_margin = {"0_2": [0, 0], "2_5": [0, 0], "5_10": [0, 0], "10_plus": [0, 0]}
for key, g in m.groupby(["seed", "decisionIdx"], sort=False):
    g = g.reset_index(drop=True)
    skip = np.flatnonzero(g.candidateId.to_numpy() < 0)
    if len(skip) != 1:
        raise ValueError(f"decision {key} has {len(skip)} skip actions")
    sa, sb = g.scoreA.to_numpy(), g.scoreB.to_numpy()
    ba, bb = sa == sa.max(), sb == sb.max()
    ia, ib = int(np.argmax(sa)), int(np.argmax(sb))
    cross_a_on_b = float(sb[ia])
    cross_b_on_a = float(sa[ib])
    records.append({
        "best_set_overlap": bool(np.any(ba & bb)),
        "argmax_equal": ia == ib,
        "a_choice_on_b": cross_a_on_b,
        "b_choice_on_a": cross_b_on_a,
        "skip_a": float(sa[skip[0]]), "skip_b": float(sb[skip[0]]),
        "oracle_a": float(sa.max()), "oracle_b": float(sb.max()),
    })
    aa, ab = sa - sa[skip[0]], sb - sb[skip[0]]
    non_skip = g.candidateId.to_numpy() >= 0
    adv_a.extend(aa[non_skip]); adv_b.extend(ab[non_skip])
    for i in range(len(g)):
        for j in range(i + 1, len(g)):
            da, db = sa[i] - sa[j], sb[i] - sb[j]
            if da == 0 or db == 0:
                continue
            agree = int(np.sign(da) == np.sign(db))
            margin = min(abs(da), abs(db))
            bucket = "0_2" if margin < 2 else "2_5" if margin < 5 else "5_10" if margin < 10 else "10_plus"
            pair_by_margin[bucket][0] += agree; pair_by_margin[bucket][1] += 1
            pair_agree += agree; pair_total += 1

r = pd.DataFrame(records)
adv_a, adv_b = np.asarray(adv_a), np.asarray(adv_b)
corr = float(np.corrcoef(adv_a, adv_b)[0, 1])
best_overlap = float(r.best_set_overlap.mean())
metrics = {
    "decisions": int(len(r)), "actions": int(len(m)),
    "best_set_overlap": best_overlap,
    "strict_argmax_agreement": float(r.argmax_equal.mean()),
    "advantage_correlation": corr,
    "pairwise_sign_agreement": float(pair_agree / pair_total),
    "pairwise_by_min_margin": {
        k: {"agreement": (v[0] / v[1] if v[1] else None), "pairs": v[1]}
        for k, v in pair_by_margin.items()
    },
    "panel_a_choice_scored_on_b": float(r.a_choice_on_b.mean()),
    "panel_b_skip": float(r.skip_b.mean()),
    "panel_b_oracle_same_panel": float(r.oracle_b.mean()),
    "panel_b_choice_scored_on_a": float(r.b_choice_on_a.mean()),
    "panel_a_skip": float(r.skip_a.mean()),
    "panel_a_oracle_same_panel": float(r.oracle_a.mean()),
}
# Both conditions matter: top-set overlap catches policy instability, while
# centered correlation catches unstable advantage magnitudes hidden by ties.
metrics["needs_adaptive_futures"] = bool(best_overlap < 0.70 or corr < 0.80)
with open(out, "w") as f:
    json.dump(metrics, f, indent=2)
print(json.dumps(metrics, indent=2))
