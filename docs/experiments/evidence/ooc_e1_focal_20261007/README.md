# E1: focal retrain of the #334 X2 family (2026-10-07)

Ledger: [§394](../../ledger-06.md). Offline only: no gameplay, no data
collection, TEST components never opened.

## Question

Were the counterfactual sibling comparisons in the #334 corpus diluted among
the many later trajectory rows that X2-B trains on? If so, training on (or
upweighting) the first MAP row after each sampled option should price picks
better, especially card rewards.

## Inputs

- Corpus index `.../a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json`,
  SHA-256 `ae56f963...0dfa00`, sources TRAIN/VALIDATION/TEST = 696/155/173.
  Strictly validated for #334; this run re-checked only the index, all
  component-manifest hashes and the map/runout/branches table hashes of
  TRAIN/VALIDATION components (no `validate_bundle` rerun, per brief).
- Frozen X2-B: `.../a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/model.ubj`,
  SHA-256 `99dbac6b...cdcb52dd`, 461 features. Recomputed VALIDATION NLL
  0.4226083643848224 equals the frozen value exactly (anchor check).
- Rows: TRAIN 648,669 MAP rows / 23,557 branches; VALIDATION 141,566 / 5,169.
  Focal rows: TRAIN 23,551 (6 branches ended before another MAP row),
  VALIDATION 5,169.

## Arms

All retrained arms use the X2-B recipe (hist, depth 6, eta 0.06,
min_child_weight 10, `curHp` monotone, subsample 0.8, colsample 0.7, up to
2,500 rounds, early stopping 50 on VALIDATION with the arm's own weights),
the public 457 features (461 minus `nextEliteId`, `nextFight0..2`, #397),
seeds 0/1/2. The primary prediction is the 3-seed probability mean.

| Arm | Rows | Weights |
|---|---|---|
| X2B | frozen | frozen, 461 features incl. hidden-future fields |
| P0 | all MAP rows | 1 |
| F1 | focal rows only | each decision's siblings share weight 1, rescaled to mean 1 |
| F2 | all MAP rows | non-focal 1; focal rows keep F1 shares, scaled so the focal block's total weight equals the non-focal total |

Only the frozen X2B arm reads the four hidden-future fields, so its absolute
NLL is not a public-information baseline; P0, F1 and F2 are. Compare focal arms
with P0.

Focal row = sibling_ranking join: the minimum recorded `rowIdx` of the branch
trajectory (`rowIdx > 0` for MAP branches).

Selection gain per sampled decision = `won(model's argmax sibling) -
won(source/V4 chosen sibling)`, each from that sibling's own single branch
rollout; predicted ties average the tied siblings. 95% CIs resample source
seeds (2,000 reps, `cluster_mean`). Decisions are limited to the sampled
siblings (at most six options per decision).

## Results (VALIDATION, 155 sources)

| Arm | NLL all | Brier all | NLL focal | Brier focal |
|---|---:|---:|---:|---:|
| X2B | 0.4226 | 0.1378 | 0.4884 | 0.1626 |
| P0 | 0.4237 | 0.1385 | 0.4923 | 0.1644 |
| F1 | 0.4369 | 0.1424 | 0.4958 | 0.1651 |
| F2 | 0.4263 | 0.1392 | 0.4869 | 0.1622 |

Per-seed all-row NLL: P0 0.4269/0.4263/0.4235, F1 0.4407/0.4395/0.4375,
F2 0.4293/0.4291/0.4274.

Deltas vs P0 (source-clustered 95% CI):

| Comparison | NLL all | NLL focal | Brier focal |
|---|---|---|---|
| X2B − P0 | −0.0011 [−0.0059, +0.0041] | −0.0039 [−0.0098, +0.0022] | −0.0018 [−0.0040, +0.0004] |
| F1 − P0 | +0.0132 [+0.0035, +0.0227] | +0.0035 [−0.0086, +0.0162] | +0.0007 [−0.0036, +0.0054] |
| F2 − P0 | +0.0026 [−0.0024, +0.0078] | −0.0054 [−0.0119, +0.0010] | −0.0022 [−0.0045, −0.0000] |

Selection gain vs V4's choice (decisions / discordant decisions in brackets):

| Type | X2B | P0 | F1 | F2 | Oracle |
|---|---|---|---|---|---|
| CARD_REWARD (155/48) | +0.025 [−0.023, +0.071] | +0.027 [−0.019, +0.079] | +0.039 [−0.014, +0.096] | +0.042 [−0.009, +0.090] | +0.155 |
| BOSS_RELIC (153/72) | −0.052 [−0.121, +0.013] | −0.047 [−0.112, +0.013] | −0.050 [−0.113, +0.013] | −0.026 [−0.092, +0.033] | +0.144 |
| NEOW (155/78) | +0.068 [−0.003, +0.142] | +0.061 [−0.010, +0.136] | +0.071 [−0.003, +0.145] | +0.045 [−0.032, +0.123] | +0.219 |
| SHOP (153/61) | +0.016 | +0.000 | +0.039 | +0.013 | +0.176 |
| REST (155/57) | +0.013 | +0.006 | +0.021 | +0.018 | +0.155 |
| EVENT (155/34) | +0.019 | +0.008 | +0.020 | +0.033 | +0.090 |
| MAP (155/32) | +0.008 | +0.016 | +0.029 | +0.026 | +0.103 |
| OTHER_SELECTOR (93/31) | −0.065 | −0.070 | −0.001 | −0.006 | +0.086 |
| TREASURE (155/21) | −0.003 | −0.003 | +0.019 | +0.016 | +0.058 |
| pooled (1,329/434) | +0.006 [−0.025, +0.037] | +0.003 [−0.028, +0.036] | +0.022 [−0.010, +0.056] | +0.019 [−0.012, +0.050] | +0.134 |

Paired gain differences vs P0: CARD_REWARD F1 +0.011 [−0.030, +0.050],
F2 +0.015 [−0.018, +0.045]; BOSS_RELIC F2 +0.021 [+0.000, +0.047];
pooled F1 +0.019 [+0.005, +0.032], F2 +0.016 [+0.004, +0.027].
A uniform-random sibling scores −0.010 pooled (BOSS_RELIC −0.074).

Sibling-ranking concordance (descriptive, pooled): X2B 0.537, P0 0.535,
F1 0.564, F2 0.551.

## Verdict

`E1_INCONCLUSIVE` under the plan's rule. No arm's card-reward selection gain
is clearly positive: F1 and F2 point up (+0.04) but both CIs include zero, on
48 discordant card-reward decisions. Pooled over all types, focal training
selects slightly better than P0 (+0.016..+0.019, CI above zero), but the
pooled contrast was not the preregistered criterion and the per-type CIs are
not multiplicity-adjusted. F2 keeps all-row calibration within noise of P0 and
improves focal Brier slightly; F1 loses 0.013 all-row NLL. Removing the four
hidden-future fields costs nothing measurable (X2B − P0 within noise, as in
§371). Per the plan, E3 decides; focal weighting (F2) is a cheap default for
it.

## Files

- `report.json`: full metrics, per-seed results, selection gain by type,
  paired differences, oracle/uniform references, sibling ranking, model
  hashes.
- `run.log`: training log.
- Local run directory with all nine checkpoints and VALIDATION predictions:
  `/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/e1-focal-20261007-36b5b14f/`
  (`SHA256SUMS` inside; `report.json` `1f9e5bcb...a6192fe9e524`).

## Reproduce

```bash
A=/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334
OMP_NUM_THREADS=4 python3 -m tools.vwin_e1_focal \
  $A/a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json \
  --x2b-run $A/a3-final1024-x2b-finalist-20261003-49c28d80/tune \
  --output build/e1-focal-NEW --seeds 0,1,2 --threads 4
```

Tooling SHA `36b5b14f` (Python 3.12.3, NumPy 2.5.1, XGBoost 3.4.0, pandas
3.0.5, CPU, 4 threads). Runtime: 35 s load, ~4 min training total.
