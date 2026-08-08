# 2026-08-08 — check_vwin_calibration.py default CSV resolved as not-a-bug: `build/strategic_qwin.csv` stays the default

Date: 2026-08-08
Session/task: Inspect Issue #45's claim that `check_vwin_calibration.py`'s
default CSV path is stale and should point at the calibrated
`build/strategic_qwin_cal.csv`.

## Decision

Do not change the default. `check_vwin_calibration.py:42` correctly defaults
`CSV` to `build/strategic_qwin.csv` (the uncalibrated primary artifact).
Issue #45's stale-default sub-item is closed as not-a-bug; no code changes
were made to `check_vwin_calibration.py`, `fit_vwin_calibration.py`, or any
other file.

## Rationale

- The checker keeps only terminal chosen rows: it filters to
  `labelBootstrap==0` AND `chosen==1`
  (`check_vwin_calibration.py`, `read_cols = ["labelBootstrap", "won",
  "chosen"] + state cols`; filter mask in the chunk loop). Its whole purpose,
  per its docstring, is to compare native-win-tree V_win predictions against
  the live run's terminal outcome `won` — for which the calibration state of
  the file is immaterial.
- `fit_vwin_calibration.py` modifies exactly one column — `labelWon` — and
  only on censored rows (`ch.loc[m, "labelWon"] = C(...)` where `m` is
  `labelBootstrap==1`, `fit_vwin_calibration.py:200-202`). The checker never
  reads `labelWon` (grep: only docstring mentions). Terminal rows are
  value-identical in both CSVs, so the checker's output is identical
  regardless of which path it receives.
- The "wrong headline" that Issue #45 points to (§94-96 context) was caused
  by the base_score logit-vs-probability bug in the checker's Python
  tree-walk (false Brier 0.232 / max-decile 0.42), not by the CSV default;
  EXPERIMENTS.md §94/§95 record that `parity_vwin.py` + `one_combat
  winnettest` caught and corrected it. Label: **Inference** for the causal
  attribution from the experiment log text; the column/filter/read facts
  above are direct code observations.

## Alternatives considered

- Change the default to `build/strategic_qwin_cal.csv` — rejected: a no-op
  for this script (terminal rows identical in both files) that would create
  the misleading impression that the checker depends on the calibration.
- Add `labelWon` to the checker's reads to audit the calibrated values — out
  of scope: that would change calibration semantics, which Issue #45's
  resolution explicitly must not do (it would also be a feature request, not
  a stale-default fix).

## Evidence

- `check_vwin_calibration.py:42` (`CSV = ARGS[0] if ... else
  "build/strategic_qwin.csv"`); `check_vwin_calibration.py` chunk loop
  (`labelBootstrap==0 & chosen==1` filter; `read_cols` never includes
  `labelWon`).
- `fit_vwin_calibration.py:200-202` (remap only on `labelBootstrap==1`).
- `EXPERIMENTS.md` §94/§95 (wrong-headline root cause: base_score logit bug,
  fixed via `parity_vwin.py` / `one_combat winnettest`).
- Issue `docs/knowledge-base/issues/2026-08-05-issue-45-eval-train-hygiene-batch.md`.

## Status and follow-up

- Implemented (decision recorded; issue sub-item closed as not-a-bug).
- Remaining Issue #45 sub-items (trainer CSV defaults, `__main__` guard,
  `STRAT_EPOCHS`/`CPSI_EPOCHS` collision, `eval_combat_pvnet.py` val-seed
  hardcode, misc) stay open.
