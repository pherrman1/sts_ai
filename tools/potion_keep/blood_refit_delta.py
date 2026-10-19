#!/usr/bin/env python3
"""Blood Potion keep-value change from the heal fix, from paired potionpriceprobe copies.

  blood_refit_delta.py DIR      (DIR/f1-s<seed>.csv with STS_BLOOD_POTION_HEAL_FIX=1, DIR/f0-s<seed>.csv with =0)

Each probe run (EXTRA addpot:BLOOD_POTION, FIGHTS_AHEAD=1) plays every sampled battle-start state twice: base
and with one Blood Potion added. Value per state = (hp_add - hp_base) + 53 * (survived_add - survived_base),
the ADR-0039 unit (53 = SilverEvalWeights::winBonus). Prints both regimes, the change fix1 - fix0 with a
95% seed-cluster bootstrap CI, and the paired change over start states identical in both regimes.
"""
import glob
import sys
import numpy as np
import pandas as pd

WIN_BONUS = 53.0
D = sys.argv[1]


def load(fix):
    rows = []
    for f in sorted(glob.glob(f"{D}/f{fix}-s*.csv")):
        d = pd.read_csv(f)
        if (d.valid == 0).any():
            raise SystemExit(f"{f}: invalid rows")
        b = d[d.variant == "base"].set_index(["seed", "battleIdx"])
        a = d[d.variant == "addpot:BLOOD_POTION"].set_index(["seed", "battleIdx"])
        j = a.join(b, rsuffix="_b", how="inner")
        j["dhp"], j["dsurv"] = j.hp - j.hp_b, j.survived - j.survived_b
        j["v"] = j.dhp + WIN_BONUS * j.dsurv
        rows.append(j.reset_index())
    return pd.concat(rows)


r1, r0 = load(1), load(0)
for name, r in (("fix1", r1), ("fix0", r0)):
    print(f"{name}: states {len(r)} seeds {r.seed.nunique()} value {r.v.mean():.2f} "
          f"(dHP {r.dhp.mean():.2f}, dSurvived {r.dsurv.mean():.4f})")
p = r1.merge(r0, on=["seed", "battleIdx", "floor", "curHp", "maxHp", "potions"], suffixes=("1", "0"))
print(f"identical start states {len(p)}: paired change {(p.v1 - p.v0).mean():.2f} (sd {(p.v1 - p.v0).std():.2f})")
seeds = np.array(sorted(set(r1.seed) | set(r0.seed)))
s1 = r1.groupby("seed").v.sum().reindex(seeds, fill_value=0).values
n1 = r1.groupby("seed").v.size().reindex(seeds, fill_value=0).values
s0 = r0.groupby("seed").v.sum().reindex(seeds, fill_value=0).values
n0 = r0.groupby("seed").v.size().reindex(seeds, fill_value=0).values
rng = np.random.default_rng(0)
boot = []
for _ in range(4000):
    i = rng.integers(0, len(seeds), len(seeds))
    boot.append(s1[i].sum() / n1[i].sum() - s0[i].sum() / n0[i].sum())
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"change fix1 - fix0 {r1.v.mean() - r0.v.mean():.2f}  95% seed-bootstrap CI [{lo:.2f}, {hi:.2f}]")
