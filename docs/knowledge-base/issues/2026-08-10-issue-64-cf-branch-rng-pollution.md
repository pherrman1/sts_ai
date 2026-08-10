# Issue 64: Counterfactual branch RNG pollution via `[=]` lambda capture

- **Status:** closed (2026-08-10, fixed in `src/game/GameContext.cpp`)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/GameContext.cpp:2620, 2683, 3030, 3075`

## Symptom

Event-fight `regainControlAction` lambdas use `[=]`, which captures `this` —
not the branch copy. `DEAD_ADVENTURER` calls `createCardReward(...)` on the
original context (consumes original `cardRng`, `cardRarityFactor`, `potionRng`).
`MASKED_BANDITS` and `HYPNOTIZING_COLORED_MUSHROOMS` use original `potionRng`.

A counterfactual branch that hits one of these event fights advances the
parent/live run's RNG streams — breaking the CRN invariant claimed at
`one_combat.cpp:285-286` and diverging the live run.

## Evidence

- `GameContext.cpp:2620-2630`: DEAD_ADVENTURER uses `[=]`, calls on `this`.
- `GameContext.cpp:2683`: DESIGNER_IN_SPIRE case 4 uses original `miscRng`.
- `GameContext.cpp:3030-3042`: MASKED_BANDITS uses original `potionRng`.
- `GameContext.cpp:3075-3088`: HYPNOTIZING_COLORED_MUSHROOMS same.
- `apps/one_combat.cpp:285-286`: CRN invariant claim.

## Why it matters

Counterfactual evaluation correctness — branch evaluation should not
side-effect the live run's state or RNG.

## Candidate fix directions

Change the lambdas to capture the branch copy explicitly, or use a
`shared_ptr<GameContext>` that the branch owns.

## Resolution (2026-08-10)

`regainControlAction` is always invoked with the owning context
(`GameContext::regainControl()` calls `regainControlAction(*this)`;
`BattleContext::exitBattle` calls `g.regainControl()`), so a lambda inherited
by a branch copy is invoked with the branch as its `gc` argument while its
`[=]`-captured `this` still points at the original context. Fixed the four
lambdas in `GameContext::chooseEventOption` to operate on `gc` instead of the
captured `this`:

- DEAD_ADVENTURER: `createCardReward`/`addPotionRewards` now `gc.`-qualified
  (was: consumed the original's `cardRng`/`cardRarityFactor`/`potionRng`).
- DESIGNER_IN_SPIRE case 4: `upgradeRandomCards` now uses `gc.miscRng`
  (was: original `miscRng`).
- MINDBLOOM case 0: `addPotionRewards` now `gc.`-qualified.
- HYPNOTIZING_COLORED_MUSHROOMS: `createCardReward`/`addPotionRewards` now
  `gc.`-qualified.

MASKED_BANDITS (line ~2997) was already correct: it uses `[goldAmt]` capture
and `gc.createCardReward`. MYSTERIOUS_SPHERE's `[=]` lambda only calls
`gc.afterBattle()` and never touches `this`. Regression test added to
`apps/test.cpp` `testIssueFixes()` (branch copy resolving a DESIGNER_IN_SPIRE
remove-select must not advance the original's `miscRng`); `./build/test
issue_fixes` PASS.

## Relevant code

- `src/game/GameContext.cpp:2620, 2683, 3030, 3075`
