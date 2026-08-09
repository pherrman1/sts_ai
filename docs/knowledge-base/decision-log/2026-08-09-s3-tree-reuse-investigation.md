# S3 fair tree reuse investigation

Date: 2026-08-09
Context: Investigation of fair-Searcher3 tree reuse (STS_REUSE_MAX_SEARCHES,
STS_REUSE_STATS_MODE, STS_REUSE_ALWAYS_Q, diagnostics, RNG-gate hardening).

## Decision

Implemented the full reuse-control stack (diagnostic, not deployed):

- `STS_REUSE_MAX_SEARCHES=N`: N=0 fresh every decision (default), N=1 promoted
  tree searched once, N=-1 unlimited cascading. Default 0 preserves current
  behaviour.
- `STS_REUSE_STATS_MODE`: `keep` (default) preserves subtree statistics;
  `recursive_reset` zeros simulationCount / evaluationSum / dist on every
  retained node.
- `STS_REUSE_ALWAYS_Q`: on carried trees PUCT uses Q from sim 1 directly,
  no gate on `bestActionSequence`.
- Diagnostics: `STS_REUSE_DIAG=1` prints per-search obsMismatch,
  generation/depth, retained nodes, edge particle-availability.
- RNG gate hardened to all 6 streams (was only shuffle + card-random).

All five 64-seed gates falsified reuse as a performance lever:

| Arm | win% | floor | hp_end |
|-----|------|-------|--------|
| control (N=0) | 37.5 | 42.9 | 20.6 |
| one-use + keep + always-Q | 4.7 | 30.5 | 12.7 |
| cascade + keep + always-Q | 4.7 | 30.5 | 12.7 |
| one-use + recursive_reset | 17.2 | 37.8 | 37.8 |
| cascade + recursive_reset | 17.2 | 37.8 | 37.8 |

No arm promoted; the control (N=0, current behaviour) remains default.

## Rationale

Two failure modes identified from single-seed diagnostics (STS_REUSE_DIAG=1):

1. **Tree topology staleness (dominant).** On carried trees, edgeAvailability
   collapses from 6–13 root edges on fresh searchers to 2–4 on carried trees.
   The tree's edge structure was enumerated under old particle
   determinizations; actions that were not legal in any old particle are
   missing as edges, even though they are legal in the new state. This is
   **Inference**: the carried tree topology is conditioned on the previous
   draw-pile order and becomes increasingly wrong as the real state advances.

2. **Statistics staleness (keep mode).** obsMismatch on carried trees is
   3,000–22,000 per search (vs. ~1,000–2,500 on fresh searchers). Almost
   every node visited in a carried tree has a stale `CombatObservation` from
   a different determinization. In keep mode, PUCT exploits these stale Q
   values and the searcher collapses to ~4.7% win.

`recursive_reset` partially addresses (2) by zeroing the stale statistics,
bringing win to 17.2%, but the fundamental topology staleness (1) limits
further recovery. The tree structure itself is wrong for the new state.

## Alternatives considered

- **Tree-repair on carry**: re-enumerate edges from the live state after
  advanceRoot, matching against stored obs-hash → rejected as would
  require a full recomputation of every edge in the carried subtree.
- **Only carry root edges, discard children**: would preserve the
  budget-allocation signal from the old search without stale topology →
  not implemented, may be worth investigating.
- **Stay with N=0 (current default)**: the evidence is clear — tree reuse
  as implemented hurts the ISMCTS search. The fresh-searcher regime is
  correct for ISMCTS where the particle distribution shifts between
  decisions.

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp` — `advanceRoot`, `recursiveResetStats`,
  `computeEdgeAvailability`, `printReuseDiagnostics`, PUCT always-Q gate.
- `src/sim/search/ScumSearchAgent2.cpp` — fair S3 loop with strengthened
  RNG gate (all 6 streams) + reuse control.
- `apps/one_combat.cpp` — env-var parsing for STS_REUSE_*.
- 64-seed paired gates at ascension 0, 1000 sims, 64 particles, 12 threads.

## Status

Investigative implementation complete. All arm results falsified —
no default-behaviour change, no deployment, no promotion.
Diagnostics and reuse control remain in the tree as opt-in tooling.

## Follow-up

- Open question: could carrying only root-edge visit counts (without the
  full subtree) transfer budget-allocation signal without the topology cost?
- The strengthened RNG gate (all 6 streams) is a correctness improvement
  independent of reuse — it is active in all reuse modes, including N=0
  (current default).
