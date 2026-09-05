# Issue 52: `std::bad_function_call` crash via empty `PoisonLoseHpAction`

- **Status:** fixed (2026-08-10)
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/Actions.cpp`, `src/combat/BattleContext.cpp`

## Symptom

`Actions::PoisonLoseHpAction` returns `sts::Action()` (empty `actFunc`).
`executeActions` invokes it unconditionally at `BattleContext.cpp:776-779`,
causing `std::bad_function_call` → `std::terminate()`. The action is queued
every monster turn while poison is set (`Monster.cpp:36-38`).

Currently unreachable in Ironclad only because Poison Potion is excluded from
the Ironclad pool (`Potions.h:238`) and all poison sources (Envenom, Noxious
Fumes, Twisted Funnel) are Silent. Same empty-stub pattern exists in
`ChangeStance`, `EssenceOfDarkness`, `IncreaseOrbSlots`.

## Evidence

- `Actions.cpp:930-932`: `return sts::Action();`
- `BattleContext.cpp:776-779`: unconditional `actFunc()` invocation
- `Monster.cpp:36-38`: poison action queued every monster turn
- `Potions.h:237-242`: Ironclad potion pool excludes Poison Potion

## Why it matters

A landmine for any class/pool expansion. If Ironclad ever gains a poison source
or if another class uses the same action dispatch, it's an instant crash.

## Candidate fix directions

Implement the action stub (at minimum a no-op body) or add a runtime guard
before the unconditional `actFunc()` call.

## Relevant code

- `src/combat/Actions.cpp:930-932` (`PoisonLoseHpAction`)
- `src/combat/Actions.cpp:151-153` (`ChangeStance`), `909-911` (`EssenceOfDarkness`), `913-915` (`IncreaseOrbSlots`)
- `src/combat/BattleContext.cpp:776-779`
- `src/combat/Monster.cpp:36-38`

## Resolution

All four empty stubs now return actions with a valid `actFunc`. The action
factories (`src/combat/Actions.cpp`) now construct real lambda bodies;
`ChangeStance`, `EssenceOfDarkness`, and `IncreaseOrbSlots` are explicit
no-ops (stances/orbs not implemented), and `PoisonLoseHpAction` gained a
`monsterIdx` parameter (declaration in `include/combat/Actions.h`, call site
`Monster.cpp::applyStartOfTurnPowers` passes `this->idx`) that applies the
poison amount as unblockable damage (`Monster::damageUnblockedHelper`, the
port equivalent of the game's `DamageType.THORNS`), decrements poison by 1,
and calls `bc.checkCombat()`. Regression tests: `poison_lose_hp` and
`time_eater_exhaust` (see `apps/test.cpp`, CTest entries in `CMakeLists.txt`).
See historical session record.
