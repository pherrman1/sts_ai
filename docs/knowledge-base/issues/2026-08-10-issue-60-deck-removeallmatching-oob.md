# Issue 60: `Deck::removeAllMatching` off-by-one (Vampires drops real card)

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/Deck.cpp:301-310`

## Symptom

`Deck::removeAllMatching` starts the loop at `cards.size()` instead of
`cards.size() - 1`. `fixed_list::remove` leaves the removed card's value
in the stale slot, so the Vampires event can spuriously match the stale
value and drop a real last card.

## Evidence

- `Deck.cpp:301-310`: `for (int i = cards.size(); i >= 0; --i)` should
  start at `cards.size() - 1`.
- `GameContext.cpp:3472`: Vampires event call site.

## Why it matters

Vampires event can incorrectly remove a non-Strike card from the deck.

## Candidate fix directions

Change loop bound: `for (int i = cards.size() - 1; i >= 0; --i)`.

## Relevant code

- `src/game/Deck.cpp:301-310`
