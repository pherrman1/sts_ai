# Issue 28: Policy input includes hand-authored Expert features

- **Status:** closed
- **Tier:** Low
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Invariants and assumptions"; [`architecture/training-and-inference.md`](../architecture/training-and-inference.md)

## Symptom

Two of the 14 policy action features come from `Expert` play/obtain weights, so
the learned policy input is not free of hand-authored guidance. This is
documented, not a defect; it becomes an issue only when claims of a
pure-learned policy are made.

## Evidence

- `src/sim/search/CombatValueNet.cpp::combatFillActionFeatures` (Expert
  play/obtain features).
- `AGENTS.md`: "Existing combat policy features already include `Expert`
  play/obtain weights, so do not claim the implementation is free of
  hand-authored guidance."

## Why it matters

Policy-quality claims that ignore the Expert prior overstate what was learned;
this is a claim-hygiene issue for experiment reporting.

## Candidate fix direction

None required; record the Expert dependency in any policy claim. Removing the
features would be an explicit design change.

## Relevant code

- `src/sim/search/CombatValueNet.cpp::combatFillActionFeatures`,
  `combatPolicyFeatureNames`

## Resolution (2026-08-02)

Already documented in `combat-search.md` ("Two action features come from Expert play/obtain weights"), `training-and-inference.md`, and `AGENTS.md`; no code change needed.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
