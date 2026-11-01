# All-feature Heart-entry value (stage B): result

Pre-registration: [PREREG.md](PREREG.md) (review FAIL → Lizard Tail fix 3e1a4807 → delta PASS, before the real fit).
Run: frozen `fit_value.py` (xgboost 3.0.5, scikit-learn 1.9.1) on §731's `labels.csv` and `variants.tar` states, output
[results/value.json](results/value.json). 1,000 bases, 699 source seeds, 14,000 pairs, 436 features; offline, ~8 min.

## Primary
Paired-difference squared error, A − L: **−0.00013 [−0.00134, +0.00109]** → **NOT_SHOWN**.

## Co-reported
| model | MSE of D | − predicting no effect | corr(D̂, D) | BCE all fights |
|---|---|---|---|---|
| A (all features) | 0.13484 | −0.0014 [−0.0028, +0.0001] | 0.123 | 0.459 |
| LI (leaf inputs, GBM) | 0.13677 | +0.0006 [−0.0007, +0.0018] | 0.094 | 0.539 |
| L (Silver leaf, logistic) | 0.13497 | −0.0012 [−0.0016, −0.0009] | 0.107 | 0.621 |
| no effect | 0.13621 | | | |

A − LI −0.0019 [−0.0026, −0.0012]; LI − L +0.0018 [+0.0007, +0.0028]. Out-of-fold BCE on all fights, A − L per
base: −0.162 [−0.184, −0.139] (A knows which states win, L does not).

Mean effect per operator (pp): observed D, then each model's mean D̂.

| operator | n | observed | A | LI | L |
|---|---|---|---|---|---|
| HP down | 1,712 | −7.1 | −10.9 | −13.1 | −2.5 |
| HP up | 823 | +3.8 | +8.6 | +10.7 | +2.0 |
| potion removed | 810 | −7.2 | −8.7 | −9.4 | −2.6 |
| potion added | 1,000 | +5.0 | +8.4 | +9.6 | +2.6 |
| relic removed | 1,323 | −5.0 | −0.7 | −0.1 | −0.1 |
| relic counter | 1,058 | −2.7 | −0.5 | −0.7 | −0.2 |
| relic added | 1,332 | +1.4 | +0.6 | +0.1 | +0.0 |
| card added | 1,252 | +2.2 | +0.7 | 0 | 0 |
| card removed | 1,263 | +0.5 | −0.9 | 0 | 0 |
| card upgraded | 1,280 | +0.3 | +0.4 | 0 | 0 |
| max HP up / down | 625 / 651 | +2.1 / −1.7 | +2.6 / −0.1 | +2.2 / +1.0 | +3.2 / −2.8 |
| potion swapped | 871 | −0.3 | −0.2 | 0 | +0.1 |

Incense counter changes, A's D̂ against §723's table: slope 0.01, correlation 0.17 (n 92): A did not learn the
Incense phase.

## Disclosed after the run
- L's logistic did not converge in outer fold 4 (coef 0.0026 vs 0.0083-0.0092 in the other folds; float32 input, default
  100 lbfgs iterations). Refit on float64 (`results/l_convergence_check.py`, exploratory) every fold converges and L's
  MSE drops from 0.13497 to 0.13480, which moves A − L to about +0.00004. The verdict stays NOT_SHOWN; the frozen
  number favoured A.
- The reviewer's rerun with xgboost 3.4.1 gives A − L +0.000004 [−0.00114, +0.00114] (L identical, A slightly
  different): same verdict.
- Exploratory ceiling (`results/op_mean_ceiling.py`): predicting each pair by its operator's mean effect (cross-fit) scores −0.0011 against no
  effect. With effects of a few pp against ±1 outcome noise, this statistic leaves little room between models.

## Reading
- A predicts which states win the Heart far better than L (BCE −0.16), but not what a single change does. Its HP and
  potion effects are 1.2-2.3x too large and it misses relic removal (−0.7 vs −5.0 pp) and the Incense phase.
- Training on all fights as independent outcomes mostly teaches between-state differences (strong decks also have
  more HP and potions), so HP and potions take credit for deck strength. The paired structure (same seed, one
  change) is not used by the fit.
- L's shape is right but its scale, fitted across states, is too flat (HP −2.5 vs −7.1 pp).

## Decision
NOT_SHOWN (pre-registered) → no stage C now. Options for Philipp: fit on the paired differences directly
(within-base model: the control's outcome as a fixed offset, trees learn only the change), more labels per operator,
or adding the 4,253 observational Heart-entry states.
