# Phase-12 M0/M1 autopsy — corrected after reverted draft

Date: 2026-08-15
Baseline: `ab18dce5877774f17cc1f55c015a823c9820e790`
Branch: `phase12-m0-m1-autopsy-fixed`
Status: corrected post-hoc analysis; no retraining, gameplay, or new seeds

## Executive result

M0 and M1 have identical policy supervision (`chosen`). Marginalization changes
auxiliary Q supervision with `Q_target = 10*labelWon + labelHp`.

On 39,870 matched groups: Q-target argmax disagreement was **16,951/39,870
(42.52%)**; exact top-two reversal **3,338/39,870 (8.37%)**; predicted-Q
argmax disagreement **9,932/39,870 (24.91%)**; and model policy-logit
argmax disagreement **3,154/39,870 (7.91%)**, concentrated on SHOP (32.08%)
and UPGRADE_SELECT (33.30%) versus CARD (3.90%) and TREASURE (0.00%). Mean
target margin fell from 6.9049 to 5.7728. The strict gameplay result remains
M0 23/64 (35.9%) vs M1 16/64 (25.0%), Δ −10.9pp, approximately
[−25.0,+3.1]pp; the interval crosses zero.

## Verified mapping and semantics

Serena verified `include/game/GameContext.h::sts/ScreenState`:

| numeric | enum |
|---:|---|
| 1 | EVENT_SCREEN |
| 2 | REWARDS (CARD groups) |
| 3 | BOSS_RELIC_REWARDS |
| 4 | CARD_SELECT (UPGRADE_SELECT groups) |
| 5 | MAP_SCREEN (absent) |
| 6 | TREASURE_ROOM |
| 7 | REST_ROOM |
| 8 | SHOP_ROOM |

The trainer uses `chosen` for policy CE and `10*labelWon + labelHp` for
absolute Q MSE. `labelFloor` and `labelBootstrap` do not enter the current
loss. `q_top1` compares predicted-Q argmax with Q-target argmax; policy
`margin` is policy-logit top1−top2. All argmax decisions use first-occurrence
tie-breaking, matching `numpy.argmax` and the trainer; top-two extraction and
reversal use `np.argsort(-x, kind="stable")`, so tied values resolve to the
earlier row. The M0/M1 `chosen` supervision is asserted identical for every
matched row, and duplicate action rows are retained in source order.

## Provenance

| artifact | path | SHA256 |
|---|---|---|
| M0 corrected dataset | `/tmp/phase12b_m0_screen_corrected.csv` | `5276ad8fc80f828243ed1f7ff781ec727ab6056ff9467862a6eccc18186b3df0` |
| M1 corrected dataset | `/tmp/phase12b_m1_screen_corrected.csv` | `f1a92de6705aa46fadad20b51b9da184de51c184b20fad2e2f2f4749fde10b59` |
| strict M0 checkpoint | `/tmp/strict_m0_best_ce.pt` | `e600d1bfebbebb5c6b4059eb7f29dcb1c08b9a318178c43c6d77d5744f369b2e` |
| strict M1 checkpoint | `/tmp/strict_m1_best_ce.pt` | `3c98841018f5c6742238c4c192b22a6d2a35f352615e10e4f8e3941a72fd2102` |
| strict M0 native | `/tmp/strict_m0_best_ce.native` | `97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a` |
| strict M1 native | `/tmp/strict_m1_best_ce.native` | `80995be6e626b7f0278d6ac376d34718863480ef51783f20bd526f3f098c91f0` |

Dataset rows/groups: 210,838/39,870. Semantic group counts: CARD 27,568;
EVENT 2,832; BOSS_RELIC 696; UPGRADE_SELECT 1,084; TREASURE 1,294; REST
3,260; SHOP 3,136.

## Label/Q table

| screen | groups | Q diff | top-two reversal | M0 margin | M1 margin | Δ margin |
|---|---:|---:|---:|---:|---:|---:|
| ALL | 39,870 | 42.52% | 8.37% | 6.9049 | 5.7728 | −1.1320 |
| EVENT | 2,832 | 32.95% | 21.79% | 13.2677 | 11.0801 | −2.1876 |
| CARD | 27,568 | 44.88% | 6.34% | 6.0548 | 5.0041 | −1.0507 |
| BOSS_RELIC | 696 | 1.58% | 1.01% | 8.8555 | 8.8534 | −0.0020 |
| UPGRADE_SELECT | 1,084 | 44.37% | 1.85% | 2.0799 | 1.9665 | −0.1134 |
| TREASURE | 1,294 | 30.68% | 30.68% | 11.8743 | 8.4579 | −3.4164 |
| REST | 3,260 | 26.29% | 10.61% | 9.2308 | 8.2940 | −0.9368 |
| SHOP | 3,136 | 60.62% | 6.51% | 5.3982 | 4.6412 | −0.7570 |

Overall action-row M1−M0 statistics across all 210,838 matched rows, reported
as mean / median / mean absolute / within-decision centered absolute:
`labelWon` 0.000913/0/0.054109/0.044798; `labelHp` 0.031911/0/7.879336/
6.138981; `labelFloor` 0.016875/0/1.341882/1.135842; `labelBootstrap`
0.000634/0/0.054882/0.051060. Action-row 5/95% quantiles: `labelWon`
[−0.164786, +0.159648]; `labelHp` [−21.5, +22.5]; `labelFloor` [−4.084828,
+3.717980]; `labelBootstrap` [−0.25, +0.25]. Decision-weighted means (mean of
per-decision means) are 0.000919, 0.036456, 0.013027, and 0.000570; an
earlier draft mislabeled these decision-weighted values as action-row
statistics.

## Model-output table

| screen | groups | policy diff | predicted-Q diff | policy margin M0/M1 | entropy M0/M1 |
|---|---:|---:|---:|---:|---:|
| ALL | 39,870 | 7.91% | 24.91% | 5.4526 / 5.0465 | 0.5154 / 0.5271 |
| EVENT | 2,832 | 11.02% | 17.62% | 0.5024 / 0.5451 | 0.8744 / 0.8630 |
| CARD | 27,568 | 3.90% | 25.95% | 7.4275 / 6.8516 | 0.2632 / 0.2710 |
| BOSS_RELIC | 696 | 11.35% | 14.08% | 1.1438 / 1.0313 | 0.8040 / 0.8557 |
| UPGRADE_SELECT | 1,084 | 33.30% | 47.79% | 0.5449 / 0.5402 | 2.2423 / 2.2458 |
| TREASURE | 1,294 | 0.00% | 3.25% | 3.3610 / 3.3466 | 0.1506 / 0.1512 |
| REST | 3,260 | 9.85% | 5.25% | 1.1246 / 1.0700 | 0.5924 / 0.6111 |
| SHOP | 3,136 | 32.08% | 46.11% | 0.5762 / 0.5270 | 1.8180 / 1.8761 |

All-input predicted-Q top-1 fidelity: M0 25.72%, M1 25.67%.

## Complete A/B/C cross-classification

A = Q-target argmax same; B = model policy argmax same; C = model predicted-Q
argmax same. All cells come from the same records as the headline metrics.

| A | B | C | groups |
|---|---|---|---:|
| different | different | different | 571 |
| different | different | same | 951 |
| different | same | different | 4,065 |
| different | same | same | 11,364 |
| same | different | different | 483 |
| same | different | same | 1,149 |
| same | same | different | 4,813 |
| same | same | same | 16,474 |
| **total** |  |  | **39,870** |

Marginals: A different=16,951; B different=3,154; C different=9,932.

## Prediction artifact provenance

The model-output table was computed from inference-only prediction CSVs
produced by the committed `STRAT_PREDICT_ONLY=1` mode of
`train_strategic_tok.py` (which uses the exact training-time `fwd_rows()`
tensor preparation; this commit adds the policy-logit column to that export,
previously emitted only by the session's ad-hoc copy). Both artifacts were
regenerated with the committed script and verified **byte-identical**:

| artifact | path | SHA256 | rows |
|---|---|---|---:|
| M0 predictions | `/tmp/c0_preds.csv` | `64f294e90518baff0c9bd9dbeca8288e11ae8eade0bb8f7e30c8baed68933e39` | 39,870 groups |
| M1 predictions | `/tmp/c1_preds.csv` | `3969c9df10566c3b6b97bb86f75569e3cf38753d20c9f3d337b0d6e9e71e789d` | 39,870 groups |

Generation commands (exact, from repo root; the second positional argument
names the trainer output prefix whose `_tok_state.bin` is rebuilt from the
corrected CSV):

```bash
PYTHONPATH=. STRAT_DEVICE=cuda STRAT_TOK_COMPILE=0 STRAT_PREDICT_ONLY=1 \
  STRAT_PREDICT_CKPT=/tmp/strict_m0_best_ce.pt \
  STRAT_PREDICT_OUT=/tmp/c0_preds.csv \
  python3 train_strategic_tok.py /tmp/phase12b_m0_screen_corrected.csv /tmp/c0

PYTHONPATH=. STRAT_DEVICE=cuda STRAT_TOK_COMPILE=0 STRAT_PREDICT_ONLY=1 \
  STRAT_PREDICT_CKPT=/tmp/strict_m1_best_ce.pt \
  STRAT_PREDICT_OUT=/tmp/c1_preds.csv \
  python3 train_strategic_tok.py /tmp/phase12b_m1_screen_corrected.csv /tmp/c1
```

Checkpoint hashes are the strict values above (`e600d1bfebb…4f369b2e`,
`3c98841018f5…fd2102`), verified before inference; the label inputs are the
corrected datasets hashed in the provenance table. The regenerated CSVs
matched the original artifacts byte-for-byte (`cmp` PASS), and the autopsy
script rerun on them reproduced the headline numbers unchanged (Q-target
disagreement 16,951 = 42.52%, predicted-Q 9,932 = 24.91%, policy 3,154 =
7.91%, reversal 3,338 = 8.37%).

## Root causes of reverted-draft errors

The screen error came from using diagnostic `gateKind`-like numbering instead of
the numeric trainer `screen` field and `ScreenState` enum. The cross-table error
was a hand-assembled report: the reverted commit contained no analysis script,
and the table omitted every B-different cell while the policy headline came
from separate ad-hoc inference. The corrected script uses one numeric mapping,
preserves duplicate rows, derives all booleans once, emits all eight cells, and
asserts every marginal.

## Interpretation and decision

Established: M1 changes Q targets substantially and model Q outputs more often
than policy outputs; M1 is not clearly less faithful to its own Q target.
Inference: auxiliary-Q/representation coupling remains plausible because Q
supervision changes while policy labels are fixed and policy outputs diverge in
7.91% of groups overall — a smaller overall rate than predicted-Q divergence,
but strongly concentrated, with SHOP policy disagreement at 32.08% and
UPGRADE_SELECT at 33.30% versus CARD 3.90% and TREASURE 0.00%. This does not
establish that any screen caused a gameplay loss or explain the −10.9pp point
estimate causally.

**STOP the M0/M1 investigation.** No M2, retraining, new seeds, gameplay
tracing, label generation, or model changes are justified.