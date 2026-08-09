# 2026-08-09 — Zero-mean ranking correction for the combat leaf value

Date: 2026-08-09
Session/task: Implement the experimental `STS_VNET_RANK_CORR` correction
model: a small XGBoost model predicting `leafref.referenceValue -
endHp_pred` residuals (group-centered), added on top of the primary
vnet/PVNet leaf value with a fair-path search-complete zero-mean clamp.

## Decision

- New standalone training script `tools/train_rank_correction.py`: joins a
  leafdiag CSV with its leafref CSV on `(seed, fightIdx, decIdx, obsHash)`,
  computes `residual = referenceValue - endHp_pred`, centers the residual to
  zero-mean within each decision group, and trains a small XGBoost model
  (max_depth 6, eta 0.05, subsample 0.8, colsample_bytree 0.7,
  min_child_weight 20, 100 rounds, 20-round early stop) on the SAME
  733-feature combat layout as the deployed vnet (std>1e-9 filter on
  combatgen rows, not leafdiag rows), with the same fight-group
  `GroupShuffleSplit` (test_size 0.15, random_state 0) as
  `train_value_combat.py`. Export via `export_combat_model.py::export_trees`
  plus a vnettest parity CSV.
- New env var `STS_VNET_RANK_CORR=<path>` (parsed after the STS_VNET region
  in `apps/one_combat.cpp::main`, non-fatal on failure): loads the correction
  model into the new globals `search::g_combatVNetRankCorr` /
  `search::g_useVNetRankCorr` (declared in `include/sim/search/CombatValueNet.h`,
  defined in `src/sim/search/CombatValueNet.cpp`).
- The correction is ADDED (not blended) on top of the primary prediction in
  `BattleScumSearcher3::evaluateLeaf` (vnet + PVNet branches), the S3
  leaf-blend site in `step()` (where the leafdiag `endHp_pred` column comes
  from — without this the ranking acceptance is unsatisfiable), and
  `BattleScumSearcher2::evaluateLeafState` (vnet branch, terminal and
  non-terminal). Each applied correction is accumulated into the per-searcher
  `rankCorrValues` member; at search-complete in the fair paths
  (`ScumSearchAgent2::playoutBattleFair`) `clampRankCorrAtRoot()` subtracts
  the per-search mean correction from every root edge's stored mean value
  (threshold |mean| > 0.1), leaving visit counts — and therefore the root
  action choice — untouched. The non-fair S2 path clears the accumulator at
  `advanceRoot` (per-decision boundary) without clamping.
- Experimental arm only: `STS_VNET_RANK_CORR` is off by default; nothing is
  promoted without a paired gameplay gate. With the env var unset the
  behavior is byte-identical to the pre-change code (verified by an 8-seed
  fair-S3 structural-equality smoke against the pre-change commit).

## Rationale

The deployed end-HP vnet ranks leaf states within a decision group at
~0.725-0.726 pairwise accuracy vs the high-budget leafref references
(EXPERIMENTS.md §134-§137) — the HP scale is right but the ordering is
sub-optimal. The correction model targets exactly that gap: residuals are
group-centered so the model is scale-neutral by construction, and the
fair-path clamp enforces zero-mean at runtime, so the HP scale of the leaf
value is preserved while within-group ordering can improve. The leafref
reference is itself a Searcher3 evaluation using the same deployed vnet
(not model-free), so the correction may learn reference-vnet-blend bias
rather than true ranking error (**Inference** — same caveat as the existing
leafref analysis).

## Alternatives considered

- Fine-tune the deployed vnet on leafref targets
  (`tools/train_vnet_ranking.py`) — already explored; a separate additive
  model keeps the deployed vnet untouched and lets the correction be
  enabled/disabled independently per run.
- Multiply/blend the correction into the alpha blend — rejected: an additive
  correction on the vnet side keeps the (1-alpha) rollout term's scale
  intact and matches the residual semantics (HP units).
- Apply the correction only inside `evaluateLeaf`/`evaluateLeafState`
  (the plan's literal step 5) — rejected: the S3 leaf-blend site in
  `step()` is where the MCTS leaf value actually enters the tree AND where
  the leafdiag `endHp_pred` column (the training target's base) is captured;
  without the blend-site application the leafdiag ranking acceptance
  criterion is unsatisfiable. This is a deliberate, documented deviation
  from the plan's literal file list.

## Evidence

- `tools/train_rank_correction.py` — training script (733 features confirmed
  on `build/vcombat_honest.csv`).
- Smoke run on `build/leafdiag_smoke_16.csv` (seeds 126700-126715, extracted
  from `build/leafdiag_gate_64.csv`) joined to `build/leafref_gate_64_4k.csv`:
  68,534/73,643 rows joined; centered-residual val RMSE 11.8 / MAE 7.4 (10
  smoke rounds); held-out ranking pairwiseAcc 0.646 vs baseline 0.649
  (smoke-only, no signal expected at 10 rounds).
- `one_combat vnettest build/v_rank_corr_smoke.txt
  build/v_rank_corr_smoke_parity.csv` — PASS, max|diff| = 0.000001
  (tolerance 0.001).
- `STS_FAIR=1 STS_SEARCHER3=1 STS_VNET_RANK_CORR=build/v_rank_corr_smoke.txt
  ./build/one_combat bestbench 300 4 0` — loads and completes; banner
  `[V_combat rank-correction ON: <path>, 10 trees]`.
- Byte-identical default: 8-seed fair-S3 `bestbench` output of the new
  binary matches the pre-change commit `42dbf13` binary (modulo cpu_sec).
- `ctest --test-dir build` — 15/15 pass.

## Status and follow-up

- Implemented, experimental, NOT a default. Follow-ups: train on the full
  gate corpus, run `tools/leaf_ranking.py` on a corrected leafdiag capture
  (16 seeds), then a paired fair-S3 @1k/32-seed gameplay gate before any
  promotion consideration.
