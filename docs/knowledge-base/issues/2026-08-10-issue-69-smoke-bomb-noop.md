# Issue 69: Smoke Bomb drink was a zero-effect action

- **Status:** closed correctly on 2026-08-26 by `e53f994`; the 2026-08-10
  guard-only closure was based on an incorrect external-rule premise and is
  superseded by the correction recorded in
  `../.md`
- **Tier:** Low
- **Date:** 2026-08-10; corrected 2026-08-26
- **Source:** investigator audit plus the pinned Silver reference

## Original symptom

`potionRequiresTarget(SMOKE_BOMB)=false` allowed search enumeration while the
old `drinkPotion` case had no effect. The first repair forbade combat use and
removed it from search enumeration.

The premise used by that repair—"the real game forbids using Smoke Bomb in
combat"—was false. Smoke Bomb escapes eligible non-boss combat, gives no
combat rewards, cannot escape a boss, and cannot be used while `SURROUNDED`.

## Current implementation

- `BattleContext::smokeBombEscapeBlocked()` is true for boss encounters or
  `SURROUNDED`.
- Eligible use consumes the potion, records `smokeBombUsed`, and terminates
  combat through the normal successful-combat exit mechanism.
- `BattleContext::exitBattle` transfers the escape marker to `GameContext`.
  `GameContext::afterBattle` performs exit processing, grants no combat reward,
  skips event-specific victory continuation, and returns to the map.
- Searcher2, Searcher3, SimpleAgent, and shared action validity expose eligible
  use and reject blocked use. Potion discard remains independently legal.
- `apps/test.cpp::testIssueFixes` covers eligible escape, boss and
  `SURROUNDED` blocking, discard, search enumeration, post-combat relic
  processing, and unchanged ordinary potion behavior.

## Relevant code

- `include/combat/BattleContext.h::smokeBombEscapeBlocked`
- `src/combat/BattleContext.cpp::drinkPotion`, `exitBattle`
- `src/game/GameContext.cpp::afterBattle`
- `src/sim/search/Action.cpp::isValidPotionAction`
- `apps/test.cpp::testIssueFixes`
