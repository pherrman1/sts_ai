# Issue 66: Omamori counter underflow in `exitBattle`

- **Status:** closed (2026-08-10 issue-fixes session: `exitBattle` now guards the Omamori decrement with `>0`; regression coverage in `./build/test issue_fixes`)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/BattleContext.cpp:479-480`

## Symptom

`exitBattle` does `--g.relics.getRelicValueRef(RelicId::OMAMORI)` without a
`>0` guard. A 0-charge Omamori goes to −1 and the Parasite curse is skipped.
`Deck.cpp:157-167` has the correct guard. IMPLANT check at
`MonsterSpecific.cpp:1519-1524` also tests `hasRelic` (bit) not charges.

## Evidence

- `BattleContext.cpp:479-480`: decrement without guard.
- `Deck.cpp:157-167`: correct guard pattern exists elsewhere.

## Candidate fix directions

Add `>0` guard before decrement: `if (count > 0) --count;`

## Relevant code

- `src/combat/BattleContext.cpp:479-480`
