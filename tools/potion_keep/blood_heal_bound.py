#!/usr/bin/env python3
"""Bound the Blood Potion keep-value bias from the legacy in-combat heal (no seeds).

  blood_heal_bound.py <in.csv.gz> <out.csv.gz>

The legacy engine healed int(0.4 * maxHp) per in-combat Blood Potion without Sacred Bark; the fixed engine
heals int(0.2 * maxHp) (STS_BLOOD_POTION_HEAL_FIX). Subtracts the full difference from postHp in every fight
where a Blood Potion was drunk (held at the start, fewer at the end), as if the legacy heal were never capped
at max HP. Refitting the output with fit_keep_values.py gives a lower bound for the HP part of the value;
the old fit is the upper bound. Prints drink rates and the share of drinking fights that end at max HP.
"""
import sys
import numpy as np
import pandas as pd

BLOOD = "7"  # Potion::BLOOD_POTION
src, dst = sys.argv[1], sys.argv[2]
df = pd.read_csv(src)
count = lambda s: s.fillna("").astype(str).str.split().apply(lambda l: sum(1 for v in l if v == BLOOD))
pre, post = count(df.prePot), count(df.postPot)
drinks = (pre - post).clip(lower=0)
excess = (np.floor(0.4 * df.preMax) - np.floor(0.2 * df.preMax)) * drinks
held, drunk = pre > 0, drinks > 0
print(f"{src}: fights {len(df)} bloodHeld {int(held.sum())} drunk {int(drunk.sum())} "
      f"drinkRate {drunk[held].mean():.3f} meanExcessPerHeldFight {excess[held].mean():.2f} "
      f"postHpAtMax(drunk) {(df.postHp[drunk] >= df.postMax[drunk]).mean():.3f}")
df["postHp"] = df.postHp - excess
df.to_csv(dst, index=False, compression="gzip")
