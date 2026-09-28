# ADR-0023: Native equivalent-copy reroot

Date: 2026-09-25
Status: accepted

Amends: [ADR-0022](0022-remove-vendored-silver.md), whose consequences listed
the loss of equivalent-copy reroot. Restores the intent of
[ADR-0015](0015-live-silver-equivalent-copy-reroot.md) on native Silver.

## Context

Silver deduplicates search-equivalent card copies at a decision: two identical
Strikes give one card-play edge, expanded with one physical copy. When the
player plays the other copy, the next state differs only in which unique id
sits in the discard pile, so the exact node lookup misses and the search starts
over. ADR-0015 handled this in the vendored model; its removal (ADR-0022) lost
it (issue #327).

## Decision

- `SilverSearcher::findNodeUpToEquivalentCopy(state)`: when the exact lookup
  misses, retry with the unique ids of one pair of search-equivalent cards
  exchanged throughout the state (hand, piles, limbo, stasis, queue card).
  Cards that use their special data are never exchanged.
- The native backend and the advisor session reroot through such a match.
  Actions of the retained root reach the live state through
  `SilverSearcher::translateAction`, which already falls back to an equivalent
  copy; the advisor translates before lowering, so actions always name a card
  in the live hand, and reports `equivalentCopy: true`.
- `equalForSearch`, hashing and the dedup table stay exact.

## Alternatives considered

- Make search identity ignore unique ids of equivalent cards. Rejected: it
  changes transposition identity everywhere and needs a separate gameplay
  qualification.
- Port the vendored UID remap of the retained subtree. Rejected: the lookup
  plus action translation gives the same reuse without mutating the graph.

## Affected files

- `include/sim/search/SilverSearcher.h`, `src/sim/search/SilverSearcher.cpp`
- `src/sim/search/NativeSilverBackend.cpp`, `apps/one_combat/native_silver_advisor.{h,cpp}`,
  `apps/one_combat/advisor_stdio.cpp`

## Evidence

- `test silver_searcher` (equivalent-copy lookup and translation) and
  `live_silver_importer_test` (advisor reroot with inherited visits, lowered
  cards in the live hand).
- Paired 128-seed gameplay check: ledger §355.
