# Issue 70: Searcher2 stale-`outcome` on fair-mode re-expansion

- **Status:** closed (2026-08-10: `step()` clears the stale `outcome` on fair-mode re-expansion; regression `scum_convroot_stale_outcome`)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/BattleScumSearcher2.cpp:360-382`

## Symptom

In fair mode, a node terminal in one determinization (outcome=1/2, empty edges)
can be re-reached in another world where the state is non-terminal. It gets
edges while `outcome` stays stale, violating the documented invariant
"outcome != 0 implies edges.empty()". `collectFrontierStats` misclassifies
such nodes as terminal leaves, skipping their subtrees.

## Evidence

- `BattleScumSearcher2.cpp:360-366`: terminal sets outcome, no edge reset.
- `BattleScumSearcher2.cpp:371-382`: re-expansion enumerates edges, leaves
  outcome unchanged.
- `BattleScumSearcher2.h:28-36`: documented invariant.
- `combat-search.md:104`: invariant documentation.

## Candidate fix directions

Reset `outcome = Outcome::UNDECIDED` when re-enumerating edges on a
previously-terminal node.

## Relevant code

- `src/sim/search/BattleScumSearcher2.cpp:371-382`
