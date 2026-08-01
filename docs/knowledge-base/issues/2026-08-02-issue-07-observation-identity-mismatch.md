# Issue 07: `CombatObservation` equality and hash disagree

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md)

## Symptom

`CombatObservation::operator==` and `visibleHash` cover different field sets.
Equal observations can hash differently and stored distinctions can be omitted
from the intended identity, so the observation identity used by Searcher3 (node
matching, RNG seeding) is not a well-defined contract.

## Evidence

- `src/sim/search/CombatObservation.cpp::visibleHash` (line 67) and
  `operator==` (line 130): different field sets per the knowledge base; neither
  establishes complete identity.
- Used as the node identity and seed input in
  `src/sim/search/BattleScumSearcher3.cpp` (lines 50, 64, 71).

## Why it matters

Search correctness (which worlds share a node, when searches replay
identically) depends on a consistent identity. Mismatched equality/hash breaks
the leakage-test premise and can cause node deduplication to diverge from
equality semantics.

## Candidate fix direction

Define a single canonical identity field set used by both `operator==` and
`visibleHash`; add a unit test asserting `a == b` implies equal hashes and
documented non-equal field coverage.

## Relevant code

- `src/sim/search/CombatObservation.cpp::visibleHash`, `operator==`
- `src/sim/search/BattleScumSearcher3.cpp`

## Resolution (2026-08-02)

Fixed: `CombatObservation::operator==` and `visibleHash` now share one canonical field set (card piles as `CardKey` multisets). Test `./build/test obs_identity <seed>` passes.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
