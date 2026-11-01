# Heart-entry value fit on the paired design (stage B2): result

Pre-registration: [PREREG.md](PREREG.md) (review FAIL → convergence fix 513b5aec → delta PASS, before the real fit).
Run: frozen `fit_paired.py` (xgboost 3.0.5) on §731's labels and states, output [results/paired.json](results/paired.json);
14,000 pairs, 436 features, 46 min on 4 cores.

## Primary
Paired-difference squared error, B2 − L: **+0.00146 [−0.00010, +0.00302]** → **NOT_SHOWN** as frozen (xgboost 3.0.5). The reviewer's rerun with xgboost 3.4.1 gives
**WORSE**: +0.00172 [+0.00011, +0.00333] (all fits again at the cap, HP down −12.3 pp).

## Co-reported
| model | MSE of D | − no effect | corr(D̂, D) | operator calibration error |
|---|---|---|---|---|
| A (§732, refit) | 0.13484 | −0.0014 [−0.0028, +0.0001] | 0.123 | 0.00068 |
| L (Silver leaf, converged) | 0.13480 | −0.0014 [−0.0018, −0.0010] | 0.113 | 0.00074 |
| B2 (paired fixed effects) | 0.13626 | +0.0000 [−0.0018, +0.0019] | 0.124 | 0.00118 |

B2 − A +0.0014 [+0.0004, +0.0024]; A − L +0.00004 [−0.0011, +0.0012]; calibration error B2 − L +0.00045
[−0.00027, +0.00120].

Mean effect per operator (pp): observed, A, L, B2.

| operator | observed | A | L | B2 |
|---|---|---|---|---|
| HP down | −7.1 | −10.9 | −2.9 | −11.9 |
| HP up | +3.8 | +8.6 | +2.3 | +9.8 |
| potion removed | −7.2 | −8.7 | −2.9 | −11.7 |
| potion added | +5.0 | +8.4 | +2.9 | +10.7 |
| relic removed | −5.0 | −0.7 | −0.1 | −0.1 |
| relic counter | −2.7 | −0.5 | −0.2 | −0.3 |
| relic added | +1.4 | +0.6 | +0.0 | +0.2 |
| max HP up / down | +2.1 / −1.7 | +2.6 / −0.1 | +3.7 / −3.1 | +3.6 / −1.1 |
| card added / removed / upgraded | +2.2 / +0.5 / +0.3 | +0.7 / −0.9 / +0.4 | 0 | +0.4 / −0.5 / +0.4 |
| potion swapped | −0.3 | −0.2 | +0.1 | −1.4 |

Incense counter changes, B2 against §723: slope 0.04, correlation 0.14 (n 92).

## Disclosed after the run
- None of the 65 fixed-effects fits converged: every fit stopped at the 20-alternation cap, with a final offset change
  of 0.10-0.17 in the outer fits (median 0.15 over all fits; `fe_fits` in paired.json). The synthetic check converged
  in 8-10 alternations; on 436 features the trees and offsets keep trading. The verdict is reported as frozen.

## Reading
- Fitting only within-base differences did not help: B2's HP and potion effects are even larger than A's (about 1.6-2.6x
  the observed), and it still misses relic removal and counter changes. A plausible cause is that with 16 fights per base a
  flexible fixed-effects model overfits each base's few wins and losses (incidental-parameter bias); since the
  alternation never settled, this is not shown.
- A and L, with very different structure, both reach about −0.0014 against predicting no effect, close to an
  operator-mean predictor (−0.0011); B2 reaches +0.0000. At 16,000 labels the single-change effects are too small
  against ±1 outcome noise for a flexible model to learn more than the average price per kind of change.
- The prices themselves are estimated well by the plain averages of §731 (HP −7.1 / +3.8 pp per 5-30% of max HP,
  potion −7.2 / +5.0, relic removed −5.0 pp). Silver's leaf has the right signs but values HP and potions at about
  40% (losses) to 60% (gains) of their Heart-kill price.

## Decision
NOT_SHOWN → no stage C from B2. A general value that learns interactions needs far more labels per kind of change, or a
model with much less freedom (a price per field, shrunk); that choice goes to Philipp.
