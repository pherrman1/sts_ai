# Searcher3 persistent-posterior lifecycle

Date: 2026-08-15
Session/task: Decouple Searcher3 belief lifetime from MCTS tree lifetime.

## Decision

Correct the initial conclusion: do not reject persistent filtered-posterior
transfer based on the 79.1% collapse smoke. Keep only diagnostic telemetry; do
not add a runtime feature flag or change Searcher3 policy defaults.

## Rationale

The lifecycle premise is confirmed and material: in the fair S3 loop a failed
reuse or `STS_REUSE_MAX_SEARCHES` reconstruction constructs a new searcher and
calls `Belief::initial`. On the 8-seed diagnostic, 99.42% of non-trivial filters
were followed by `fresh_initial` rather than a search consuming the posterior.

The original 8-seed forced-fresh-tree treatment had 79.11% collapse, dominated
by 2,066 `PROPAGATION_FAILURE` events. This was confounded: on collapse with
fresh recovery off, `filterRealTransition` restores `oldParticles` from before
the real transition. The paired correction held temporary transfer and fresh
trees constant, changing only `STS_S3_REAL_BELIEF_COLLAPSE_FRESH`: collapse fell
from 79.82% to 19.66%, propagation failure from 83.48% to 31.23% of attempts,
and all 2,363 `PROPAGATION_FAILURE` collapses disappeared. The added split shows
these failures were overwhelmingly draw-pile mismatches, not action illegality.

`HiddenBattleState` still lacks RNG counters and `applyParticleImpl` resets them
to zero. That remains an **Open question**, not the established primary cause of
the previous catastrophic cascade.

## Alternatives considered

- Preserve an unsafe tree to preserve belief — rejected; violates the August 14
  draw-pile-sensitive CARD_SELECT reuse boundary.
- Reconstruct RNG counters or resample/rejuvenate particles — deferred; outside
  this experiment and not needed to explain the stale-fallback cascade.
- Treat `belief_carried` as consumption — rejected; reuse-limit reconstruction
  can discard a carried boundary before the next actual search.

## Evidence

- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFairSearcher3` — fresh
  reconstruction and diagnostic sidecar emission.
- `src/sim/search/BattleScumSearcher3.cpp::filterRealTransition` and
  `applyParticleImpl` — stale fallback, draw-pile mismatch split, and reset RNG
  counters.
- `tools/analyze_s3_belief_filter.py` — actual next-search-source analysis.
- `build/linux-gcc-release/s3_belief_lifecycle_phase2_8.csv` and
  `s3_persist_{control,treatment}_8.csv` — ignored local evidence.

## Status and follow-up

- Implemented: diagnostic-only next-search-source telemetry and analysis.
- Corrected: sequential real-boundary filtering now skips particles with
  non-positive weight, so rejected hypotheses cannot resurrect without an
  explicit resampling/rejuvenation mechanism; `real_belief_filter` covers this.
- Rerun after that correction: corrected T1 on seeds 94000–94007 produced
  15.14% collapse, 44/183,488 propagation failures (0.02398%), zero draw-pile
  mismatches, and 44 action-illegal particles. Its next-search sources were
  `fresh_initial=2698` and `no_next_search=169`; no larger quality gate was run.
- Removed: temporary posterior-transfer gameplay treatment after the causal
  diagnostic; a separately designed quality experiment is required.
- **Open question:** whether a future exact hidden-state representation can
  carry RNG counters across real transitions without changing simulator
  invariants.