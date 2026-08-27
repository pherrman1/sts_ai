# Silver leaf teacher corpus

Date: 2026-08-27

## Decision

Use `BattleStateWire` as the exact source-of-truth snapshot for both Silver
rollout-start leaves and their nearest non-random parent decisions. Persist
complete semantic parent action groups, raw auxiliary rollouts, and raw
per-action teacher Q/visit/victory statistics. Do not choose a scalar-model or
policy-prior target transformation in this task.

Fresh teacher searches reuse a stable group/replicate seed across budgets and
sibling leaves; a separate replicate B supplies the independent 25k reference.

## Corrected utility fact

Executed `BattleSearcher::evaluateEndState()` uses `rootState` only for the
victory-branch effective-gold and max-HP deltas. The leaf-root to original-root
difference is consequently constant per victorious continuation but zero for
losses, not one unconditional constant across a mixed-outcome Q. Corrected Qs
therefore require the action's empirical victory fraction. The implementation
records child victory counts and retains all raw quantities.

## Evidence

- `include/sim/search/SilverBridge.h`; `SilverWireJson.h`
- `third_party/silver_lightspeed/bridge/SilverStateBridge.cpp`
- `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp`
- `apps/silver_leaf_relabel.cpp`
- `apps/silver_bridge_test.cpp`; `tests/agent/test_silver_leaf_pipeline.py`

## Status and follow-up

Implementation validation and a tiny GCP smoke are required before the draft
PR review checkpoint. The decision-bearing ~500-group pilot remains prohibited
until independent review accepts the frozen SHA.
