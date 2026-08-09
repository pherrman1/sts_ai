# 2026-08-09 — Act-4 key collection in the default OOC policy chain

Date: 2026-08-09
Session/task: Fix missing `RT::KEY` collection so Act 4 (`THE_HEART`) is reachable in default `bestbench`.

## Decision

Every REWARDS handler in the OOC chain now takes the emerald (burning elite)
and sapphire (chest) keys via `search::GameAction(RT::KEY, 0)` immediately
after the potion handler, and every rest-room handler takes the ruby key
(RECALL, rest action 2) when `act >= 3 && !hasKey(RUBY_KEY)`. Applied at all
20 REWARDS blocks in `apps/one_combat.cpp` (each previously handled
GOLD → RELIC → POTION → CARD/SKIP only), in `restWinPolicy`
(`apps/one_combat.cpp`) as the active rest-room layer in the default chains, in
`ScumSearchAgent2::stepRewardsPolicy` + its `REST_ROOM` case (the base-policy
fallback used by `runFullRun` and every chain's `stepOutOfCombatPolicy`), and
in `SimpleAgent::stepRestScreen`.

## Rationale

The REWARDS chains and `ScumSearchAgent2::stepRewardsPolicy` never issued
`RT::KEY`, so emerald/sapphire keys were silently dropped and the ruby key was
never taken (rest layers heal/smith/random only), making Act 4 unreachable.
Key collection is required for the `bestbench` run to proceed past Act 3.

Ordering note: keys are taken **after** gold/relic/potion, per the fix spec.
For a chest (gold + relic + sapphireKey) the relic is taken first; the RELIC
`execute` in `src/sim/search/GameAction.cpp` clears `sapphireKey` only when
`getIdx1() == relicCount-1` **after** removal, which never holds for the
single-relic chest, so the sapphire key is then collected as well.

## Alternatives considered

- Placing the key handler before the RELIC handler — rejected: the fix spec
  says "after the potion handler"; the plan ordering also avoids forfeiting the
  chest relic.
- Restricting ruby-key recall to a single shared helper instead of layering it
  into `restWinPolicy` + both agent rest handlers — rejected: the
  `possibleEncounterOptions` trunk loop takes `actions.front()` without calling
  `restWinPolicy`, so a single-point fix would leave paths that never collect
  the key.

## Evidence

- `apps/one_combat.cpp` — 20 REWARDS chains (`runFullRunOOC`,
  `runFullRunDraft/Cards/Combo`, `runTraceRun`, `oocMapRouteSearchPolicy`,
  `possibleEncounterOptions`, `advanceOocToNextBattle`, `runOocNextCombatSeed`,
  `pathCounterfactualHeader`, `cardCounterfactualHeader`, `runCombatGenSeed`,
  `runFairGenSeed`, `runStrategicGenSeed`, `runStrategicGenSeed2`,
  `runFightGenSeed`, `runPolicyGenSeed`, `runDataGenSeed`, `runCausalGenSeed`,
  `dumpRun`), `restWinPolicy`, `possibleEncounterOptions` REST_ROOM branch.
- `src/sim/search/ScumSearchAgent2.cpp` — `stepRewardsPolicy`,
  `stepOutOfCombatPolicy` REST_ROOM case.
- `src/sim/search/SimpleAgent.cpp` — `stepRestScreen`.
- `src/sim/search/GameAction.cpp` — `executeRewardsAction` KEY case
  (`obtainKey` + chest-relic removal), rest action 2 = `chooseCampfireOption`
  RECALL (`src/game/GameContext.cpp`).
- Regression test: `apps/test.cpp::testKeyCollection` (`keys_collect`), CTest
  entry added in `CMakeLists.txt`.
- Note: the plan's function name `combatGenSeed3` does not exist in the tree;
  the equivalent datagen loops are `runCombatGenSeed` / `runFightGenSeed`.

## Status and follow-up

- Implemented. `bestbench` (and all listed run/datagen/counterfactual loops)
  now collect all three keys; Act 4 is reachable in principle. A paired
  re-measurement of bestbench win-rate is the follow-up, since prior baselines
  predate key collection.
