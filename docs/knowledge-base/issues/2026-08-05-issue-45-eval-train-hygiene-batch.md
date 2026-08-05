# Issue 45: eval/train hygiene batch — stale defaults, import safety, misc

- **Status:** open
- **Tier:** Low
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05

## Symptom (batch)

- `train_strategic.py:38` defaults to `build/strategic_200.csv` while the tok
  trainer and `probe_cpsi.py` default to `build/strategic_tierb.csv`;
  `fit_vwin_calibration.py:19-21` writes `build/strategic_qwin_cal.csv` while
  `check_vwin_calibration.py:34-35` defaults to the uncalibrated
  `build/strategic_qwin.csv` — consumers can silently check pre-calibration data.
- `train_strategic.py` has no `if __name__ == "__main__"` guard (import-unsafe).
- `train_combat_cpsi.py:89`: `STRAT_EPOCHS` overrides `CPSI_EPOCHS` (env
  namespace collision).
- `eval_combat_pvnet.py:67`: val-seed filter hardcodes `< 20` instead of
  reading `PVNET_VAL_FRAC`.
- `train_combat_dist.py::export_model` receives unused `mon_cont_mean`;
  `probe_cpsi.py` "q10" slot is tau=0.05 (mislabel vs docstring);
  `train_combat_pvnet.py` avg_loss mixes row- and group-weighted terms, and
  normalization stats include val seeds; `eval_combat_pvnet.py:181` computes
  logits without `no_grad()`; `fit_vwin_calibration.py:191` re-reads all
  columns as float32 (crashes on any string column mid-remap);
  `export_strategic.py:55` hardcodes architecture dims.

## Evidence

- File:line references in the symptom list (verified 2026-08-05).

## Why it matters

Individually minor; collectively they are silent footguns (wrong CSV checked,
wrong epoch knob, wrong val filter) that have already cost one wrong headline
per `check_vwin_calibration`'s uncalibrated default (§94-96 context).

## Candidate fix direction

Batch cleanup: align defaults, add the `__main__` guard, rename
`STRAT_EPOCHS`→`CPSI_EPOCHS` collision, read `PVNET_VAL_FRAC`, drop dead args,
fix labels, add `no_grad`, guard the float32 re-read.

## Relevant code

- `train_strategic.py`, `train_strategic_tok.py`, `probe_cpsi.py`,
  `train_combat_cpsi.py`, `eval_combat_pvnet.py`, `train_combat_dist.py`,
  `fit_vwin_calibration.py`, `export_strategic.py`

## Resolution

Open — minor batch; no experiment rerun required.
