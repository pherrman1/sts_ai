# ADR-0016: Canonicalize historical queue items in settled Silver decisions

- Status: accepted
- Date: 2026-09-22

## Context

At a settled unresolved `PLAYER_NORMAL` decision, `curCardQueueItem` records
the previously executed card. It can differ across states whose remaining
search-relevant fields agree. Silver's hash already omits this field, but its
dedup equality and reroot comparison previously required an exact match.
The earlier default-off candidate in PR #275 was exploratory; its whole-combat
efficiency comparison was trajectory-confounded. PR #277 established the
selected deterministic child reroot invariant used here.

## Decision

Silver retained-search identity ignores `curCardQueueItem` only when both
states are unresolved, nonterminal `PLAYER_NORMAL` decisions with empty action
and card queues and no pending or completed end turn. Exact equality is tried
first. All other fields retain the ordinary `equalForSearch()` contract.
Global `BattleContext::equalForSearch()` and the state hash remain unchanged.

Ordinary dedup keeps its first retained representative. When a matching child
becomes the active root, rerooting aligns the retained queue item to the
observed value before hand alignment. The same predicate applies to selected
deterministic children, sampled chance outcomes, equivalent-copy repair, and
live explored-edge matching. A deterministic selected child still must reroot,
be cap-blocked, or fail loudly.

`CARD_SELECT`, `EXECUTING_ACTIONS`, queued, terminal, and end-turn states remain
exact. Chance widening, RNG, reuse caps, rollout/value behavior, and search
constants are unchanged.

## Evidence

Focused search and bridge boundary tests cover dedup, excluded states, hand
permutation, equivalent-copy repair, selected deterministic reroot, sampled
chance outcomes, and Attack Potion selection. Frozen DEV and HOLDOUT results
and same-root measurements are recorded in the next Silver ledger entry.
