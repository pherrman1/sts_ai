# Issue 03: Searcher3 composite seeding uses unassigned values

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md)

## Symptom

`BattleScumSearcher3` seeds its `std::mt19937_64` from `agentSeed`,
`visibleHash`, and `decisionIndex` inside the constructor, but callers assign
`agentSeed` only after construction and no caller ever assigns
`decisionIndex`. The advertised composite seeding is therefore not implemented
as stated; effective seeding uses the visible hash plus default-zero members.

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp::BattleScumSearcher3` (lines 56–73):
  the seed is computed before any caller can set members.
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` (line 82) and
  `playoutBattle` (line 134): `s3.agentSeed = bc.seed` happens after
  construction.
- `include/sim/search/BattleScumSearcher3.h` (lines 60–61): `agentSeed = 0`,
  `decisionIndex = 0` defaults; `decisionIndex` has no other assignment in the
  repository.

## Why it matters

Particle sampling and search RNG are keyed on unintended values, so per-decision
search diversity and the documented leakage test ("same agent seed + same
observation = same search") do not behave as designed. Datasets produced by
Searcher3 (e.g., PVNet training data) inherit this behavior.

## Candidate fix direction

Make `agentSeed`/`decisionIndex` explicit constructor parameters or assign them
before seeding; add a regression test asserting distinct decision indices
produce distinct seeds.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp::BattleScumSearcher3`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`, `playoutBattle`
- `include/sim/search/BattleScumSearcher3.h`

## Resolution (2026-08-02)

Fixed: `BattleScumSearcher3` takes explicit `agentSeed`/`decisionIndex` constructor parameters; the tree-reuse path re-keys via `reseed()`. Test `./build/test seed_contract <seed>` passes.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
