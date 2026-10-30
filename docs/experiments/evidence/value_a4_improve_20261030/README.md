# Improve V_A4 (Act-4 entry value) offline (2026-10-30)

Philipp, 2026-10-30 12:03Z: try to improve V_A4 (architecture, parameters, more data, other models, more epochs).
Baseline: §720 ([value_clean_labels_run1](../value_clean_labels_run1_20261029/RESULT.md)): G (XGBoost on the public
entry record, `s0.features`) and GC (G + the Act-4 CTM logit). Offline only: no gameplay, no seeds run.

## Protocol
- The run-1 TEST split (seed % 4 == 3) was read for §720, so every selection here uses the **dev pool seed % 4 != 3**
  only: 5-fold CV grouped by seed, 3 fold assignments (`core.oof`), out-of-fold predictions averaged over the 3.
- Score: per-game BCE and Brier R² on the dev **core** entries (stage-2 entries, 1 game; run-1 entries, 5 games);
  paired differences with a seed-cluster bootstrap (`core.paired`). Extra training sources are never scored.
- The old TEST is read once at the end (`oldtest_check.py`), secondary only.

## Data
- `a4.pkl` (stage 2, sha256 253e3178…) and `run1_a4.pkl` (§720, 2911d98b…) from `/mnt/project-files/value-clean-labels/`.
- `more_a4.pkl` (5432e85a…): `../value_clean_labels_20261029/tools/extract_a4.py` over value-level-ab,
  ooc-map-only-search, az-gen2-ab, ooc-sibling-crn, ooc-swkeyed-labels, ooc-root-quality, expert-replay-ab,
  aivat-replay-676, boss-budget-probe, value-leaf-compare (the last four yield no complete Act-4 games in this layout).
  Older configs, Act 4 not strong; exact duplicates (seed, record, outcome) dropped (`core.entries(2)`).
- `states_a4.pkl` (6b5001e5…): `tools/extract_states.py`, all Act-4 states of Act-4-strong games (run 1 + stage-2 campaigns).
- Copies: `/mnt/project-files/value-a4-improve/` (SHA256SUMS).

## Reproduce
`VA4_DATA=DIR tools/run_all.sh` (DIR holds the four pkls; Python 3.13, numpy 2.5.3, xgboost 3.0.5, scikit-learn 1.9.1,
scipy 1.18.1, torch 2.15.0+cpu for exp7). Logs in [`logs/`](logs/) are that run; the deployable model in
[`model/`](model/) is `tools/fit_va4.py`.
