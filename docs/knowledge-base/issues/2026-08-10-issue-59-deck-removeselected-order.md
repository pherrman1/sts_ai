# Issue 59: `Deck::removeSelected` wrong-card removal on multi-select

- **Status:** open
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/Deck.cpp:289-298`

## Symptom

`Deck::removeSelected` has dead sorted-`removeIdx` code. Removal iterates
`selectList` in reverse *pick* order, not descending deck-index order.
Picking a lower-index card first then a higher one removes card 1, shifts
the array, then `remove(3)` is out of range → `fixed_list::remove` just shrinks
size, dropping the wrong card.

Affects Astrolabe, Empty Cage, remove-2 screens.

## Evidence

- `Deck.cpp:289-298`: sorted `removeIdx` is computed but never used; removal
  iterates `selectList` directly.
- `Deck.cpp:289-298`: `fixed_list::remove` at an out-of-range index silently
  shrinks and drops the wrong card.
- GameContext.cpp:3634, 3655, 3776: call sites.

## Why it matters

Multi-card removals (Astrolabe, Empty Cage, Peace Pipe) can remove the wrong
card, silently changing the deck composition.

## Candidate fix directions

Use the sorted `removeIdx` array (descending order) for removal, or sort
the selectList by deckIdx before iterating.

## Relevant code

- `src/game/Deck.cpp:289-298`
- `src/game/GameContext.cpp:3634, 3655, 3776`
