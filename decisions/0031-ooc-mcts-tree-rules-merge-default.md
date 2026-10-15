# ADR-0031: Live OOC MCTS applies tree rules and merges equivalent outcomes by default

Date: 2026-10-14
Status: accepted

## Context

The OOC MCTS decision trace of seed 74060000 (`/mnt/project-files/ooc-decision-trace/REPORT.md`) showed the §433
`combo` tree is about one decision deep: maximum depth 2, every search ended on the visit lock at about 2,050
simulations, and the pick equalled the top V4 prior in 72 of 87 searches. Inside the tree, forced steps the live
chain never searches (gold, potion and relic pickups, chests, empty reward screens) competed as decisions, and each
copy of a card was its own bottle, duplicate or bonfire target.

`STS_OOC_MCTS_TREE_RULES=1` (#532) applies the live forced steps inside the tree and at the live root and coalesces
those selectors per distinct card. `STS_OOC_MCTS_MERGE_OUTCOMES=1` (#384, §367) pools sampled successors with equal
search-equivalence keys. Ledger §464 (128 fresh paired seeds, §433 `combo` with current defaults) measured the pair:
107 vs 104 wins, +2.3 pp [−6.3, +10.2], NOT_SHOWN; median per-search depth 2 → 4; about 6% more wall time.

On 2026-10-14 Philipp chose to make both the default ("both flags should be default").

## Decision

- When `STS_OOC_MCTS=1` and the variables are unset, live OOC MCTS runs with tree rules and outcome merging on
  (`configureLiveOocMcts`).
- `STS_OOC_MCTS_TREE_RULES=0` and `STS_OOC_MCTS_MERGE_OUTCOMES=0` each restore the previous behaviour; `1` equals the
  default; any other value is fatal.
- The planner and adapter struct defaults (`OocMctsConfig::mergeEquivalentOutcomes`, `OocAdapterOptions::treeRules`)
  stay false, so offline tools and unit tests that build their own configuration are unchanged.
- Runs without OOC MCTS (the default stack, ADR-0027) are unaffected.

## Consequences

- Every `STS_OOC_MCTS=1` run can play differently from before. Earlier OOC MCTS results need
  `STS_OOC_MCTS_TREE_RULES=0 STS_OOC_MCTS_MERGE_OUTCOMES=0` to reproduce; comparisons against controls from a binary
  without ADR-0031 must set both to 0 in the new arm or rerun the controls.
- The `[ooc-mcts-config]` banner reports `"mergeOutcomes":true` by default.
- **Unverified:** a playing-strength gain. §464 did not show one; the default was chosen because the tree now follows
  the live rules and searches deeper, not because a game test passed.

## Evidence

Ledger §464, `docs/experiments/evidence/ooc_tree_rules_464_20261014/`. Default equivalence: with both variables
unset the binary reproduces the §464 `rulesmerge` smoke on seed 74065000, and with both set to 0 the `combo` smoke
(see the PR for #532).
