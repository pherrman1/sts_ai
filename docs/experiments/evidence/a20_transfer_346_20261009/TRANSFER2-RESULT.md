# #346 transfer test 2: result

Ledger: [§407](../../ledger-06.md). Plan: [TRANSFER2-PLAN.md](TRANSFER2-PLAN.md),
committed at `f0e41fbf` before training. Report: [transfer2_report.json](transfer2_report.json)
(`python -m tools.vwin_a20_transfer … --e3-weights --extra-a0 …`, xgboost
3.4.0, 4 threads, 153 s). Models and validation predictions:
`/mnt/project-files/a20-transfer-346/transfer2-f0e41fbf/`.

**Verdicts under the plan:**
- **C (A0 + A20) vs A0 only:** `INCONCLUSIVE`.
- **B (A20 pretrain → A0) vs A0 only:** `INCONCLUSIVE`.
- **C vs D (A20 rows vs the same number of extra A0 rows):** `NO_DIFFERENCE_DETECTED`.
- **D vs A (descriptive):** `INCONCLUSIVE`.

Weight scale factor 7.899. Arms A, B and C reproduce the §405 reviewer's
post-hoc numbers to the fourth decimal.

D's extra rows are 16,590 #334 map rows from 96 TRAIN sources
(pool 89,866 rows). Their label win rate is 74.7%, against 77.6% for A0
TRAIN and 10.4% for A20.

## E3 VALIDATION map-row NLL (lower is better)

| A0 TRAIN used | A (A0 only) | C (+ A20) | B (A20 pretrain) | D (+ extra A0) |
|---|---|---|---|---|
| 10% | 0.5118 | 0.5043 | 0.5005 | 0.5143 |
| 25% | 0.4938 | 0.4844 | 0.4823 | 0.4989 |
| 50% | 0.4810 | 0.4767 | 0.4738 | 0.4901 |
| 100% | 0.4856 | 0.4769 | 0.4769 | 0.4864 |

Paired differences (95% CI, resampling E3 VALIDATION source seeds):

| Rung | C − A | B − A | D − A | C − D |
|---|---|---|---|---|
| 10% | −0.0075 [−0.0207, +0.0075] | −0.0113 [−0.0246, +0.0027] | +0.0025 [−0.0101, +0.0153] | −0.0100 [−0.0309, +0.0121] |
| 25% | −0.0094 [−0.0195, +0.0008] | −0.0115 [−0.0228, +0.0001] | +0.0051 [−0.0105, +0.0221] | −0.0145 [−0.0336, +0.0044] |
| 50% | −0.0043 [−0.0129, +0.0044] | −0.0072 [−0.0170, +0.0023] | +0.0092 [−0.0046, +0.0237] | −0.0135 [−0.0305, +0.0046] |
| 100% | −0.0087 [−0.0164, −0.0014] | −0.0087 [−0.0185, +0.0011] | +0.0009 [−0.0120, +0.0139] | −0.0095 [−0.0250, +0.0057] |

The pattern is consistent but no rule fires:
- Every C − A and B − A point estimate is negative (A20 data better).
- Every D − A estimate is positive (extra #334 rows slightly worse).
- Every C − D estimate is negative.
- Only C − A at 100% has a CI that excludes 0, and the rules key on the
  lower rungs.

The 50% A0-only model beats the 100% one (0.4810 vs 0.4856). The NLL curve is
not monotone at this data size, so rung-to-rung noise is about as large as
the effects being tested.

## Selection gain vs V4 (descriptive)

- **Boss relics:**
  - C − A: +7.2 pp [+3.5, +11.1] at 10%; +2.3, −0.5 and +1.2 pp at the
    higher rungs (CIs include 0).
  - C − D: +8.0 [+4.4, +11.8] at 10%, +7.7 [+3.6, +12.0] at 25%; +1.7 and
    +1.2 pp at 50% and 100% (CIs include 0).
  - D − A is −5.4 pp [−9.0, −1.8] at 25%. So at low A0 data the extra #334
    rows hurt relic ranking, while A20 rows help it.
- **Card rewards:** every difference has a CI that includes 0.

## Arm E (A20 model alone on A0)

NLL 1.629. Boss-relic ranking against A at 100%: −3.0 pp [−6.6, +0.7].

## Reading (Inference)

- With E3's weights, A20 rows do not measurably improve the A0 win model's
  calibration (NLL), and not measurably more than the same number of extra A0
  rows from #334 do.
- The point estimates lean toward A20 data being at least as useful as extra
  #334 rows, and more useful for boss-relic ranking when A0 data is scarce.
- That ranking result is descriptive (a secondary metric, not a rule) and
  is not corrected for multiple comparisons.

## Caveats

- D is not like-for-like: #334 rows are trajectory map rows from a different
  generator, not counterfactual option rows. A same-generator A0 control would
  need new A0 data from the §402 generator.
- Early stopping uses the scoring set (E3 VALIDATION). TEST is still closed.
- The re-test of arms A/B/C repeats an analysis whose result was known from
  review. Only D is new.
