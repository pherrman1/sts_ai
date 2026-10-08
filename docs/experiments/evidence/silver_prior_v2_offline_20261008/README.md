# Synthetic Silver root prior v2: offline replay (ledger §400)

- Corpus and folds: the §397 `silversynthgen` corpus (450376c8), unchanged.
  Train folds 0-2, validation fold 3, test fold 4 (43 test seeds).
- Features: `one_combat silversynthfeatures` at this PR's commit, which adds an
  `after` row per root action (one sampled post-action state). Prior v2 input:
  root state (1,766) ++ action block (22) ++ (after state − root state)
  (1,766) = 3,554 columns.
- Model: LightGBM, same tree parameters as §397, custom per-root softmax
  cross-entropy against the 10k visit shares, up to 6,000 rounds, early stop
  100. Stopped at 2,981 rounds (`train-v2.json`).
- Pipeline: `tools/silver_prior_v2.py train|tasks|pickweight|report`; replay
  with `one_combat silversynthreplay` (no game seeds are played).
- Weight: picked on 1,000 validation roots at 1,000 sims from
  {200, 400, 800, 1600, 3200}: 1600 (`weight-v2.json`). v2 at w = 400 is a
  secondary arm.
- Test: 4,094 roots x 2 replay seeds = 8,188 runs per arm, 0 dropped
  (`report-v2.json`). CIs are 95% seed-clustered percentile bootstraps.
- Fit on validation roots (fold 3, 32,342 roots): per-root cross-entropy
  uniform 1.669, v1 1.244, v2 1.192, entropy floor 0.700. Top action equals the
  10k top action: v1 55.1%, v2 58.5%; a second independent 10k search agrees
  74.99% (8,186 roots with a second search). On roots where both 10k searches
  agree, v2 matches them 66.8% (v1 62.8%). Computed with
  [`compare_v1_v2.py`](compare_v1_v2.py). Fold 3 also served as both models'
  early-stopping set, so these fit figures are slightly optimistic for both.
- Model, root files, replay tasks and outputs:
  `/mnt/project-files/silver-synthetic-prior/prior-v2-20261008/`.
