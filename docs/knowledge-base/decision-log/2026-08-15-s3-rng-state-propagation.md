# Searcher3 RNG-state propagation

Date: 2026-08-15
Session/task: Correct sequential real-posterior hidden RNG-state propagation.

## Decision

Represent the current counter as well as `seed0` and `seed1` for each of
Searcher3's six combat RNG streams in `HiddenBattleState`. Restore all three
fields when applying a particle and propagate all three fields from a predicted
compatible transition back into the particle.

## Rationale

The previous implementation restored seed pairs but reset every RNG counter to
zero, then copied only the predicted draw pile after a compatible real
transition. This made the particle's hidden RNG state stale at the next real
boundary. The correction is limited to hidden-state representation and
propagation; it does not resample, rejuvenate, duplicate particles, change
particle count, or alter observation equality.

## Alternatives considered

- Resampling, rejuvenation, or history replay — rejected; outside this
  mechanical correctness task.
- Fixing `HiddenBattleState::randomize()` — rejected; its `rand64()` construction
  is a separate prior-sampler concern and changing it would alter another
  conceptual variable.

## Evidence

- `include/sim/search/CombatObservation.h::HiddenBattleState` — six counters
  added alongside the six seed pairs.
- `src/sim/search/BattleScumSearcher3.cpp::applyParticleImpl` — all counters
  restored; `BattleScumSearcher3::filterRealTransition` — all six post-transition
  RNG states propagated.
- `src/sim/search/CombatObservation.cpp::hiddenRngHash` — counters included in
  distinct RNG signatures.
- `apps/test_belief.cpp::testRngStatePropagation` — actual Cultist `END_TURN`
  transition consumes `aiRng`, then a second transition remains compatible
  without a fresh-belief reset. The test reports `draw_pile=match rng_fields=18/18`.
- Focused output: transition 1 had `compatible=8`, counters `[0,0,1,0,0,0]`;
  transition 2 had `compatible=3`, counters `[1,0,2,0,0,0]`.

## Status and follow-up

- Implemented and mechanically verified with the focused regression plus the
  existing `real_belief_filter` and `persistent_belief_transfer` tests.
- The previous persistent-posterior quality experiment remains evidence for
  its frozen implementation; its propagation was incomplete under this
  correction and its gameplay results are not reinterpreted here.
- **Open question:** whether additional simulator state outside the six RNG
  streams and draw-pile order is required for a complete hidden-state model.
- **Unverified separate concern:** `randomize()` combines two 64-bit
  `std::mt19937_64` outputs with a 32-bit shift/OR pattern that may bias the
  sampled prior word. It was not changed here.