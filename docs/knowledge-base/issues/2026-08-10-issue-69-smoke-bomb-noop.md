# Issue 69: Smoke Bomb drink was a zero-effect action

- **Status:** closed correctly on 2026-08-26 by `e53f994`; the 2026-08-10
  guard-only closure was based on an incorrect external-rule premise and is
  superseded by the correction recorded in
  `../decision-log/2026-08-26-smoke-bomb-rule-correction.md`
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
- Colosseum's two fight continuations replace `afterBattle`, so they handle
  the marker themselves: a slaver-fight escape clears it and reopens the event
  (the fight has no rewards either way); a Nob-fight escape calls
  `afterBattle`, forfeiting the Victory rewards and returning to the map.
  Verified against the game bytecode (`desktop-1.0.jar` cfad868a, issue #641,
  2026-10-18): `EventRoom.update` calls `Colosseum.reopen()` after the escape,
  and the smoked flag only changes the reward screen, which the reward-less
  slaver fight never opens.
- Java still makes the reward RNG rolls on an escape (`AbstractRoom.update`
  runs `addGoldToRewards`, `dropReward` and `addPotionToRewards` before the
  `rewardAllowed`/`smoked` checks) and only skips the reward screen, so no
  card reward is rolled. Since #641's fix the engine does the same:
  `GameContext::rollEscapedCombatRewardRng` rolls gold (hallway, elite), the
  elite relics (popped from their pools) and a potion, and the Colosseum
  slaver fight rolls a potion whether won or escaped.
  `STS_REWARDLESS_COMBAT_RNG_FIX=0` restores the legacy engine, which skipped
  these rolls.
- Dead Adventurer, Masked Bandits and Hypnotizing Colored Mushrooms also set
  their reward screen as the fight continuation. Since 2026-10-07 each one
  calls `afterBattle` on an escape, so the escape forfeits the event's gold,
  relic, potion and card rewards and clears the marker, like any other escape.
  Before that fix these escapes paid the full rewards and left
  `smokeBombUsed` set outside combat. Mind Bloom's fight is a boss, where
  Smoke Bomb is blocked.
- Searcher2, Searcher3, SimpleAgent, and shared action validity expose eligible
  use and reject blocked use. Potion discard remains independently legal.
- `apps/test.cpp::testIssueFixes` covers eligible escape, boss and
  `SURROUNDED` blocking, discard, search enumeration, post-combat relic
  processing, Colosseum and event-fight escapes, and unchanged ordinary potion behavior.

## Relevant code

- `include/combat/BattleContext.h::smokeBombEscapeBlocked`
- `src/combat/BattleContext.cpp::drinkPotion`, `exitBattle`
- `src/game/GameContext.cpp::afterBattle`
- `src/sim/search/Action.cpp::isValidPotionAction`
- `apps/test.cpp::testIssueFixes`
