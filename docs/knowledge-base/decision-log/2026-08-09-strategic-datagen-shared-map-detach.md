# 2026-08-09 — Strategic datagen probe loops detach the shared map

Date: 2026-08-09
Session/task: Fix the shared-map hazard in the strategic datagen
probe/chosen-detection loops in apps/one_combat.cpp.

## Decision

`runStrategicGenSeed` and `runStrategicGenSeed2` (apps/one_combat.cpp) now
detach the map on each per-action successor probe, following the existing
`regretGateChoose` pattern:

```cpp
GameContext probe = pre;
probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
a.execute(probe);
```

Previously `probe = pre` shared `pre`'s `Map` through its `shared_ptr`.
`transitionToAct` regenerates the map **in place** (`*map = Map::fromSeed(...)`,
src/game/GameContext.cpp::transitionToAct), so a probe executing the
BOSS_RELIC_REWARDS SKIP action mutated the map object shared by `pre` and the
live `gc`. That left the live run on the next act's map while `act`/`floorNum`/
`screenState` still described the current act, and made every row of that
decision (`richRow(pre, path)`, which includes forward-map features) encode
next-act map features with the current act's floor number. Detaching the probe
confines the regeneration to the probe's own copy.

## Rationale

`stratFingerprint` reads only `GameContext` fields (screen/act/floor/hp/gold/
keys/potions/deck/relics/rewards/select size), never `gc.map` content, so the
fingerprint-based chosen detection is unaffected by the detach. The label loop
in `runStrategicGenSeed2` already used `detachedCounterfactualCopy` and is
unchanged.

## Alternatives considered

- Guard `if (gc.map)` like `detachedCounterfactualCopy` — the map is always
  non-null at decision points (constructed in `GameContext::GameContext`), and
  the reference `regretGateChoose` pattern is unguarded; kept the unguarded
  form for consistency with the reference.
- Detach once on `pre` instead of per probe — `pre` must remain a faithful
  snapshot of the pre-decision state, and the per-probe detach is the minimal
  change.

## Evidence

- `apps/one_combat.cpp::runStrategicGenSeed`, `runStrategicGenSeed2` (probe
  loops now detach), `regretGateChoose` (reference pattern),
  `detachedCounterfactualCopy` (existing helper with the same invariant).
- `src/game/GameContext.cpp::transitionToAct` (`*map = Map::fromSeed(...)` in
  place).
- `src/sim/search/ScumSearchAgent2.cpp` BOSS_RELIC_REWARDS branch: the live
  policy always takes a boss relic, so only probes can trigger the transition.
- `./build/one_combat strategicgen 4 50 0` → 2543 rows from 4 runs, clean
  exit; ctest 10/10 passed.

## Status and follow-up

- Implemented. `regretGateChoose`'s own action-match loop
  (`GameContext probe2 = pre; actions[i].execute(probe2);`) still shares the
  map and has the same latent hazard if a one-ply gate ever runs on a
  BOSS_RELIC_REWARDS decision; not in the datagen path today.
- Note: a `strategicgen2` smoke run (4 seeds, sims=50, no STS_VNET) aborts in
  `BattleScumSearcher2::playoutRandom` (empty action enumeration in a branch
  rollout). Reproduced identically on the unmodified tree — pre-existing and
  unrelated to this change.
