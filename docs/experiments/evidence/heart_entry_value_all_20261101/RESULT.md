# Heart-entry value fit on both label rounds (stage B3): result

Pre-registration: [PREREG.md](PREREG.md) (review FAIL → curve-rule fix → PASS at 69e6026a, before the real fit).
Run: frozen `fit_all.py` on `../heart_entry_perturb2_20261101/results/labels_all.csv` (4,252 bases, 1,437 source
seeds, 59,528 pairs, 440 features), output [results/all.json](results/all.json); 69 min wall, 265 CPU-min.
Versions: xgboost 3.0.5, scikit-learn 1.9.1, numpy 2.5.3 (written to all.json).
The results reviewer's rerun with xgboost 3.4.1 also gives PASS (A − L −0.00179 [−0.00240, −0.00119], A100 − A50
−0.00041 [−0.00069, −0.00014], per-change means within 0.1 pp), so unlike §733 the verdict holds across versions.

## Primary
Paired-difference squared error, A (all-feature GBM, 100% of training seeds) − L (Silver leaf, converged):
**−0.00180 [−0.00240, −0.00121]** → **PASS**. On round-2 pairs only: −0.00202 [−0.00269, −0.00134].

## Learning curve and skill
| model | MSE of D | − no effect | corr(D̂, D) |
|---|---|---|---|
| A, 25% of training seeds (~857 bases) | 0.13964 | −0.0025 [−0.0032, −0.0019] | 0.140 |
| A, 50% (~1,676 bases) | 0.13911 | −0.0031 [−0.0037, −0.0024] | 0.149 |
| A, 100% (~3,402 bases) | 0.13870 | −0.0035 [−0.0042, −0.0027] | 0.160 |
| L (Silver leaf, converged) | 0.14050 | −0.0017 [−0.0019, −0.0015] | 0.121 |
| op-mean (mean D per change type) | 0.14057 | −0.0016 [−0.0020, −0.0013] | 0.101 |
| no effect | 0.14217 | 0 | – |

A − L at 25/50/100%: −0.00086 [−0.00138, −0.00034], −0.00140 [−0.00190, −0.00089], −0.00180 [−0.00240, −0.00120].
A100 − A50 −0.00041 [−0.00067, −0.00014]; A100 − A25 −0.00095 [−0.00130, −0.00060]. `curve_branch` = true: A was
still improving at the top of the curve. The log-linear extrapolation in all.json (−0.00047 per doubling) is
descriptive and rough; it is not used for the verdict.

At §732's scale (1,000 bases, 16,000 labels) A and L were tied; with 4.3× the bases A is clearly better than both L
and the per-change-type average. A's skill against no effect is about twice L's and op-mean's (CIs do not overlap;
the paired A − op-mean difference was not pre-registered and is not computed).

## Mean effect per change type (pp, held out)
| change | n | observed | A 100% | L | op-mean |
|---|---|---|---|---|---|
| HP down | 7,369 | −7.4 | −9.4 | −3.1 | −7.4 |
| HP up | 3,580 | +5.5 | +8.7 | +2.5 | +5.5 |
| potion removed | 3,491 | −7.8 | −8.7 | −3.1 | −7.9 |
| potion added | 4,212 | +5.3 | +8.8 | +3.1 | +5.3 |
| relic removed | 5,505 | −5.0 | −1.0 | 0.0 | −5.1 |
| relic counter | 4,494 | −1.9 | −0.8 | −0.2 | −1.9 |
| relic added | 5,500 | +1.7 | +1.0 | 0.0 | +1.7 |
| max HP up / down | 2,741 / 2,676 | +2.2 / −2.2 | +2.9 / −0.2 | +3.9 / −3.3 | +2.2 / −2.2 |
| card added / removed / upgraded | 5,491 / 5,451 / 5,416 | +0.4 / −1.4 / −0.3 | +0.9 / −1.0 / +0.3 | 0 | +0.4 / −1.4 / −0.3 |
| potion swapped | 3,602 | −0.5 | −0.4 | 0.0 | −0.5 |

A ranks states better than any other model but is miscalibrated on average: it overstates HP and potion changes by
1.1-1.7× and understates relic removal (−1.0 vs −5.0) and max-HP loss (−0.2 vs −2.2). A is trained on win/loss of
states, not on the paired differences, so these average errors are not corrected by the fit.

## Decision (pre-registered)
PASS → pre-register stage C: A as Silver's S&S win leaf in §724's S&S → Heart chain. Runs need Philipp's go.
The calibration gaps above (relic removal, HP/potion scale) are the obvious risk for stage C and go into its
pre-registration as co-reported checks.
