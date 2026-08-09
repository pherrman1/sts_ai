# 2026-08-09 — DeepSets combat VNet implementation and MCTS leaf-state diagnosis

Date: 2026-08-09
Session/task: Implemented DeepSets combat value net (C++ + PyTorch), then diagnosed catastrophic online failure via MCTS leaf-state tracing.

## Decision

1. **Implemented a DeepSets combat value net** (`train_combat_deepsets.py`,
   `combat_deepsets_v1` format in `CombatValueNet.cpp`) treating combat state
   as permutation-invariant sets (cards by zone, relics, potions, monsters,
   encounter) with learned embeddings, sum/mean-pooling, and an MLP head.
   Architecture: 90K params. C++ parity verified (max|diff| < 0.001).

2. **Extended `STS_VNET_QUERY_LOG`** to capture parentObsHash and search depth
   alongside every VNet evaluation, enabling sibling-grouped MCTS leaf-state
   analysis without modifying search logic.

3. **Diagnosed the DeepSets online failure** (0% win vs XGBoost 31%) via
   fixed-leaf-state comparison on identical MCTS search states. Root cause:
   numerical collapse on out-of-distribution states — the scalar z-normalizer
   produces extreme activations when MCTS visits states with feature values
   far outside the training range (e.g., Transient encounter with monSumHp
   ~970 vs training mean ~50). DeepSets predicts negative 40 million HP on
   these states.

4. **Confirmed distribution shift between training trajectories and MCTS
   leaves**: a simple RandomForest distinguishes them with 95% accuracy.

## Rationale

- The DeepSets architecture was chosen because XGBoost/CatBoost trees split
  one feature at a time and are architecturally weak at card synergies
  (AND-interactions over sparse card-count columns). The OOC DeepSets model
  (`train_deckset.py`) already demonstrated this approach for run-level
  prediction.
- **Inference**: The scalar z-normalizer is the failure point — it was
  calibrated on training data only and has no clamping. Extreme OOD feature
  values produce z-scores of 20+ standard deviations, which produce huge
  activations in the scalar encoder Linear layer that cascade through the MLP.
  This is a numerical stability problem, not an architecture problem.
- **Inference**: The draw pile order, card upgrade status, and other
  information losses identified in the audit are real but secondary — the
  model works well in-distribution (Pearson 0.97 vs XGBoost on trajectory
  states). The catastrophic collapse is purely an OOD robustness issue.

## Alternatives considered

- **Survival + conditional-HP heads** — deferred. The numerical collapse must
  be fixed first; adding output structure won't help if the model produces
  NaN-range values on MCTS states.
- **Collecting search-leaf training data** — deferred until OOD robustness is
  addressed. The model can already learn in-distribution.
- **Replacing DeepSets with a Transformer** — rejected as premature. The
  architecture is not the bottleneck.

## Evidence

- `train_combat_deepsets.py` — PyTorch trainer (90K params, RMSE 8.66 on
  honest data, parity-verified via `vnettest`)
- `src/sim/search/CombatValueNet.cpp` — `combat_deepsets_v1` format parser +
  native C++ inference (lines ~520–570, ~900–990)
- `include/sim/search/CombatValueNet.h` — isDeepSets flag + ds* fields
- `apps/one_combat.cpp` — extended `onVNetQuery` with parentObsHash + depth
  columns (lines ~2545–2560)
- `tools/analyze_mcts_leaves.py` — fixed-leaf-state comparison script
- `tools/diagnose_deepsets.py` — initial offline diagnostic suite (Exp 1-5)
- `build/vnet_mcts_leaves_xgb.csv` — 1M-row MCTS leaf trace (3.4GB; 50K
  sample at `build/vnet_mcts_leaves_50k.csv`)
- Gate results (32 seeds, S3 fair, 1k sims, α=0.3, no gate stack):
  XGBoost 31.2% vs DeepSets 0% (build/dsgate_*.log on sts-test)

## Status and follow-up

- **Implemented**: DeepSets trainer, C++ native inference, parity verification,
  MCTS leaf tracing, diagnostic scripts. All CTests pass.
- **Follow-up**: Add input clamping to scalar z-normalizer (clamp z-scores to
  [−5, +5]) to prevent numerical collapse on OOD states. This is the single
  most impactful next step — a one-line change in both Python and C++.
