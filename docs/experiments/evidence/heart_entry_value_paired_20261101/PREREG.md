# Heart-entry value fit on the paired design (stage B2): pre-registration

Status: written after §732 (stage B, NOT_SHOWN) and before this model was fit on the real labels. The only run on the
data before freezing is a `--permute` debug run (labels shuffled within each base); its numbers are not reported. It picked the fewest rounds (200) in every fold, so 50 rounds were added to the grid.

## Why
§732: a GBM fit on all 16,000 fights as independent outcomes predicts which Heart-entry states win (BCE −0.16 vs
Silver's leaf) but not what a single change does. Its HP and potion effects are 1.2-2.3x too large and it misses relic
removal (−0.7 vs −5.0 pp), probably because across states HP and potions stand in for deck strength. §731's design
has a cleaner signal: each base's 16 fights share the state except one change (14 of them also share the battle seed).
B2 fits only that within-base signal.

## Model (`fit_paired.py`)
- **B2**: logit P(Heart kill) = b_base + f(state), with a free offset per base (fixed effects). Fitting alternates three
  times between the offsets (Newton on the base's own 16 fights; a base with 16 wins or 16 losses gets ±8 and drops
  out) and the trees f (XGBoost with base_margin = offset, same features and monotone constraints as §732's A).
  Hyperparameters depth {2, 3, 4} × rounds {50, 200, 500, 1000} (min child weight 20, eta 0.03), chosen by 4-fold CV
  grouped by source seed inside each outer training set, by conditional log loss on the validation bases (offset
  refitted on the validation base's own fights, f fixed).
- On a held-out base: D̂_B2 = σ(a0 + f(state k) − f(control)) − σ(a0), with a0 = logit of A's prediction for the
  control. A is §732's all-feature GBM, refitted on the same outer training set by the same code; no outcome of the
  held-out base is used.
- **L**: Silver's leaf as in §732 (with the unused-Lizard-Tail fix), logistic fitted on float64 with max_iter 10,000
  (§732's fold 4 did not converge).
- Data, features, 5 outer folds (source seed mod 5), the 14,000 pairs and the bootstrap are §732's.

## Primary
Mean of (D − D̂_B2)² − (D − D̂_L)², 95% CI by bootstrap over source seeds (10,000, seed 20261102). PASS if the CI
upper bound < 0; WORSE if the lower bound > 0; else NOT_SHOWN.

## Key secondary
Operator calibration error E_M = Σ over the 13 change operators of n_op / N × (mean D̂_M − mean D)²; B2 − L with a
bootstrap over source seeds (2,000 resamples). This asks whether the model prices HP, potions, relics, counters and
cards right on average. The primary statistic has little room: in §732 an operator-mean predictor reached only
−0.0011 against predicting no effect.

## Co-reported
B2 − A and A − L on the primary statistic; each model's skill against no effect; correlation of D̂ with D; per
operator mean D and mean D̂ for each model; B2's Incense counter effects against §723's table (slope, correlation).

## Decision
- Primary PASS → pre-register stage C (B2 as Silver's S&S win leaf in §724's S&S → Heart chain; runs need
  Philipp's go).
- Primary NOT_SHOWN but the calibration error is lower for B2 (CI < 0) → report to Philipp as a candidate for a
  stage C gate; his call.
- Otherwise → no stage C; the lever is more labels.

## Caveats
As §732: research Heart search, single changes drawn from Heart-entry frequencies, rare card and relic types. A0 comes
from A, so B2's level on a held-out base is A's; only the differences are B2's.
