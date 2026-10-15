# Issue 84: `Deck::anyCardBottled` logic inverted

- **Status:** closed (2026-08-10)
- **Fix:** `Deck::anyCardBottled` now returns true when any bottle slot is
  active (`bottleIdxs[i] != -1` for any i) instead of when any slot is empty
  (`== -1`). The removal shortcut at `Deck.cpp:254` only fires when NO card is
  bottled; the shift path now runs whenever a bottled card exists, so bottle
  indices stay aligned after removals (previously a removal while all three
  bottles were active corrupted `bottleIdxs`).
  Regression test: `./build/test issue_fixes` (ctest `issue_fixes`).
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/Deck.cpp:41-43`

## Symptom

`Deck::anyCardBottled` uses `||` instead of `&&` — inverted logic. The
`remove` shift path happens to be correct for both cases, so latent only.

## Evidence

- `Deck.cpp:41-43`: `||` should be `&&`.
- `Deck.cpp:254-271`: removal shift logic works for either interpretation.

## Candidate fix directions

Change `||` to `&&`.

## Relevant code

- `src/game/Deck.cpp:41-43`
