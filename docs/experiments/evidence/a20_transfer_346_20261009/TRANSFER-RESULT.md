# #346 GBM transfer test: result

Ledger: [§405](../../ledger-06.md). Plan: [TRANSFER-PLAN.md](TRANSFER-PLAN.md),
committed at `d10cc8da` before training. Report: [transfer_report.json](transfer_report.json)
(`python -m tools.vwin_a20_transfer`, xgboost 3.4.0, 4 threads, 112 s).
Models and validation predictions: `/mnt/project-files/a20-transfer-346/transfer-d10cc8da/`.

**Verdict under the plan: `TRANSFER_HELPS` for both C (mixed) and B (A20 → A0).**

Data: E3 A0 15,664 map rows (TRAIN 10,922 from 693 sources, VALIDATION 2,624
from 167 sources; 1 invalid (state, k) group dropped, as in §396). A20 16,590
rows. Label win rate: A0 TRAIN 77.6%, A20 10.4%.

## E3 VALIDATION map-row NLL (lower is better)

| A0 TRAIN used | A (A0 only) | C (A0 + all A20) | B (A20 pretrain → A0) |
|---|---|---|---|
| 10% | 0.5194 | 0.5105 | 0.4970 |
| 25% | 0.5117 | 0.4984 | 0.5009 |
| 50% | 0.5033 | 0.4909 | 0.4991 |
| 100% | 0.4990 | **0.4827** | 0.4911 |

Paired differences against A (95% CI, resampling source seeds):

| Rung | C − A | B − A |
|---|---|---|
| 10% | −0.0089 [−0.0227, +0.0053] | −0.0224 [−0.0334, −0.0116] |
| 25% | −0.0133 [−0.0247, −0.0021] | −0.0109 [−0.0209, −0.0012] |
| 50% | −0.0124 [−0.0242, −0.0004] | −0.0042 [−0.0138, +0.0050] |
| 100% | −0.0163 [−0.0274, −0.0062] | −0.0079 [−0.0150, −0.0017] |

C passes on the 25% and 50% rungs; B passes on 10% and 25%. Neither regresses
at 100%. C with 25% of the A0 labels (0.4984) matches A with all of them (0.4990).

## Selection gain vs V4 (descriptive)

Boss relics, difference to A at the same rung: C +4.5 pp [+1.2, +7.7] at 10%,
+1.9 [−1.1, +4.7] at 25%, +5.8 [+2.6, +9.4] at 50%, +2.2 [−0.6, +5.2] at 100%.
B: +3.0 [+0.4, +5.5], −0.4, +3.7 [+1.4, +6.2], −0.5. Card rewards: every
difference is within ±1.7 pp and every CI includes 0 (as in §396, card
choices hardly move the win label).

## Arm E (A20 model alone on A0)

NLL 1.538: unusable as an A0 probability, as expected (A20 win base rate 10%).
Its boss-relic ranking is worse than A at 100%: −4.5 pp [−7.8, −1.3]. So the
A20 model's rankings do not transfer directly; the benefit comes from training
with A20 data, not from using A20 values.

## Caveats

- Early stopping uses E3 VALIDATION, which is also the scoring set (E3's
  convention, the same for every arm). Absolute numbers are optimistic; TEST
  is still closed.
- C trains on more rows than A. This test shows A20 rows help, not that they
  help more than the same number of extra A0 rows would. #334's A0 rows are
  the natural control (F2 reached NLL 0.479 with them, §396 settings).
- Arm C's model can split on `ascension`; the trees were not inspected for
  how much they separate the two ascensions.
