# ADR-0032: Live OOC MCTS leaf rollouts shop greedily by default

Date: 2026-10-14
Status: accepted

## Context

Inside OOC MCTS leaf rollouts a shop is played by the native policy chain, whose last stage, `nativeShopPlan`,
enumerates every affordable subset of cards and relics (with and without the best removal), scores each bundle with
the floor model and executes only the first item of the best bundle. `STS_OOC_MCTS_ROLLOUT_SHOP=greedy` (#523)
instead scores leaving, each affordable item alone and the best removal alone, and buys the single best one, asking
again on the next decision.

Ledger §459 (128 fresh paired seeds, §433 `combo`, both arms with the ADR-0030 deck-size accounting) measured it:
103 vs 101 wins, +1.6 pp [−5.5, +8.6], NOT_SHOWN; paired wall-time ratio 0.889 [0.859, 0.922] (not pre-registered).
§463 later showed the deck-size accounting itself does not change play strength.

On 2026-10-14 Philipp chose to make it the default ("Greedy rollout also should be default").

## Decision

- When `STS_OOC_MCTS=1` and `STS_OOC_MCTS_ROLLOUT_SHOP` is unset, live OOC MCTS leaf rollouts shop greedily
  (`configureLiveOocMcts`).
- `STS_OOC_MCTS_ROLLOUT_SHOP=planner` restores the bundle planner; `greedy` equals the default; any other value is
  fatal.
- `OocAdapterOptions::greedyRolloutShop` stays false as a struct default, so offline tools and unit tests that build
  their own options are unchanged.
- Live shop roots (searched by the tree), the live fallback chain and runs without OOC MCTS (ADR-0027) keep the
  bundle planner.

## Consequences

- Every `STS_OOC_MCTS=1` run whose rollouts reach a shop can play differently from before. Earlier OOC MCTS results
  need `STS_OOC_MCTS_ROLLOUT_SHOP=planner` to reproduce; comparisons against controls from a binary without ADR-0032
  must set it in the new arm or rerun the controls.
- The `[live OOC MCTS ON …]` banner carries `rollout_shop=greedy` by default.
- **Unverified:** a playing-strength gain. §459 did not show one (NOT_SHOWN; paired wall-time ratio 0.889, not
  pre-registered).

## Evidence

Ledger §459, `docs/experiments/evidence/ooc_greedy_shop_459_20261013/`; §463,
`docs/experiments/evidence/ooc_deck_size_fix_463_20261014/`. Default equivalence: see the PR (decision traces with
the variable unset equal `greedy`, and with `planner` equal the pre-ADR binary).
