# ADR-0042: heart1full is the default OOC MCTS tree prior when heart1 weights are loaded

Date: 2026-10-17
Status: accepted

## Context

With `STS_OOC_MCTS_PRIOR=heart1`, heart1 (in the current A20 stack, student C `studentc.bin`) scores only the
nodes V4 can encode (`sourcePriorCovered`). Every other node gets a uniform prior: full-belt shops, reward screens
without a card reward, nodes with two or more card groups, and selectors other than UPGRADE. heart1 leaf-policy
rollouts had the same V4 gate and handed such screens to the native chain (V4 gates, trees, heuristics). A live
root that the search returned no action for went to the V4 chain. `STS_OOC_MCTS_PRIOR=heart1full` (PR #591) lets
heart1 score those nodes.

On 2026-10-17 Philipp decided: "ok teh prior hear1full should be default, no fallback to v4 or uniform."

## Decision

- When `STS_OOC_MCTS=1`, `STS_OOC_HEART1` is set and `STS_OOC_MCTS_PRIOR` is unset, the tree prior is heart1full
  (`configureLiveOocMcts`). `STS_OOC_MCTS_PRIOR=heart1` restores the V4-gated heart1 prior, and `=policy` the V4
  prior. Without `STS_OOC_HEART1` the default stays V4.
- Under heart1full with `STS_OOC_MCTS_LEAF_POLICY=heart1`, rollout steps on screens V4 cannot encode are also taken
  by heart1. A live root the search returns no action for goes to `heart1::policyStep` before the V4 chain.
- Card selects other than UPGRADE are excluded in all three places. Student C was distilled with no CARD_SELECT
  rows (audit-2026-10-17 heart1-distill, finding 1). Those nodes stay uniform in the tree and go to the chain in
  rollouts. A node heart1 cannot encode (Match and Keep, unmapped events) also stays uniform or goes to the chain.
  `heart1_leaf_reasons` counts these as `chain:screenN`.
- `OocAdapterOptions::heart1Coverage` stays false as a struct default, so offline tools and unit tests are
  unchanged.

## Consequences

- Every live OOC MCTS run with `STS_OOC_HEART1` set and no explicit prior can play differently than before. Runs
  that set `STS_OOC_MCTS_PRIOR=heart1` explicitly, such as the §504 arm C environment, are unchanged.
- **Unverified:** a playing-strength gain. No A/B has been run. One plumbing smoke (A20, seed 111123004, to the
  end of Act 1) showed `prior=heart1full`, 5,657 heart1 prior nodes and 0 prior fallbacks.
- The remaining non-heart1 paths are listed in `docs/knowledge-base/architecture/out-of-combat.md`.

## Evidence

PR #591; the adapter self-test (`oocmctsselftest`: a full-belt shop gets a heart1 prior under heart1full, and a
REMOVE select stays uniform); audit report `audit-2026-10-17/ooc-mcts-adapter.md`.
