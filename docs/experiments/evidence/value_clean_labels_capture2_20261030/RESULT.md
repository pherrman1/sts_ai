# Stage 5b result: backward fit V_A3 -> V_A2 -> V_A1 on 1,280 captured games, gate FAIL in all three acts

Script `stage5b.py` (committed 9aa2562a at 17:38Z 10-30, after the first capture-2 tars landed on the share (17:10Z) but before any were read; eval fix 73e7b2f7, resume 34314cf9).
Data: run-1 pilot (32) + stage 4 (256) + capture 2 (992) price-captured replays = 1,280 games; 48,644 real run-1
map states. Fresh TEST = capture-2 seeds with seed % 4 == 3 (never read before this run). Encoder `full_feats.py`
(3,239 columns), act-end anchor for act 3 = #915 V_A4 ensemble (§722).

| act | val BCE | calib a, b (VALIDATION games) | (a) concordance V - search q | (b) real logloss V vs q | (c) HP inv | (d) upgrade wrong | gate |
|---|---|---|---|---|---|---|---|
| 3 | 0.544 | 0.92, 1.43 (208 g) | -0.014 [-0.053, +0.025] (1,239 pairs) | 0.526 vs 0.641, -0.115 [-0.216, -0.017] | 0 | 13.8% | FAIL (a) |
| 2 | 0.491 | 0.86, 1.24 (286 g) | -0.018 [-0.048, +0.015] (1,879) | 0.560 vs 0.572, -0.012 [-0.077, +0.047] | 0 | 9.4% | FAIL (a) |
| 1 | 0.530 | 0.29, 1.01 (320 g) | **+0.064 [+0.035, +0.093]** (2,137) | 0.539 vs 0.529, +0.010 [-0.020, +0.039] | 0 | 8.8% | FAIL (b) |

Pre-registered gate per act: (a) diff >= +0.02 and CI > 0, (b) diff <= 0, (c) 0, (d) < 29.7%. All four needed.

## Reading
- Act 1 ranks map choices better than the search's q (63% vs 57% concordant with the rollout labels) and is level
  calibrated (slope 1.01), but its real-outcome logloss is 0.010 worse than q (not significant). Act 1 misses (b) narrowly.
- Acts 2 and 3 do not rank map choices better than q (both slightly worse, CIs include 0), although act 3's real
  logloss is clearly better than q (-0.115). Calibration slopes 1.24/1.43 show the raw GBM is underconfident on real states.
- Stage 5's diagnosis "real logloss much worse -> overfit" was mostly the eval bug below; with the fix
  the models are as good as or better than q on real outcomes in acts 2-3.

## Eval bug and disclosures
- First run (run_a/): the gate's (b)-(d) passed DENSE arrays to XGBoost models trained on CSR. XGBoost reads absent
  CSR entries as missing but dense zeros as values, so predictions were nonsense (validation check: logloss 0.48
  sparse vs 1.10 dense, max |diff| 0.86). Found after reading act 3's TEST numbers; fix converts dense to CSR in
  `VCal`. Model fits, calibration and concordance (a) always used CSR and are unchanged (run A and B identical).
- The same bug sits in `../value_clean_labels_stage4_20261030/stage5_full.py`; its (b)-(d) numbers are invalid.
- Fix and checkpoint/resume were added after the first look; nothing in the model or gate definitions changed.
- Calibration games (VALIDATION) are disjoint from TEST; capture-2 TEST was read once per act (run A act 3 + run B).

Models: share `/mnt/project-files/value-clean-labels/stage5b/V_A{1,2,3}.pkl` (sha256 prefixes V_A1 d7e69feed627,
V_A2 e557c80cbfa6, V_A3 f4d72f665452).
