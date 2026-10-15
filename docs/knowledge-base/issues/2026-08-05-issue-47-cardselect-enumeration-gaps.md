# 2026-08-05-issue-47 — CARD_SELECT legal-action enumeration gaps (closed)

**Tier:** Critical
**Status:** closed by the cardselect parity fix commit (2026-08-05)
**Source pages:** [combat-search](../architecture/combat-search.md)

## Symptom

`BattleScumSearcher3::enumerateActionsForNode` (CARD_SELECT branch) and
`BattleScumSearcher2::enumerateCardSelectActions` / the canonical
`search::Action::enumerateCardSelectActions` cannot produce every action the
simulator accepts:

- S3's default branch enumerated `i < cardSelectInfo.pickCount` hand indices —
  the wrong pool for WARCRY, FORETHOUGHT, HEADBUTT, LIQUID_MEMORIES_POTION,
  SECRET_TECHNIQUE/WEAPON, DUAL_WIELD, HOLOGRAM, MEDITATE, NIGHTMARE, RECYCLE,
  SETUP, SEEK; no EXHUME-card filter; garbage edges for `INVALID`; stray
  `break;` statements after the ARMAMENTS case.
- S2 and the canonical enumerator missed HOLOGRAM, MEDITATE (discard pool),
  NIGHTMARE, RECYCLE, SETUP (hand pool), SEEK (draw pool) entirely, and
  emitted a single bogus empty MULTI_CARD_SELECT for EXHAUST_MANY/GAMBLE.

## Evidence

`apps/test.cpp::testCardSelectParity` (`./build/test cardselect_parity`):
48 of 63 fabricated states mismatched the `isValidAction` ground truth before
the fix (S3-only failures on 24 states, canonical+S2+S3 failures on the rest);
after the fix all 63 pass, deterministic across runs.

## Why it matters

A search that cannot enumerate a legal action is blind to it — Dual Wield,
Headbutt, Warcry, Secret Technique/Weapon, Gambler's Brew, Elixir, Purity and
similar selections were partially or fully invisible, so the search could not
choose them.

## Fix

Canonical enumerator extended to the full validity contract; S2 and S3
delegate to it. Multi-select action space is prunable for search scale via
`STS_MULTISELECT_MODE` (see issue 48 — full subsets regress win rate at fixed
simulation budgets).
