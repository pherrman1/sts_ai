# Issue 39: train_combat_dist validation split is never used

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `train_combat_dist.py`

## Symptom

`train_combat_dist.py` builds a 90/10 fight split (`train_fights`/`val_fights`),
prints it, and then trains only on `train_fights` — but never evaluates
`val_fights`; best-model selection uses the **training** loss
(`if avg_loss < best_loss: export_model(...)`). The docstring advertised a
nonexistent `[TEACHER]` argument and an unused `[VAL]` argument.

## Evidence

- `train_combat_dist.py:444-454` (split), `:456-497` (train-only selection),
  `:19` (stale usage line).

## Why it matters

The exported "best" artifact was selected on train loss (overfit-prone) with
no validation; dist models consumed by the Q_win calibration chain
(`ooc_strategic_qwin_cal_dist_*`) were selected this way.

## Candidate fix direction

Evaluate val loss per epoch (same chunk/sample gates) and select on it.

## Relevant code

- `train_combat_dist.py` (epoch loop + validation_loss)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: `validation_loss()` per epoch,
best-model selection on val loss, docstring corrected. Rerun ledger: the dist
models of the (falsified) Q_win calibration line were selected on train loss —
re-select only if that line reopens.
