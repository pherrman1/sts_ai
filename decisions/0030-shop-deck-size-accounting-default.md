# ADR-0030: Native shop planning uses corrected deck-size accounting by default

Date: 2026-10-13
Status: accepted

## Context

`nativeShopPlan` values each affordable shop bundle as an edit of the current
rich feature vector and scores it with the floor model `v_rich_trees.txt`. The
legacy edit counted every purchased item, relics included, as one more deck
card, and a planned card removal did not lower deck size. Real states never
look like that: relics leave `deckSize` unchanged and a removal lowers it.

`STS_OOC_SHOP_DECK_SIZE_FIX=1` (overnight campaign, 2026-10-08) already
corrected this as an opt-in flag, covered by
`tests/native_ooc_shop_features_test.cpp`. Its playing strength was never
measured. The same planner runs in the MCTS-off chain, the OOC MCTS fallback
and the OOC MCTS leaf rollouts, and the opt-in greedy rollout shop option
(`STS_OOC_MCTS_ROLLOUT_SHOP=greedy`, #523) reuses the same accounting.

On 2026-10-13 Philipp chose to turn it on ("Deck size should be on").

## Decision

- With `STS_OOC_SHOP_DECK_SIZE_FIX` unset, the native shop planner counts only
  purchased cards in deck size and subtracts one for a planned removal.
- `STS_OOC_SHOP_DECK_SIZE_FIX=0` restores the legacy accounting exactly;
  `1` is accepted and equals the default; any other value is fatal.
- The startup banner `[native OOC shop deck-size correction ON]` and the
  counterfactual teacher policy flag `native_ooc_shop_deck_size_fix` now
  appear by default.
- Nothing else changes: the floor model, the removal target pick, potions
  (still never bought by the planner) and server-backed shop modes.

## Consequences

- Every native-OOC run that visits a shop can play differently from before,
  with or without OOC MCTS. Earlier results need `STS_OOC_SHOP_DECK_SIZE_FIX=0`
  to reproduce.
- **Unverified:** the playing-strength effect. The default was chosen because
  the corrected features match real states, not because a game test passed.

## Evidence

`tests/native_ooc_shop_features_test.cpp` (relic, removal and card cases;
explicit 0 keeps the legacy plans). Overnight campaign worked case:
`docs/experiments/evidence/ironclad_a0_overnight_20261008/strategy/SHOP_WORKED_CASE.md`.
