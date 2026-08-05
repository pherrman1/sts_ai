# Issue 36: token-state normalization stats for derived globs from wrong columns

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `train_strategic_tok.py`

## Symptom

The V4 token-state trainer's global mean/inv stats pass accumulated the first
50 **CSV** columns (`sub[:, :NGLOB]`), but CSV columns 44–49 are deck counts
`d0..d5` while state-file slots 44–49 hold six **derived** features
(hpFrac, missingHp, freePotionSlot, goldGeRemoval, canTakeEliteKey, bossNear).
`fwd_rows` then normalized the derived slots with deck-count statistics.

## Evidence

- `train_strategic_tok.py:300-308` (stats over `sub[:, :NGLOB]` = CSV cols) vs
  `:322-331` (derived slots written in the file layout) and `:455` (normalize
  with these stats).
- `apps/one_combat.cpp::richRow` (CSV block is 44 scalars then `d0..`).

## Why it matters

Self-consistent (train/export/C++ share the saved stats), so nothing breaks —
but the six derived features were standardized with the wrong scale, degrading
V4 quality. **All recorded V4 token-net results (incl. the deployed
`ooc_strategic_tok_final.native` and the 45.3% V4@3k baseline, EXPERIMENTS.md
§99) were trained with this defect** and must be re-derived after a retrain.

## Candidate fix direction

Compute derived values in the stats pass (mirroring the write pass) and
standardize slots 44–49 with their own stats.

## Relevant code

- `train_strategic_tok.py` (stats pass + fwd_rows normalization)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree (stats pass mirrors the write
pass). Rerun required: rerun-ledger row "V4 glob normalization" — retrain V4 →
re-export → simsweep + full gate stack vs `simsweep_v4_3k_256.csv` (GPU-gated).
