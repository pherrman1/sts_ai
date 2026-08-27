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

If a fully restored nonterminal snapshot has no Silver-selected root action,
the offline relabeler records a fail-closed `teacher_valid=false` row with the
stable identity, requested/actual simulation count, telemetry, and explicit
failure reason. It does not substitute a rollout or heuristic value. The
analyzer reports these rows as coverage failures and excludes them from paired
value/action metrics rather than silently dropping or fabricating labels.

## Evidence

- `include/sim/search/SilverBridge.h`; `SilverWireJson.h`
- `third_party/silver_lightspeed/bridge/SilverStateBridge.cpp`
- `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp`
- `apps/silver_leaf_relabel.cpp`
- `apps/silver_bridge_test.cpp`; `tests/agent/test_silver_leaf_pipeline.py`

## Status and follow-up

Implementation validation and the tiny GCP smoke passed at `7870059`. The
decision-bearing GCP pilot used corpus-generation SHA `b4445179` and final
relabel/analyzer SHA `0189bb40`. It selected 500 complete sibling groups / 3,207
leaves, with 93 groups receiving independent replicate-B searches. No model or
gameplay run was performed.

The preregistered verdict is
`TEACHER_BUDGET_UNRESOLVED_OR_25K_REQUIRED`. Paired sibling-group bootstrap
probabilities of satisfying every global acceptance bar were 0% for 1k, 0% for
3.7k, and 6% for 10k. The 10k labels were close on Q error, regret, legal-action
ordering, and sibling ordering, but did not pass the registered top-action and
sibling-concordance margins. The independent 25k-A/25k-B comparison itself had
only 66.77% top-action agreement, establishing substantial action-level teacher
replicate noise rather than a deterministic 25k ground truth. The result does
not authorize a larger 25k corpus; model training remains a separate experiment.

Decision-bearing GCP provenance under
`/home/philippherrmann/sts_sweep/pilot-artifacts/b444517`:

- raw corpus, 419,562 rows:
  `8e722f4dd8e6a851dabee90eb9254e617d90bef34a7a74575f0a80d1ad9e8fa9`;
- selected exact-state corpus, 3,207 rows:
  `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7`;
- 500-group manifest:
  `db67ff9df6a1578a46e4e09038b5f2548772fc9c70fc54a00b1576f659883cd7`;
- 17,030-row relabel output:
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`;
- analyzer output:
  `5e34fa25adecb7d7efe64191d16163b257e1f9b07705110cd4618272aa32e7ab`;
- GCP master log:
  `05bdefa9ad0ba2a0e0e408229747d866bfca6ee231c1d29c49d7b5cb8b24e096`.
