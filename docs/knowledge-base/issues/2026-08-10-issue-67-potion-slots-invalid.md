# Issue 67: Default potion slots INVALID instead of EMPTY

- **Status:** closed (2026-08-10)
- **Fix:** `std::array<Potion, 5> potions` now defaults every slot to
  `Potion::EMPTY_POTION_SLOT` via a member initializer in
  `include/game/GameContext.h` and `include/combat/BattleContext.h`.
  `BattleContext::init` already overwrites `potions = gc.potions`, so a
  properly initialized context is unchanged; the fix covers default-constructed
  contexts (and `initFromSave` slots beyond the save's potion vector).
  Regression test: `./build/test issue_fixes` (ctest `issue_fixes`).
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `include/game/GameContext.h:232,243`, `include/constants/Potions.h:13-14`

## Symptom

Default-constructed `GameContext`/`BattleContext` potion slots are
`Potion::INVALID` (0), not `EMPTY_POTION_SLOT` (1). `obtainPotion` silently
drops potions if gc/bc was never properly initialized. Convention-enforced only.

## Evidence

- `GameContext.h:232`: `std::array<Potion, 5>` with `= default` at 243.
- `Potions.h:13-14`: INVALID=0, EMPTY_POTION_SLOT=1.
- `BattleContext.cpp:2251-2263`: `obtainPotion` assumes EMPTY.

## Candidate fix directions

Initialize potion slots to EMPTY_POTION_SLOT in default constructors.

## Relevant code

- `include/game/GameContext.h:232,243`
- `src/combat/BattleContext.cpp:2251-2268`
