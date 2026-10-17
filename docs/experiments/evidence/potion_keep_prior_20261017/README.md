# STS_OOC_MCTS_POTION_KEEP_PRIOR smoke (2026-10-17)

Binary: `one_combat` built from `3fafc034` (sha256 `0fb6a45d…de523d`). `smoke.sh ARM SEED` with the §503 A20
environment, student C, 128 OOC simulations, `STS_OOC_MCTS_PRIOR=heart1full`; arm `on` adds
`STS_OOC_MCTS_POTION_KEEP_PRIOR=1`. Seeds 111155040-111155051, both arms. `keep_split.py` reads the
decision logs; output in `keep_split.out`.

- Off: 7 reward roots without cards offered discards, all with a uniform prior; search discarded on 4.
- On: 5 such roots. 4 got the keep prior and none discarded. The fifth stayed uniform because both discards
  tied "Leave rewards" (held Block Potions, reward Block Potion: equal keep values, so the swap is a no-op);
  search took that no-op swap.
- Roots with cards already had heart1full's prior in both arms; no discard picked in either.
- Outcomes 2 vs 1 wins, 3 vs 3 runs reaching Act 4. A smoke, not an A/B.
