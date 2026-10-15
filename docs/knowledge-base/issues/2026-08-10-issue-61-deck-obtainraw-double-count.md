# Issue 61: `Deck::obtainRaw` double-counts stats on save load

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/Deck.cpp:193-212`

## Symptom

`Deck::initFromSaveFile` → `obtainRaw` increments `transformableCount` and
`cardTypeCounts` once at line 194-195 and again in each switch branch
(201-211). Gates like `getTransformableCount(2) >= 2` can then offer
"transform 2" with only 1 transformable card, deadlocking the select screen.

## Evidence

- `Deck.cpp:193-212`: double increment of `transformableCount` and
  `cardTypeCounts`.
- `src/sim/search/GameAction.cpp:87`: gate checking `getTransformableCount`.

## Why it matters

After a save-load roundtrip, multi-card transform screens may be offered
with insufficient cards, potentially deadlocking the UI.

## Candidate fix directions

Remove the duplicate increments in the switch branches or the initial
increments at 194-195.

## Relevant code

- `src/game/Deck.cpp:193-212`
