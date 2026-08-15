# Searcher3 hidden-RNG prior sampler

Date: 2026-08-15
Session/task: Correct the biased `HiddenBattleState::randomize()` prior sampler.

## Decision

Construct each hidden RNG seed word from the low 32 bits of two consecutive
`std::mt19937_64` outputs. Preserve two engine calls per seed word and the
existing 12-word ordering.

## Rationale

The previous `static_cast<std::uint64_t>(rng()) << 32 | rng()` expression left
the second draw's upper 32 bits unmasked. Each upper output bit was therefore
the OR of two independent bits and had probability 3/4 of being one. Explicit
masking confirms the intended low32/low32 concatenation without changing the
generator state consumed before particle draw-pile construction.

## Alternatives considered

- Returning one `rng()` output — rejected because it would consume only 12
  engine outputs instead of the existing 24.
- Statistical bias testing — rejected because the deterministic word-for-word
  and engine-state regression proves the construction directly.
- Particle rejuvenation or gameplay evaluation — rejected; outside this prior
  sampler correctness fix.

## Evidence

- `src/sim/search/CombatObservation.cpp::HiddenBattleState::randomize` — masks
  both halves and retains two calls per sampled word.
- `apps/test_belief.cpp::testS3Rand64PriorSampler` — checks all 12 seed words
  against a fixed-seed reference and compares eight subsequent engine outputs.
- CTest `s3_rand64_prior_sampler` — deterministic focused regression.
- Cross-reference: `2026-08-15-s3-rng-state-propagation.md` recorded this as a
  separate unverified concern; that entry is not rewritten.

## Status and follow-up

- Implemented and mechanically verified; no gameplay-quality claim is made.
- Historical experiments used the historical biased prior and are not
  retrospectively reinterpreted. Any gameplay or search-quality effect requires
  a separate evaluation.
