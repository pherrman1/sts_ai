# ADR-0052: an unsupported OOC MCTS edge is pruned instead of aborting the whole root search

Date: 2026-10-18
Status: accepted

## Context

When the CTM refuses an imagined combat anywhere in an OOC MCTS search, or any other `OocSearchUnsupported` is raised
(semantic execution, depth safety cap, continuation step limit), the planner discarded the whole root, including the
visits and Q of every supported path, and the decision fell back to the V4/OOC policy chain (issue #633). Known
triggers: imagined A20 max HP 23 outside the CTM HP envelope (issue #634, 54 aborts in §425; about 0.1% of decisions
in §486), Lizard Tail boundaries on legacy stacks, and live-advisor fallbacks.

On 2026-10-18 at 22:55Z Philipp wrote in the #634 status thread: "fix 633. does not need a A/B, just keep it on by
default".

## Decision

- `OocMctsConfig::pruneUnsupported` (planner default off, so library callers keep the old contract):
  - an `OocSearchUnsupported` below the root discards that simulation, rolls back its visits and backs nothing up;
  - the action edge whose transition or successor evaluation raised it is pruned from selection;
  - a decision node whose actions are all pruned prunes its own parent edge;
  - the root aborts, as before, only when every root action is pruned;
  - pruned root actions are never selected and are flagged `pruned` in root traces and policy-target rows.
- OOC MCTS runs (`one_combat`) and the live advisor turn it on. `STS_OOC_MCTS_PRUNE_UNSUPPORTED=0` restores the
  whole-root abort.
- Provenance: `unsupportedSimulations`, `prunedActions` and `prunedReasons` in decision profiles, policy-target rows
  and the trace `.support.jsonl`; the startup banner and `[ooc-mcts-config]` print the setting.

## Consequences

- Play changes only in searches that previously aborted. Those decisions now take the searched action over the
  surviving edges instead of the fallback chain. Runs with `=0`, or pinned to an older commit, are unchanged.
- **Inference:** pruning hides the refused futures, so an action whose futures the CTM cannot price looks only as good
  as its supported samples. This is the accepted trade against discarding the whole search.
- **Unverified:** a playing-strength effect. No A/B was run, by Philipp's decision; the affected share of decisions
  is small (about 0.1% in §486, 0 in §504).
- Issue #634 (widening the CTM HP envelope) no longer causes whole-root aborts on the default configuration.
