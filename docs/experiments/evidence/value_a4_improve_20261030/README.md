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
- `more_a4.pkl` (5432e85a…): `../value_clean_labels_20261029/tools/extract_a4.py more_a4.pkl` over the share dirs
  value-level-ab, ooc-map-only-search, az-gen2-ab, ooc-sibling-crn, ooc-swkeyed-labels, ooc-root-quality,
  expert-replay-ab, aivat-replay-676, boss-budget-probe, value-leaf-compare. Act-4 entries come from value-level-ab
  (1,668), ooc-map-only-search (1,261), az-gen2-ab (807), ooc-sibling-crn and ooc-swkeyed-labels (123 each, the same
  relogged games) and value-leaf-compare (93); the other four dirs contribute none in this layout. Older configs,
  Act 4 not strong; duplicates (seed, record, outcome) dropped (`core.entries(2)`), leaving 3,721. With
  ctm-calibration-ab (435) and az-gen3-explore (324) from `a4.pkl` that is 4,480 older entries from 8 campaigns.
- `states_a4.pkl` (6b5001e5…): `tools/extract_states.py`, all Act-4 states of Act-4-strong games (run 1 + stage-2 campaigns).
- Copies: `/mnt/project-files/value-a4-improve/` (SHA256SUMS).

## Reproduce
`VA4_DATA=DIR tools/run_all.sh` (DIR holds the four pkls; Python 3.13, numpy 2.5.3, xgboost 3.0.5, scikit-learn 1.9.1,
scipy 1.18.1, torch 2.15.0+cpu for exp7). Logs in [`logs/`](logs/) are that run, raw, except
`exp9_heart1_probe.log`, `exp9b_combos.log` and `exp10_finetune_eval.log`: these were trimmed (the `bce_sd` and `brier`
fields removed) and are not in `run_all.sh`; they need the npz files on the data branch `claude/va4-heart1-probe-data`
(`heart1_embed.npz`, `ft_*.npz`; produced on the PC by `tools/heart1_embed.py` / `tools/heart1_finetune.py`).
The deployable model in [`model/`](model/) is `tools/fit_va4.py`.
