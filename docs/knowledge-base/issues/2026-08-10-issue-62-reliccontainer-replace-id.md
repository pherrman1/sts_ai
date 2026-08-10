# Issue 62: `RelicContainer::replaceRelic` compares wrong ID

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/Game.cpp:29-36`

## Symptom

`RelicContainer::replaceRelic` checks `if (relic.id == r)` instead of
`if (relic.id == o)`. The Golden Idol→Bloody Idol event leaves a stale
GOLDEN_IDOL entry (bits cleared but still in the `relics` vector). Visible
to `size()`, N'loth's relic shuffle, and `getRelicValue`.

## Evidence

- `Game.cpp:29-36`: `relic.id == r` should be `relic.id == o`.
- `GameContext.cpp:2792`: Golden Idol→Bloody Idol event.
- `GameContext.cpp:2795-2800`: N'loth's relic shuffle reads `size()`.

## Why it matters

The stale entry persists and affects any logic that iterates relics, including
N'loth's event and relic counting.

## Candidate fix directions

Fix the comparison: `if (relic.id == o)`.

## Relevant code

- `src/game/Game.cpp:33`
