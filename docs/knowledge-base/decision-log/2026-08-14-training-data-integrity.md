# 2026-08-14 — Training-data terminal integrity containment

## Decision

Training producers must not serialize ordinary labels from an unresolved combat,
run, or simulator-health-failed trajectory. Valid player losses remain valid
losses; terminal HP is not used as a loss-validity heuristic. Bounded
counterfactuals may retain an unresolved model bootstrap only when no simulator
health hard failure occurred. A health-failed branch is quarantined from Q-label
aggregation.

`one_combat` now applies this rule to combatgen, fightgen, and strategicgen2,
with a shared `TrainingIntegrity` predicate. Invalid worker trajectories emit no
ordinary rows. Large generators print reconciled requested/completed/
invalid-health/rows-written counters and write `<dataset>.provenance.json` with
the dataset path, UTC timestamp, Git SHA/dirty state, generator parameters,
selected simulator/model environment, and integrity counters.

## Evidence and scope

The historical VCombat finding remains: **208 malformed fights, 2,137 affected
rows, 0.238% of fights, and 0.135% of rows**. Historical fair-S3 VCombat did
**not** use subtree reuse. This safeguard is containment, not evidence that
simulator correctness is complete.

The existing Tier-B producer attaches source-run labels to every buffered
decision row and obtains Q labels from bounded counterfactual branches. An
unresolved source run could therefore fan out one malformed terminal label over
many rows, while a failed branch could contaminate its Q target independently.
The new predicate keeps those cases separate and preserves intentional clean
bootstrap semantics.

## Status

Implemented and covered by the `training_integrity` unit test plus existing
simulator-health regressions. A two-seed combatgen smoke produced normal rows,
zero quarantines, zero health failures, and a provenance sidecar. No historical
dataset or model artifact was modified.

## Supported producer inventory

The terminal-integrity contract covers all current label-producing entry points:
`datagen`, `datagen2`/`datagen3`, `causalgen`, `combatgen`, `distgen`, `fairgen`,
`fightgen`, `policygen`, `strategicgen`, and `strategicgen2`. Their source runs
are quarantined on unresolved/health-failed combat; counterfactual branches are
quarantined independently. `leafdiag`, `leafref`, `frontiergen`, `searchdiag`,
and replay/benchmark modes are diagnostic or evaluation producers, not training
label producers, and are intentionally outside this contract.