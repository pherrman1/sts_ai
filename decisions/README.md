# Architectural decision records

This directory contains durable, evidence-backed architectural decision records
(ADRs). These ADRs capture only the small set of decisions whose current rationale is directly supported by repository evidence. New durable choices belong here.

Git-tracked Markdown is authoritative. Derived local indexes never replace an
ADR, source code, tests, curated knowledge-base pages, or raw evidence.

## What belongs here

Create an ADR only for a current, durable architecture or operating boundary
with a meaningful alternative and repository evidence. Every record must name
affected files and exact evidence. Do not promote a one-off bug fix, temporary
plan, dated run state, unresolved investigation, or experimental outcome.
Experiment measurements remain in [`EXPERIMENTS.md`](../EXPERIMENTS.md) and its
ledger shards; maintained technical understanding remains in
[`docs/knowledge-base/`](../docs/knowledge-base/).

## Lifecycle

Use the deterministic `0001-<slug>.md` filename scheme and the standard ADR
sections. A PR adds a new ADR as `TBD-<slug>.md` with `ADR-TBD` references; the
number is assigned at merge by `tools/ledger_assign.py` (see
[agent workflow](../docs/knowledge-base/operations/agent-context-and-workflow.md#ledger-and-adr-numbers)). If a decision changes, add a new ADR that states what it supersedes
and links the historical record; do not rewrite the old ADR or chronological
entry. Mark the earlier ADR `superseded` only when current evidence establishes
the replacement.

## Current architecture ADRs

- [ADR-0046](0046-silver-rollout-root-table-default.md) makes Silver's greedy leaf rollouts use a card table
  built per searched root by the gen-6 E prior (`STS_SILVER_ROLLOUT_ROOT_TABLE=0` restores the ADR-0040 table).

- [ADR-0043](0043-az-loop-gumbel-policy-target.md) makes the planned AlphaZero-style OOC loop train its
  policy on Gumbel completed-Q targets rather than raw visit shares (no default changes).

- [ADR-0042](0042-heart1full-prior-default.md) makes heart1full the live OOC MCTS tree prior when
  `STS_OOC_HEART1` is set (`STS_OOC_MCTS_PRIOR=heart1` or `=policy` restores the old prior).

- [ADR-0041](0041-a20-heart-objective.md) sets whole-run defaults to A20 Ironclad
  Heart kills, required key collection and goal-aware terminal labels.

- [ADR-0040](0040-silver-rollout-card-table-default.md) makes Silver's greedy leaf rollout play cards by the
  gen-6-fitted table by default (§479 NOT_SHOWN, 0.89x CPU per fight; `STS_SILVER_ROLLOUT_CARD_TABLE=0` restores
  the hand-written priority list).
- [ADR-0039](0039-potion-reward-swap.md) lets the out-of-combat policy discard its worst potion for a better
  reward potion when slots are full (`STS_POTION_REWARD_SWAP=0` restores the free-slot-only pickup).
- [ADR-0038](0038-neow-transform-curse-fix.md) makes Neow "transform two cards" add a curse only
  with the CURSE drawback (`STS_NEOW_TRANSFORM_CURSE_FIX=0` restores the legacy curse on every pick).
- [ADR-0037](0037-live-advisor-escape-penalty.md) gives the live-game advisor the same `12,35` escape penalty
  (no environment override on the live path; elite fights from the wire encounter).
- [ADR-0036](0036-silver-escape-penalty-default.md) makes native Silver charge a Smoke Bomb
  escape for the forfeited rewards by default (`12,35`, §473 NOT_SHOWN; `STS_SILVER_ESCAPE_PENALTY=0,0` restores
  escape scored as a win).
- [ADR-0035](0035-silver-situational-leaf-default.md) turns Silver's situational leaf terms on by
  default (final-fight leaf, no loss potion credit, relic heal leaf, A20 boss heal fix; each `=0` restores the
  legacy term).
- [ADR-0034](0034-recall-filter-and-multiselect-canonical-default.md) turns on the
  keys-off optional Ruby Recall filter and canonical multi-select masks by default
  (`STS_OOC_SKIP_OPTIONAL_RECALL=0`, `STS_MULTISELECT_CANONICAL=0` restore the old behavior).
- [ADR-0033](0033-ooc-mcts-a20-ctm-default.md) makes live OOC MCTS use the calibrated
  A20 CTM (`pathb-a20`, §470) for ascension-20 searches on the automatic CTM stack
  (`STS_OOC_MCTS_A20_CTM=0` restores the default stack at A20).
- [ADR-0032](0032-ooc-mcts-greedy-rollout-shop-default.md) makes live OOC MCTS leaf
  rollouts shop greedily by default (`STS_OOC_MCTS_ROLLOUT_SHOP=planner` restores the
  bundle planner).
- [ADR-0031](0031-ooc-mcts-tree-rules-merge-default.md) makes live OOC MCTS apply the
  live forced-step rules in the tree and merge equivalent outcomes by default
  (`STS_OOC_MCTS_TREE_RULES=0`, `STS_OOC_MCTS_MERGE_OUTCOMES=0` restore the old tree).
- [ADR-0030](0030-shop-deck-size-accounting-default.md) makes the native shop
  planner's corrected deck-size accounting the default
  (`STS_OOC_SHOP_DECK_SIZE_FIX=0` restores the legacy accounting).
- [ADR-0029](0029-public-x2b-ooc-mcts-win-model.md) makes the §444 public X2-B
  the default win model when `STS_OOC_MCTS=1` and `STS_WIN_NET` is unset
  (`STS_WIN_NET=1` restores B0; runs without OOC MCTS keep B0).
- [ADR-0028](0028-public-encounter-futures-default.md) makes the native OOC
  fallback score 8 public encounter futures by default
  (`STS_OOC_PUBLIC_FUTURES` unset = 8; `0` restores the hidden inputs).
- [ADR-0026](0026-learned-silver-stopping-default.md) makes learned Silver
  stopping (model `gbt-770201c31f7b`) the whole-run default budget instead of
  the #199 adaptive rule, amending ADR-0018.
- [ADR-0025](0025-runic-monster-identity-and-damage-beliefs.md) records
  canonical monster occupant identity and public persistent-damage beliefs
  under Runic Dome.

- [ADR-0023](0023-native-equivalent-copy-reroot.md) reroots native Silver
  through a different physical copy of an equivalent card by an exchanged-id
  lookup, restoring ADR-0015's intent.
- [ADR-0022](0022-remove-vendored-silver.md) removes the vendored Silver model,
  its bridge, the root prior and the Silver research tools; frozen research
  contracts move to native Silver and vendored `silver_uct` teachers are
  rejected. It supersedes ADR-0015.
- [ADR-0021](0021-native-silver-default.md) makes the Silver search ported
  onto the main engine the default combat backend (its vendored opt-out was
  removed by ADR-0022).
- [ADR-0020](0020-silver-only-combat-remove-searcher2-and-selfplay.md) makes
  Silver the only combat searcher, removes Searcher2 with its
  search-statistics generators and controls, and removes the self-play loop.
- [ADR-0019](0019-remove-searcher3.md) removes Searcher3 and its
  Searcher3-only modes, flags, tests and scripts; `STS_SEARCHER3=1` now
  fails.
- [ADR-0018](0018-silver-default-combat-backend.md) makes Silver fair play
  the default combat backend for `run`, `bestbench` and `reprobench`; it
  supersedes ADR-0003.
- [ADR-0015](0015-live-silver-equivalent-copy-reroot.md) (superseded by
  ADR-0022) preserved retained live Silver visits when the human played a
  different equivalent physical card copy.
- [ADR-0014](0014-live-ooc-visit-lock-stopping.md) enables live strict visit-lock
  stopping through an explicit policy override while retaining the false
  non-aborting provider guarantee and a rollback switch.

## Current routing ADRs

- [ADR-0024](0024-local-research-execution.md) retires the cloud launcher and
  fixed local seed ceiling, preserving explicit authorization and frozen
  provenance for larger local research runs. It supersedes ADR-0006/0009.

- [ADR-0017](0017-silver-quiescent-queue-item-identity.md) accepts
  quiescent Silver queue-item identity without retained-root rewriting.
- [ADR-0016](0016-silver-settled-queue-item-identity.md) records the rejected
  settled Silver queue-item identity candidate and consumed HOLDOUT evidence.

- [ADR-0012](0012-frozen-session-decision-log.md) routes historical session material to Git history and new knowledge to canonical maintained destinations.
- [ADR-0011](0011-mcp-free-codex-skillopt-pilot.md) defines the MCP-free Codex
  path, authoritative tracked KB, bounded SkillOpt proposal pilot, and
  independent evaluator gate. It supersedes only ADR-0010's active tool routing.
- [ADR-0010](0010-codex-chatgpt-agent-workflow.md) remains authoritative for
  the ChatGPT/Sol handoff, bounded Codex preflight, evidence-packet review
  boundary, session continuation rules, and reviewed-SHA freeze. Its tool
  routing is historical and superseded by ADR-0011.
- [ADR-0008](0008-guarded-cline-serena-repowise-routing.md) is retained as the
  historical Cline-era routing decision and is superseded by ADR-0010 for
  harness/routing policy.
