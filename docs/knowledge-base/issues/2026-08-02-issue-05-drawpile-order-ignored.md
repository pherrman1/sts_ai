# Issue 05: `HiddenBattleState::drawPileOrder` is never applied

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md)

## Symptom

Searcher3 populates `HiddenBattleState::drawPileOrder` in each particle, but
`applyParticle` ignores it and independently shuffles the copied draw pile with
the searcher RNG. The stored draw order is dead data.

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp` lines 83–84: particles store
  `drawPileOrder` after a shuffle.
- `src/sim/search/BattleScumSearcher3.cpp::applyParticle` (line 23): applies
  seeds but reshuffles the copied draw pile itself; `drawPileOrder` is not
  consumed.
- `src/sim/search/CombatObservation.cpp` lines 225–226: same store pattern.

## Why it matters

Particle draw order and RNG streams are the hidden-state model. Ignoring the
sampled order decouples the "sampled world" from what the particle claims, so
draw-order diversity and conditioning work against each other.

## Candidate fix direction

Have `applyParticle` install the sampled `drawPileOrder` into the copied battle
(or define explicitly that draw order is resampled by the searcher RNG); add a
test that a particle's draw order survives application.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp::applyParticle`, `prepareCRNParticles`
- `src/sim/search/CombatObservation.cpp`
- `include/sim/search/CombatObservation.h::HiddenBattleState`

## Resolution (2026-08-02)

Fixed: `applyParticle` installs the particle's `drawPileOrder` into the copied battle when size and card multiset match, with a stale-particle shuffle fallback after tree reuse. Test `./build/test drawpile <seed>` passes.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
