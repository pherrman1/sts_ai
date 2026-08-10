# Issue 53: Fairy in a Bottle + Sacred Bark revives at 1 HP

- **Status:** closed (2026-08-10, fixed in `src/game/GameContext.cpp`)
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/GameContext.cpp:2143`

## Symptom

`playerOnDie` with Fairy in a Bottle and Sacred Bark revives the player at
1 HP instead of 60% max HP. The operator precedence bug:

```cpp
curHp = std::max(1, static_cast<int>(hasBark ? 0.6f : 0.3f * static_cast<float>(maxHp)));
```

`*` binds tighter than `?:`, so `hasBark` evaluates to `(int)0.6f == 0`, then
`max(1, 0)` = 1 HP. Non-bark path is correct: `(int)(0.3f * maxHp)`.

## Evidence

- `src/game/GameContext.cpp:2143`: operator precedence error.
- `src/game/GameContext.cpp:2132-2157`: `playerOnDie` revive handling.

## Why it matters

Sacred Bark doubles potion effectiveness — but the Fairy revive is quartered
instead of doubled. A Bark-holder playing around Fairy revive will die anyway.

## Candidate fix directions

Add parentheses:
```cpp
curHp = std::max(1, static_cast<int>((hasBark ? 0.6f : 0.3f) * static_cast<float>(maxHp)));
```

## Resolution (2026-08-10)

Applied the parenthesized form above in `GameContext::playerOnDie`. A Sacred
Bark revive now restores 60% max HP (the non-bark path stays 30%). Regression
tests added to `apps/test.cpp` `testIssueFixes()` (both bark and non-bark
cases); `./build/test issue_fixes` PASS.

## Relevant code

- `src/game/GameContext.cpp:2143`
