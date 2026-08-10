# Issue 69: Smoke Bomb drink is a zero-effect action

- **Status:** closed (2026-08-10 issue-fixes session: `drinkPotion` refuses to consume Smoke Bomb with a warning, and SMOKE_BOMB is excluded from search potion-action enumeration like FAIRY_POTION so the search never offers the no-op; regression coverage in `./build/test issue_fixes`)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/BattleContext.cpp:2430-2432`

## Symptom

`potionRequiresTarget(SMOKE_BOMB)=false` so both searchers enumerate it.
`drinkPotion` case is `// todo break;` — potion consumed, nothing happens.
The real game forbids using Smoke Bomb in combat.

## Evidence

- `BattleContext.cpp:2430-2432`: `// todo break;`
- `Potions.h:271`: `potionRequiresTarget` returns false for Smoke Bomb.
- Both searchers enumerate the action.

## Why it matters

The searcher can waste a potion slot and simulation budget on a no-op.

## Candidate fix directions

Either implement Smoke Bomb (end combat immediately) or forbid its use in
combat (matching real game).

## Relevant code

- `src/combat/BattleContext.cpp:2430-2432`
- `include/constants/Potions.h:271`
