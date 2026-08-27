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
The analyzer retains the preregistered point-estimate decision rule and also
reports a deterministic paired sibling-group bootstrap. Candidate and 25k-A
ceiling metrics share each resampled group draw against the independent 25k-B
reference; 95% percentile intervals cover the three agreement margins and
regret excess/ratio, with a global-bar pass probability reported separately
from the required manual subgroup-pathology review.

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

Implementation validation and the tiny GCP smoke passed at `7870059`. Independent
review accepted the corpus/relabel design and requested the group-bootstrap
uncertainty report before freezing the SHA used for the decision-bearing
~500-group GCP pilot. Model training remains a separate later experiment.
