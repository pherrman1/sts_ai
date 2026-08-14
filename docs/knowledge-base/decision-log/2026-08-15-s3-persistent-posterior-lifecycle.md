# Searcher3 persistent-posterior lifecycle

Date: 2026-08-15
Session/task: Decouple Searcher3 belief lifetime from MCTS tree lifetime.

## Decision

Reject persistent filtered-posterior transfer with the current `HiddenBattleState`.
Keep only diagnostic next-search-source telemetry; do not add a runtime feature
flag or change Searcher3 policy defaults.

## Rationale

The lifecycle premise is confirmed and material: in the fair S3 loop a failed
reuse or `STS_REUSE_MAX_SEARCHES` reconstruction constructs a new searcher and
calls `Belief::initial`. On the 8-seed diagnostic, 99.42% of non-trivial filters
were followed by `fresh_initial` rather than a search consuming the posterior.

However, the 8-seed forced-fresh-tree treatment had 79.11% collapse, dominated
by 2,066 `PROPAGATION_FAILURE` events. `filterRealTransition` carries the
propagated draw-pile order, but `HiddenBattleState` has no RNG counters and
`applyParticleImpl` resets all counters to zero. **Inference:** a seed-only
particle cannot represent a posterior across multiple real transitions safely.

## Alternatives considered

- Preserve an unsafe tree to preserve belief — rejected; violates the August 14
  draw-pile-sensitive CARD_SELECT reuse boundary.
- Reconstruct RNG counters or resample/rejuvenate particles — rejected; outside
  this experiment and unsupported by current state representation/evidence.
- Treat `belief_carried` as consumption — rejected; reuse-limit reconstruction
  can discard a carried boundary before the next actual search.

## Evidence

- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFairSearcher3` — fresh
  reconstruction and diagnostic sidecar emission.
- `src/sim/search/BattleScumSearcher3.cpp::filterRealTransition` and
  `applyParticleImpl` — draw-order propagation versus reset RNG counters.
- `tools/analyze_s3_belief_filter.py` — actual next-search-source analysis.
- `build/linux-gcc-release/s3_belief_lifecycle_phase2_8.csv` and
  `s3_persist_{control,treatment}_8.csv` — ignored local evidence.

## Status and follow-up

- Implemented: diagnostic-only next-search-source telemetry and analysis.
- Rejected: persistent-posterior gameplay treatment; temporary code removed.
- **Open question:** whether a future exact hidden-state representation can
  carry RNG counters across real transitions without changing simulator
  invariants.