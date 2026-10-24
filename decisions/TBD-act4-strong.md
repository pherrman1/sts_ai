# ADR-TBD: Stronger Silver search in Act 4 (Shield and Spear 10k with prior playouts, the Heart 40k)

Date: 2026-10-24
Status: accepted

Changes Act 4 of [ADR-0051](0051-a20-learned-stop-default.md) (learned stop) and of
[ADR-0056](0056-silver-prior-playout-boss-only.md) (elite rooms play greedy playouts).

## Context

After the Act-3 boss the run heals 80% of missing HP, so of Act 4's two fights Shield and Spear (S&S) sets the HP
the Heart starts with. §TBD-a replayed 128 S&S and 128 Heart entry states from the 1,024-seed guard (8 copies each)
under six Silver configurations. S&S with prior playouts at 10k simulations loses 4.5 HP less than production
(greedy playouts under the learned stop: [+3.1, +5.9]); more budget without prior playouts saves 1.1 HP. The
Heart did not gain from 40k (+0.9 pp [−1.1, +3.0]), but Silver dropped its reused tree at ~30% of 40k reroots
(node cap 32,768). §TBD-b repeated the 40k cells with the cap at 262,144: the Heart then wins +2.4 pp [+0.6, +4.2]
more than production's 10k, with prior playouts.

Philipp decided on 2026-10-24 (17:00Z): "Die extra Kosten sind es mir für beide Combats wert."

## Decision

- Whole-run Silver fights in Act 4, with the learned stop on and a root prior set (scope not `override`), replace the
  learned stop with a flat budget:
  - ELITE room (Shield and Spear): 10,000 simulations with prior-argmax playouts (as ADR-0050's boss rooms).
  - BOSS room (the Heart): 40,000 simulations with prior playouts, and the tree-reuse cap raised to 262,144 nodes.
- Searches with a budget, rollout, root-prior or prior-net override (research arms, source runs, imagined OOC MCTS
  fights), the stop trace, runs without the learned stop and the live advisor (no root prior) are unchanged.
  `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` still turns prior playouts off everywhere.
- `STS_SILVER_ACT4_STRONG=0` restores the learned stop in Act 4 (greedy S&S playouts, 32,768-node cap).
- The Silver leaf specification records `"act4_strong": true`; the engine banner says "Act 4 strong".

## Consequences

- CPU. In the replays a production S&S fight took about 6 s and a Heart fight about 58 s (single thread); the new
  settings take about 36 s and 4 min. A20 runs that reach Act 4 cost correspondingly more.
- Every A20 comparison with older runs that reach Act 4 needs `STS_SILVER_ACT4_STRONG=0` (comparability flag).
  Teacher and specification JSONs written before this ADR lack `act4_strong` and are refused by the `silver_leaf`
  equality check unless matched with `=0`.
- Act-4 outcomes in data generators that run the learned stop with a root prior (heartoutcomegen) change. The CTM's
  Act-4 survival model and its calibration were fit on learned-stop outcomes and may now be pessimistic for Act 4.
- Not gated by a run-level A/B. The evidence is fight level on 128 guard states per fight; the replay misses Burning
  Blood's end-of-combat heal (it lowers both arms alike).
