# ADR-0014: Enable live OOC visit-lock stopping without complete abort support

- Status: accepted
- Date: 2026-09-15

## Context

A strict root visit lead greater than every challenger plus all remaining
simulations fixes the visit-selected winner if search completes. The live
provider can still abort on unsupported combat or continuation exhaustion.
The full-budget observer measured substantial remaining work after locks;
those measurements do not prove a non-aborting provider contract.

## Decision

Enable strict visit-lock stopping by default within opt-in live OOC MCTS,
as explicitly requested despite remaining Smoke support exclusions.
`OocMctsConfig::allowUnqualifiedRootStop` expresses this policy separately
from `searchGuaranteedNonAborting()`, which remains false for the live provider.
`STS_OOC_MCTS_EARLY_STOP=0` restores the original guarantee requirement.
Mean-Q selection and full-budget root-lock observation suppress stopping.
Unqualified singletons complete their first simulation before stopping.

## Alternatives and consequences

Waiting for complete abort support preserves full-budget fallback behavior but
forgoes the available savings. The chosen policy can skip a later abort and
execute a locked action where full-budget search would fall back. This is a
policy change, not support qualification or an approximation to the visit lock.
Aborts encountered before a lock still discard the search and fall back.
OOC MCTS itself remains opt-in; model support and real combat are unchanged.

## Evidence and affected files

- `include/sim/search/OocMctsPlanner.h` and `src/sim/search/OocMctsPlanner.cpp`:
  explicit override, strict predicate and observer/mean-Q precedence.
- `apps/one_combat/ooc_mcts_adapter.cpp`: live default and rollback control.
- `apps/ooc_mcts_test.cpp`: 52/100 exact winner lock and deliberate skipped
  seventh-simulation abort after a singleton's first-simulation lock.
- [Full-budget observation](../docs/experiments/evidence/ooc_root_lock_observation_2026-09-15.md).
- [Enabled-stop validation](../docs/experiments/evidence/ooc_early_stop_enabled_2026-09-15.md).
