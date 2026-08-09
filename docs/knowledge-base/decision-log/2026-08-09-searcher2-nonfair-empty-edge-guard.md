# 2026-08-09 — Searcher2: non-fair empty-edge guard (defeat-guard leaves + soft rollout stop)

Date: 2026-08-09
Session/task: Fix the fair/non-fair empty-edge guard asymmetry in
`BattleScumSearcher2`. Fair mode filtered invalid edges and direct-evaluated
empty leaves; the non-fair path had no guard, so an empty edge list reached
`selectFirstActionForLeafNode` (`uniform_int_distribution(0,-1)`, UB/assert),
and `playoutRandom` asserted unconditionally on empty edges.

## Decisions

1. **`step()`: non-fair empty-edge guard mirrors the fair-mode pattern.**
   After `enumerateActionsForNode`, if `edges.empty() && !g_fairPlay`, record
   the node as a defeat (`outcome = 2`), count `leafDirectEval`, and return via
   `updateFromPlayout` without descending or rolling out. The defeat marking
   means later visits of the same node stay terminal (never re-expanded), which
   matches how an in-tree terminal would be treated; a plain early return
   without marking would re-run enumeration every visit.
   **Evidence**: `src/sim/search/BattleScumSearcher2.cpp::step`; commit aed89a6.

2. **`playoutRandom()`: replace `assert(false)` with a soft stop.**
   Empty edges in the non-fair rollout path set `stop = RolloutStop::NO_LEGAL_ACTION`
   and break, letting the leaf be evaluated directly — identical semantics to
   the fair-mode break. State diagnostics were added at the same site (commit
   42dbf13) so an actual trigger prints seed/state/task/hand/pick/turn to
   stderr instead of dying.
   **Evidence**: `BattleScumSearcher2.cpp::playoutRandom`; commit aed89a6 + 42dbf13.

## Rationale

- Both guards are defensive, not active: `PLAYER_NORMAL` always adds
  `END_TURN`, so deterministic enumeration currently always yields at least one
  legal action. A future enumerator change (new input state, changed card
  pools) could produce zero actions, and both searchers would otherwise hit
  undefined behavior instead of a soft, diagnosable stop.
- Soft-stop semantics preserve the existing rollout-usage invariant
  `simulations == terminalInsideTree + rolloutCalls + leafDirectEval`; the
  direct-eval counters already existed for fair mode.

## Alternatives considered

- Keep `assert(false)` / UB: rejected — a latent crash is exactly what the
  guard should remove, and the guard is unreachable today so an assert adds
  no diagnostic value beyond the stderr state dump.

## Evidence

- Regression test `scum_nonfair_empty_edges` added with the fix (commit
  4d954d2; `apps/test.cpp::testScumNonFairEmptyEdges`): drives an artificial
  zero-option `CARD_SELECT` (SECRET_WEAPON vs all-skill draw pile) and checks
  `playoutRandom` stops with `NO_LEGAL_ACTION` (empty action stack) and
  `step()` resolves all simulations as `leafDirectEval` with the node recorded
  as a defeat and zero rollout calls. Registered in CTest
  (`CMakeLists.txt::add_test`). Verified passing 2026-08-09 (15/15 ctest
  entries).
- KB: `docs/knowledge-base/architecture/combat-search.md` ("Rollout-usage
  diagnostics" section) updated to describe the non-fair guard.

## Status

Implemented, committed (aed89a6, 4d954d2, 42dbf13), and re-verified this
session: `./build/test scum_nonfair_empty_edges` PASS, full `ctest` 15/15
PASS.
