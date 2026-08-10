# Issue 56: Liquid Memories zero-cost broken (stale cardSelectTask)

- **Status:** closed (2026-08-10 issue-fixes session: `chooseDiscardToHandCard` now uses its `forZeroCost` parameter; regression coverage in `./build/test issue_fixes`)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/BattleContext.cpp:3018-3025`

## Symptom

`chooseDiscardToHandCard` ignores its `forZeroCost` parameter and instead tests
the never-reset `cardSelectInfo.cardSelectTask == LIQUID_MEMORIES_POTION`.
After any prior card select in the same combat, the stale task field causes
wrong behavior: Liquid Memories with exactly 1 discard-pile card fails to set
cost 0, or wrongly zero-costs a Hologram pickup.

## Evidence

- `BattleContext.cpp:3018-3025`: `chooseDiscardToHandCard` tests `cardSelectTask`
  instead of `forZeroCost`.
- `BattleContext.cpp:2405-2407`: Liquid Memories path calls with `forZeroCost` flag.
- `Actions.cpp:664-680`: `BetterDiscardPileToHandAction` passes the flag but
  it's dead.
- `CardSelectInfo.h`: no reset anywhere after a select resolves.
- Liquid Memories is in the Ironclad potion pool (`Potions.h:238`).

## Why it matters

Liquid Memories is an Ironclad-accessible potion. The zero-cost property is
critical to its value.

## Candidate fix directions

Replace the `cardSelectTask` test at line 3021 with `forZeroCost`.

## Relevant code

- `src/combat/BattleContext.cpp:3018-3025`
- `src/combat/Actions.cpp:664-680`
