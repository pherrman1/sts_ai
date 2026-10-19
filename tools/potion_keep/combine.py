#!/usr/bin/env python3
"""Combine per-ascension fits into the keep values used by PotionRewardPolicy.cpp.

  combine.py <a20-fit.csv> <a0-fit.csv>

value = hp - 53 * death (53 = SilverEvalWeights::winBonus, Silver's HP-equivalent
of surviving a fight), averaged over the two ascensions.

Steps (no seeds; reads existing CTM corpora):
  extract_ctm_fights.py a20.csv.gz main- /mnt/project-files/ctm-a20/stage1/w*.tar.gz .../rerun-stalled.tar.gz
  extract_ctm_fights.py a0.csv.gz none- /mnt/project-files/ctm-pathb/ARCHIVE-ctm-pathb.tar.gz
  fit_keep_values.py a20.csv.gz 12 ; fit_keep_values.py a0.csv.gz 0
Blood Potion heal-fix bound and refit: blood_heal_bound.py, blood_refit_delta.py (§TBD).
"""
import sys
import pandas as pd

WIN_BONUS = 53.0
a20 = pd.read_csv(sys.argv[1]).set_index("potion")
a0 = pd.read_csv(sys.argv[2]).set_index("potion")
v = pd.DataFrame({"a20": a20.hp - WIN_BONUS * a20.death, "a0": a0.hp - WIN_BONUS * a0.death})
v["mean"] = v.mean(axis=1)
# Philipp (2026-10-15): Smoke Bomb's value is reduced by 8 HP.
# Blood Potion (§TBD): the corpora were played with the legacy 40% in-combat heal. blood_refit_delta.py measured
# -3.82 at A20; A0 takes -3.82 x 0.721 (old excess heal per held fight, A0/A20); mean -3.29
# (STS_POTION_KEEP_BLOOD_REFIT=0 keeps the unadjusted 1163).
ADJUST = {"SMOKE_BOMB": -8.0, "BLOOD_POTION": -3.29}
for name, delta in ADJUST.items():
    if name in v.index:
        v.loc[name, "mean"] += delta
v = v.sort_values("mean", ascending=False)
print(v.round(2).to_string())
print("spearman a20 vs a0:", round(v.a20.corr(v.a0, method="spearman"), 3))
for name, row in v.iterrows():
    print(f"        case Potion::{name}: return {round(row['mean'] * 100)};")
