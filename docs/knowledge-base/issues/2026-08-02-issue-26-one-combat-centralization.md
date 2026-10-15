# Issue 26: `one_combat.cpp` centralizes policy and experiments

- **Status:** open
- **Tier:** Low
- **Last verified:** 2026-08-02
- **Source:** [`architecture/overview.md`](../architecture/overview.md), "Known limitations"; [`architecture/out-of-combat.md`](../architecture/out-of-combat.md)

## Symptom

`runFullRunOOC` is an ordered branch chain, not one composable policy object;
`one_combat.cpp` co-locates the simulator integration driver with policy
branches and experimental evaluators. Adding an earlier branch can silently
bypass later behavior. **Inference:** it functions as a research workbench
rather than a stable library boundary; no explicit decision record documents
that intent.

## Evidence

- `apps/one_combat.cpp::runFullRunOOC` (line 2094): ordered branch chain.
- `overview.md`: repository contains no explicit decision record for the
  workbench intent.

## Why it matters

Each new policy layer increases the risk of precedence bugs (e.g., a loaded
opt-in silently owning screens previously handled by the base policy) and makes
reuse by other executables impractical.

## Candidate fix direction

Extract policy layers into stable owners with explicit precedence
documentation; the open questions in `overview.md` and `out-of-combat.md` scope
the long-term boundary.

## Relevant code

- `apps/one_combat.cpp::runFullRunOOC`, `main`
- `docs/knowledge-base/architecture/overview.md`

## Resolution (2026-08-02)

Deferred: extracting stable policy owners from `one_combat.cpp` is a larger refactor, not in the 2026-08-02 scope.

## Closed by

*Fixed in the 2026-08-02 working tree. No change; remains open.*
