# ADR-0017: Treat queue items as historical at quiescent Silver decisions

- Status: proposed for independent review
- Date: 2026-09-22

## Context

At a decision with no pending work, `curCardQueueItem` records the last used
card and need not define Silver retained-search identity. PR #285 tried a
`PLAYER_NORMAL`-only comparison, then rewrote the retained root's queue item
to the observation. It left already-expanded descendants carrying the old
item. Its consumed HOLDOUT failed closed when a retained Gambler's Brew
`CARD_SELECT` child differed from the observed child only in that field.

The previous card is not used by Gambler's Brew selection. The problem is
graph consistency: updating just the root makes a previously expanded child
appear mismatched. In contrast, a card-created screen can retain pending
`OnAfterCardUsed` work that reads the active card item.

## Decision

Silver-specific retained identity may ignore `curCardQueueItem` only when
both states are unresolved `PLAYER_NORMAL` or `CARD_SELECT` decisions, neither
is terminal or ending a turn, and both action and card queues are empty. All
other fields retain ordinary search equality. Exact equality has priority.
Global `BattleContext::equalForSearch()` and hashing remain unchanged.

Keep the retained representative and descendants stable during dedup and
reroot. A selected deterministic child, sampled chance outcome, or explored
live edge may match through the same predicate. Do not rewrite the retained
queue item to the observed value. Hand-order and equivalent-copy UID repair
remain subject to their existing safeguards. A privately selected
deterministic child still must reroot, be cap-blocked, or fail loudly.

## Evidence and limits

Focused tests cover the previously failing expanded Gambler's Brew subtree,
reopened selection, confirmation, continuing search, and stable queue items.
They also cover Headbutt's queued `OnAfterCardUsed`, Attack Potion, ordinary
action execution, hand permutation, equivalent-copy UID repair, chance
outcomes, and excluded states. Frozen DEV results and same-root measurements
are recorded in Silver ledger §335. The prior hard64 HOLDOUT was consumed by
PR #285 and is not rerun for this candidate.

The new identity is bounded to the currently supported simulator. The
read-site audit found no direct `curCardQueueItem` read in supported quiescent
selection enumeration or execution; a future task or action path that reads
it at such a boundary requires revisiting this predicate.
