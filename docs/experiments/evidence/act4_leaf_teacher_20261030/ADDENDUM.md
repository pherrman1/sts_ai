# §721 addendum (2026-10-30, after #913's review)

- **V_H without duplicate records.** heart.pkl held 10 duplicate records (two duplicate run-1 unit tars, 111384715 and
  111384960). `fit_heart_dedup.py` (identical to `fit_heart.py` except that it keeps the first record per campaign,
  seed and game) on 4,822 states: TEST (non-fresh) BCE G 0.475, GC 0.466, CTM_recal 0.485; GC − CTM −0.019
  [−0.037, −0.003], G − CTM −0.010 [−0.035, +0.015]; potion 13.2 / 12.1 HP, Fairy 28.7 / 28.3 HP
  ([results/vh_dedup.json](results/vh_dedup.json)). §721's conclusions are unchanged.
- **§510 per-type potion prices** were not correlated with V_H's: §510 prices come from act 1-3 fights and are not on
  the same scale as a Heart-entry value.
- **Fairy gap.** The leaf values Fairy at ≈ 37 HP, V_A4/V_H at 15-30. No fight-level evidence exists on whether that
  ≈ 10 HP gap changes play.
