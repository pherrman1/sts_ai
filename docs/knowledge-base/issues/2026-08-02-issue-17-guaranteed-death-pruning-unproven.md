# Issue 17: Aggressive guaranteed-death pruning is unproven

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"

## Symptom

The aggressive `isGuaranteedDead` path remains active in Searcher3 search
despite the guarded `canPruneAsDead` helper being unused. Historical performance
claims do not prove the predicate safe for every input state, including
card-selection states.

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp::isGuaranteedDead` (line 158) is
  called at lines 219, 248, 309; `canPruneAsDead` (line 171) is not.
- `combat-search.md` "Open questions": "Is aggressive guaranteed-death pruning
  sound for all card-selection states?"

## Why it matters

If the predicate ever misfires, search can prune lines that should survive,
silently changing policy quality in a state-dependent way that benchmarks may
not expose.

## Candidate fix direction

Either prove the predicate sound with exhaustive/state-space tests or route
pruning through the guarded helper; add a focused test over card-selection and
post-battle states.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp::isGuaranteedDead`, `canPruneAsDead`

## Resolution (2026-08-02)

Fixed conservatively: the aggressive `isGuaranteedDead` was removed and all three call sites route through `canPruneAsDead`, which fires only when the player cannot act. Test `./build/test prune <seed>` passes. Behavior change: pruning is now more conservative.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
