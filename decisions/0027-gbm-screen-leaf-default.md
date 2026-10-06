# ADR-0027: The GBM screen leaf is the default OOC MCTS leaf value

Date: 2026-10-06
Status: accepted

## Context

Live OOC MCTS (`STS_OOC_MCTS=1`) valued an unresolved non-map leaf by playing
the floor out with the fixed policy chain to the next MAP and asking v_win
there (`STS_OOC_MCTS_LEAF_VALUE=native`). Issue #379 asked whether a
screen-aware value can replace that playout.

Evidence (all at OOC 2048 simulations, exact 10k Silver, X2-B selected):
- Offline, on the frozen #334 VALIDATION split (329,425 decision rows), an
  XGBoost residual on X2-B's margin over the 461 X2-B run features plus
  fixed-width public screen features reaches NLL 0.418, against 0.423 for X2-B
  applied directly at the decision state and 0.431 for the #379 MLP. The gain
  is concentrated in boss relics (0.527 to 0.454) and rewards (0.422 to 0.416).
- Online, on 128 paired seeds 47001024..47001151, the GBM screen leaf vs the
  playout leaf: wins 61.7% vs 58.6% (+3.1 pp, 95% CI −7.8 to +14), mean floor
  47.6 vs 47.3 (+0.3, CI −1.2 to +1.8), about 0.6x the time per run.
- On 512 paired seeds 47000000..47000511, X2-B directly (no playout) vs the
  playout: +1.4 pp wins (CI −3.3 to +6.1), +0.3 floors, 0.56x time.

Strength is statistically tied with the playout; the screen leaf is much
faster and is the only screen model that did not lose to X2-B directly.
Evidence: `docs/experiments/evidence/ooc_leaf_direct_probe_20261006/`.

Philipp chose to make it the default on 2026-10-06.

## Decision

When `STS_OOC_MCTS_LEAF_VALUE` is unset, live OOC MCTS uses `screengbm`:
- covered non-combat, non-map leaves (all seven DECISION screen families) are
  `sigmoid(logit(X2-B) + residual)` with the residual model
  `models/candidates/screen_leaf_gbm_v1.trees`
  (`STS_OOC_MCTS_SCREEN_LEAF_MODEL` overrides);
- the anchor, including at MAP leaves, is the pinned X2-B tree file
  `models/candidates/v_win_x2b_trees.txt`, independent of `STS_WIN_NET`,
  because the residual was trained on X2-B's margin;
- screens the public contract cannot encode fall back to the anchor directly;
- terminals stay exact; combat resolution, priors, PUCT and every other
  setting are unchanged.

`STS_OOC_MCTS_LEAF_VALUE=native` restores the playout leaf. `STS_OOC_MCTS`
itself stays off by default; this only changes its leaf when it is enabled.

## Consequences

- OOC MCTS spends far less CPU per leaf; real combat and policy priors now
  dominate MCTS time.
- The pinned anchor means OOC MCTS leaf values no longer follow `STS_WIN_NET`.
- Strength gains over the playout or over X2-B directly are not yet shown;
  a larger paired run is needed to claim them.
- The live advisor build does not include the screen models and keeps its own
  leaf configuration.
