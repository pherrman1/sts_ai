# Issue 86: Awakened One premature victory (stage 2 skipped)

> Provenance: originally recorded under duplicate legacy ID #51; renumbered to
> canonical #86 during documentation cleanup (2026-08-11). Substantive issue
> evidence is unchanged.

- **Status:** closed (2026-08-10)
- **Fix:** `Monster::die()` victory predicate is now `monstersAlive == 0 &&
  !anyHalfDead()` where `MonsterGroup::anyHalfDead` covers only the Awakened
  One stage 1 (the half-dead monster with a MANDATORY rebirth). Darklings are
  excluded because their regrow is pre-empted by victory at `monstersAlive ==
  0` (last Darkling stays dead; a blanket half-dead check would loop the
  fight). Regression tests: `./build/test awakened_one_stage2` and
  `./build/test darkling_victory` (ctest `awakened_one_stage2`,
  `darkling_victory`).
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/Monster.cpp`, `src/combat/MonsterSpecific.cpp`

## Symptom

If both Cultists die in the same round as Awakened One stage 1 (e.g., via
Corpse Explosion pop or AoE), `monstersAlive` reaches 0 before the
`AWAKENED_ONE_REBIRTH` action executes. `Monster::die()`'s victory predicate
(`monstersAlive == 0`) fires, granting PLAYER_VICTORY with the boss
mid-revival — Act 3 boss stage 2 is skipped.

## Evidence

- `Monster.cpp:280-296`: `die()` decrements `monstersAlive`, and at 291-296
  checks `monstersAlive == 0` to set VICTORY.
- `MonsterSpecific.cpp:1689-1699`: `AWAKENED_ONE_REBIRTH` increments
  `monstersAlive` but cannot undo a decided `outcome`.
- The codebase already models half-dead elsewhere: `!m.isHalfDead()` checks
  in Feed/HandOfGreed (`Actions.cpp:1080,1113`).

## Why it matters

The Awakened One is an Act 3 boss. Skipping stage 2 inflates Act 3 clear rates
and win rates in benchmarks against this encounter.

## Candidate fix directions

Change `die()`'s victory predicate to exclude half-dead monsters:

```
if (monstersAlive == 0) → if (monstersAlive == 0 && !anyMonsterHalfDead())
```

or equivalently check `!m.isHalfDead()` in the die() victory condition.

## Relevant code

- `src/combat/Monster.cpp:280-296` (`die`)
- `src/combat/MonsterSpecific.cpp:1689-1699` (`AWAKENED_ONE_REBIRTH`)
- `src/combat/Actions.cpp:1080,1113` (`isHalfDead` precedent)
