# S3 fair tree reuse — investigation summary

Date: 2026-08-09
Status: All reuse arms falsified at 64-seed gate. Diagnostics in tree as opt-in tooling.

## What was done

Added opt-in tree reuse control to `BattleScumSearcher3`'s fair ISMCTS path
(particle-belief, 64 particles). The existing code had `advanceRoot` wired up
but always force-rebuilt the searcher (`searcherValid=false`) — no tree was
ever actually carried across decisions. The investigation adds the machinery to
carry trees and measures what breaks.

Four env vars added (defaults preserve current behaviour):

- `STS_REUSE_MAX_SEARCHES=N` — 0=never reuse (default), 1=search promoted tree
  exactly once then rebuild, -1=unlimited cascading
- `STS_REUSE_STATS_MODE=keep|recursive_reset` — `recursive_reset` zeros
  `simulationCount`, `evaluationSum`, `dist.{n,loQ05,loQ20}` on every retained
  node
- `STS_REUSE_ALWAYS_Q=0|1` — on carried trees, PUCT exploits Q from sim 1
  without gating on `bestActionSequence`
- `STS_REUSE_DIAG=0|1` — prints per-search diagnostics: generation, tree depth,
  retained node count, obs mismatch count, parent/child invariant violations,
  per-edge particle-world availability

RNG gate hardened: was checking only `shuffleRng.counter` + `cardRandomRng.counter`;
now checks all 6 combat RNG streams (adds `aiRng`, `miscRng`, `monsterHpRng`,
`potionRng`). Active in all modes.

## 64-seed paired gate (asc 0, 1000 sims/decision, 64 particles, 12 threads)

| Arm | win% | floor | hp_end | cpu/run |
|-----|------|-------|--------|---------|
| control (N=0) | 37.5 | 42.9 | 20.6 | 31.66 |
| one-use + keep + always-Q | 4.7 | 30.5 | 12.7 | 22.45 |
| cascade + keep + always-Q | 4.7 | 30.5 | 12.7 | 20.03 |
| one-use + recursive_reset | 17.2 | 37.8 | 37.8 | 25.49 |
| cascade + recursive_reset | 17.2 | 37.8 | 37.8 | 27.84 |

Control matches documented baseline (37.5% §124).

## Single-seed diagnostic trace (cascade + keep + always-Q, seed 0)

Fresh searchers: `obsMismatch` ~1,000-2,500 per 1000-sim search (normal — each
determinization sees different visible state from different particle draws).

Carried trees (gen≥1): `obsMismatch` 3,000-22,000. Edge availability collapses
from 6-13 root edges on fresh to 2-4 on carried. Cascading to gen=3-4 observed
when RNG gate passes for consecutive within-turn plays.

## Failure mode analysis

Two mechanisms, one unfixable at this level:

### 1. Tree topology staleness (dominant, unfixable without re-enumeration)

In ISMCTS, each node's edges are enumerated (`enumerateActionsForNode`) the
first time that node is expanded during a simulation. At that moment the
`BattleContext` copy carries a specific particle's determinization — a
particular draw-pile order, monster intents, potion contents, etc. Actions that
are illegal in that determinization do NOT become edges. Even with
`STS_LIVE_VALID` (which re-selects among stored edges valid in the current
determinization), missing edges stay missing.

After the agent commits an action AND the real draw pile changes (cards drawn,
shuffled, exhausted), the carried tree's topology reflects the OLD particle
space. The new searcher's particle belief has been re-weighted by the observed
draw, but the tree still only has edges from the old particles.

Evidence: `edgeAvailability` drops from `[64,64,64,64,64,64]` (all 64 particles
find every root edge valid) to `[64,64,64]` (only 3 edges exist, and they're
valid in only some particles). A fresh searcher would enumerate 6 edges.

### 2. Statistics staleness (partially addressable by recursive_reset)

In `keep` mode, accumulated `evaluationSum`/`simulationCount`/`dist` from old
determinizations feed into PUCT's Q term. Since the old determinizations had
different draw-pile visibility, the Q values are misleading. `always_Q` makes
it worse by exploiting these stale values from sim 1.

`recursive_reset` zeroes all statistics on carry, reducing the problem to
topology-only. This recovers from 4.7% to 17.2% but still loses 20pp to control
because the topology itself is wrong.

### Why recursive_reset can't close the gap

Consider: a fresh searcher enumerates 6 root edges. After carry, the tree has
only 3. The missing 3 actions may include the correct play. Even with zero
statistics, PUCT can only select among the 3 present edges — exploration can
expand them deeper but never creates the missing root edges (expansion only
happens at leaves, never at the root of a carried tree).

## What HELPS but isn't enough

- `recursive_reset`: recovers 12.5pp of the 32.8pp gap.
- Neither `one-use` nor `cascade` matters — both hit the same topology wall
  on the very first reuse.
- `always_Q` is actively harmful in `keep` mode (4.7% vs 17.2% without it,
  though the without-it config wasn't gated).

## Open questions

1. **Root-edge-only carry:** Could we carry only root-edge `simulationCount`
   values (no subtree) as a budget-allocation prior for the fresh searcher?
   This avoids topology staleness while transferring "which actions were
   promising" signal.

2. **Re-enumerate on carry:** After `advanceRoot`, re-run `enumerateActionsForNode`
   on the live root state and match new edges against carried subtree edges by
   action identity. Add missing edges. This would fix topology but requires the
   subtree structure to remain valid under the new edge set.

3. **Is there any scenario where topology doesn't change?** Within a turn,
   before any draw or shuffle, the draw pile is unchanged. The RNG gate captures
   this. But even then: the particle belief has been updated by the agent with
   the real observed card, which shifts which particle worlds contribute. The
   tree topology reflects the pre-observation belief distribution.

## Implementation locations

- `src/sim/search/BattleScumSearcher3.{h,cpp}` — reuse counters, stats reset,
  PUCT always-Q, `computeEdgeAvailability`, `printReuseDiagnostics`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` — fair S3 loop with
  reuse control + hardened RNG gate
- `apps/one_combat.cpp` — env var parsing (~line 9904)
- `docs/knowledge-base/decision-log/2026-08-09-s3-tree-reuse-investigation.md`
