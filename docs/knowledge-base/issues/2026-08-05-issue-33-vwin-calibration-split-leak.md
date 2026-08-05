# Issue 33: fit_vwin_calibration isotonic fit leaks the validation split

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `fit_vwin_calibration.py`

## Symptom

The isotonic (PAVA) calibration map was fit on **all** terminal rows
(`p_all`, `y_all` — no `fit` mask) while its "validation" deciles were computed
on the held-out rows only. Platt and raw were honestly fit on fit rows only,
so the map-selection rule (`fit_vwin_calibration.py:174-185`) compared isotonic
(in-sample-optimistic) against honest baselines and could select the isotonic
map (and remap every censored `labelWon` row) based on a contaminated Brier.

## Evidence

- `fit_vwin_calibration.py:137-162` (PAVA over all rows), `:172` (validation on
  `~fit`), `:174-185` (selection).

## Why it matters

The selected map produced the corrected labels in `build/strategic_qwin_cal.csv`
and `_calmap.json`, the primary input of the whole Q_win continuation chain
(V5 qwin_cal, dist wave, Phase F, label-noise wave, map-DAG E1 base). A leaky
selection means the corrected dataset is not what the recorded Brier/decile
comparisons claim.

## Candidate fix direction

Fit PAVA on fit rows only; record isotonic validation Brier alongside the
others in the map metadata.

## Relevant code

- `fit_vwin_calibration.py` (PAVA + selection + meta)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: PAVA fits on `p_all[fit]`
rows only; `iso_val_brier`/`iso_val_cal` added to `_calmap.json`. Rerun
required before any future Q_win retrain (rerun-ledger row "calibration split
leak"); the falsified Q_win line's recorded negatives stand as recorded.
