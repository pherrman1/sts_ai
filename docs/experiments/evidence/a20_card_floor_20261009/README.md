# A20 card ranker on floor reached: offline result (2026-10-09)

Ledger §409. The [PLAN.md](PLAN.md) was committed at `5457e729`, before any
fit. The script is `tools/a20_card_floor.py` at `ea76456a` (SHA-256
`c20af9c4…`). Raw output (`report.json` copied here; boosters and
`validation_predictions.csv`) is in
`/mnt/project-files/a20-card-floor/run-ea76456a/`, which is not archived in Git.

## Data

The §402 corpus: producer `5ba068e0`, binary `dddb09f0…`, 240/240 parts, 0
dropped (state, k) groups. It has 1,200 card-reward states:

| split | states |
|---|---|
| TRAIN | 840 (158 of them in the inner early-stop set) |
| VALIDATION | 189 |
| TEST | 171 (closed) |

## Result: `NOT_SHOWN`

Selection gain is in floors versus V4's chosen card, on VALIDATION. CIs are
95% bootstraps that resample source seeds.

| arm | gain | 95% CI | agrees with V4 | picks skip |
|---|---|---|---|---|
| **CARD** (primary) | **−0.47** | **[−1.46, +0.43]** | 26% | 20% |
| ALL (cards + boss relics) | −0.39 | [−1.38, +0.60] | 33% | 16% |
| CARD_50 (half the TRAIN sources) | −0.41 | [−1.28, +0.41] | 31% | 16% |
| X2B (win model) | −0.88 | [−1.74, −0.06] | 24% | 20% |
| uniform random option | −0.95 | [−1.80, −0.13] | | |
| oracle (best observed, K=2, noise-inflated) | +3.92 | [3.00, 4.88] | | |

Paired contrasts:
- CARD − X2B: +0.42 [−0.43, +1.24].
- CARD − CARD_50: −0.06 [−0.71, +0.58], so the learning curve is flat.

V4 skips 4.2% of these states. Validation RMSE on the floor target is 12.2
floors for every arm.

## Reading (inference)

- V4 is the best card picker here. It beats a random card by about 1 floor
  (the CI excludes 0).
- X2-B ranks cards no better than random.
- A GBM on 840 states lands between X2-B and V4, and doubling its data does
  not move it.
- Beating V4 on A20 cards would need far more counterfactual states or a
  different model input, for example V4's own logits as a feature. More of
  the same rows is not supported by the flat curve, though two points are a
  weak curve.

## Post-hoc addendum: floor plus a win bonus (Philipp's question)

This was asked after the result and is not part of the plan's rule. The
target and the score are both `horizonFloor + B · finalWon`, from `--win-bonus`
at `5776676f`. Everything else is unchanged.

| B | CARD − V4 (floor + B·win units) | X2B − V4 | random − V4 |
|---|---|---|---|
| 0 (plan) | −0.47 [−1.46, +0.43] | −0.88 [−1.74, −0.06] | −0.95 [−1.80, −0.13] |
| 10 | −0.25 [−1.24, +0.72] | −0.81 [−1.79, +0.13] | −1.00 [−1.97, −0.06] |
| 25 | −0.68 [−2.06, +0.70] | −0.70 [−1.92, +0.46] | −1.08 [−2.24, +0.10] |

At B > 0 the gains are in floor + B·win units, not floors. At B = 25,
random − V4 has a CI that includes 0. The win term adds variance but no card signal, which fits §402's card
final-win option SD of about 0. Raw output is in
`/mnt/project-files/a20-card-floor/run-5776676f-wb{10,25}/`.

## Review note

Boss-reward card states can have a next-act map row, which is a leak. This
affects 7 of 189 VALIDATION states. Excluding them gives CARD − V4 −0.44
[−1.50, +0.50] (independent review), the same verdict.

## Follow-up: correction on top of the teacher's pick (§410)

The plan, [PLAN-CORRECTION.md](PLAN-CORRECTION.md), was committed before
fitting (`b7320e1c`). The script is `tools/a20_card_correction.py` at
`086e3a28`, and the report is `report-correction.json`. Raw output is in
`/mnt/project-files/a20-card-floor/corr-086e3a28/`.

The 71 boss card-reward states with a next-act map row are dropped, leaving
TRAIN 789, VALIDATION 182 and TEST 158 (closed).

**Result: `NOT_SHOWN`.**
- On the inner early-stop set, the model stopped after 2, 5 and 4 trees,
  depending on the seed.
- It predicts that every alternative is worse than the teacher's pick, so it
  never switches: 0 of 182 VALIDATION states, gain 0.
- For context, switching to a random alternative every time costs −1.22
  floors [−2.41, −0.03], and the noise-inflated oracle is +3.92.

**Reading (inference):** from these features and 789 states, nothing
predicts when an alternative beats the teacher's card.
