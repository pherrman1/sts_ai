# Issue 04: Searcher3 belief conditioning is a no-op

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md)

## Symptom

`Belief::update` does not condition particles on observed draws (it discards the
observation with `(void)obs`), and `Belief::sample` selects uniformly, ignoring
particle weights. Searcher3's particle distribution therefore never reflects
what the player has actually drawn.

## Evidence

- `src/sim/search/CombatObservation.cpp::Belief::update` (lines 268–275): the
  reweighting loop is a comment plus `(void)obs`.
- `src/sim/search/CombatObservation.cpp::Belief::sample` (lines 277–280): a
  `std::uniform_int_distribution` over particle indices; weights are unused.

## Why it matters

The project-fair path's hidden-information model is the core claim of Searcher3.
Without conditioning, the search averages over worlds that are inconsistent with
observed draws, so results cannot support honest-play claims.

## Candidate fix direction

Implement consistency-based reweighting (zero or scale weights by draw-order
compatibility) and weighted sampling; add a regression test that a particle
contradicting observed draws has zero sampled probability.

## Relevant code

- `src/sim/search/CombatObservation.cpp::Belief::update`, `Belief::sample`
- `include/sim/search/CombatObservation.h::Belief`

## Resolution (2026-08-02)

Fixed: `Belief::update` zero-weights particles whose draw order contradicts the observed pile; `Belief::sample` does weighted sampling with a uniform fallback. Test `./build/test belief` passes.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
