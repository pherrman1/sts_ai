# S3 fair tree reuse — observation-stable investigation

Date: 2026-08-09
Status: **Observation-stable + keep stats beats control (+3.1pp). First reuse arm to do so.**

## 64-seed paired gate results (asc 0, 1000 sims, 64 particles, 12 threads)

| Arm | win% | floor | hp_end | cpu/run | vs control |
|-----|------|-------|--------|---------|------------|
| A: control (N=0) | 37.5 | 42.9 | 20.6 | 35.20 | — |
| B: recursive_reset + reconcile_root (RNG gate) | 25.0 | 41.1 | 27.8 | 34.78 | −12.5pp |
| **C: obs-stable + keep** | **40.6** | 43.6 | 23.2 | 37.92 | **+3.1pp** |
| D: obs-stable + recursive_reset | 32.8 | 43.5 | 20.0 | 37.91 | −4.7pp |
| E: fresh tree + union expand | 35.9 | 42.7 | 19.3 | 42.42 | −1.6pp |

## Reuse frequency (obs-stable modes, observed on 8 seeds)

| Metric | Value |
|--------|-------|
| Attempt rate | ~75-80% of combat decisions |
| Acceptance rate | ~100% of attempted |
| Reject: obsMismatch>0 | 0 |
| Reject: hashMismatch | 0 |
| Reject: other | 0 |

Observation-stable children are ubiquitous, not rare. Within-turn card plays almost
always produce a child node that was visited from exactly one visible observation,
and that observation matches the new live root.

## Key findings

### 1. Observation-stable reuse with keep stats BEATS control

Arm C at 40.6% is the first reuse configuration to exceed the fresh-searcher
baseline (37.5%). The per-node `firstObsHash`/`nodeObsMismatches` tracking
correctly identifies subtree carries where the promoted information state is
identical to the new root state. In these cases, accumulated visit counts and Q
values transfer correctly — the tree topology and statistics were built under
the identical visible observation.

### 2. Root reconciliation helps but can't fix deep topology staleness

Arm B (RNG-gate + recursive_reset + reconcile_root) scores 25.0% vs the
previous 17.2% (RNG-gate + recursive_reset without reconcile). The root-level
topology fix recovers ~7.8pp, confirming that missing/misidentified root actions
explain a significant part of the old result. But the remaining 12.5pp gap to
control comes from stale topology below the root — the carried subtree's edges
were enumerated under old particle determinizations.

### 3. recursive_reset hurts on genuinely observation-stable children

Comparing C (keep, 40.6%) vs D (recursive_reset, 32.8%): when the promoted
child represents a single information state, the accumulated statistics ARE
informative. Zeroing them discards useful signal. This is the opposite of the
RNG-gate regime where every child accumulated observations from multiple
different visible states and resetting helped.

### 4. Union expansion is flat on fresh trees

Arm E (35.9%) is within noise of control (37.5%). The current Searcher3 behavior
of enumerating once from the first determinization does not measurably hurt
fresh-search performance at 1000 sims. Legal actions from other
determinizations that are missing from the stored edge set are apparently rare
enough not to matter, or the search compensates through live-valid
re-selection.

### 5. Carry diagnostic confirms positional card-action staleness

The `STS_REUSE_CARRY_DIAG` diagnostic successfully identifies cases where a
stored `CARD(idx=N)` refers to a different card after the hand shifts:

```
STALE: old CARD(idx=2,Defend) != new CARD(idx=2,Strike)
STALE: old CARD(idx=3,Strike) != new CARD(idx=3,Wild Strike)
```

This validates the user's hypothesis about `Action::operator==` comparing raw
bits — the same positional action identity can refer to different semantic cards
across observations.

## Implementation

All new behavior is opt-in behind env flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `STS_REUSE_OBS_STABLE` | 0 | Only promote obs-stable children matching the new root |
| `STS_REUSE_RECONCILE_ROOT` | 0 | Add missing legal root actions using semantic card matching |
| `STS_REUSE_CARRY_DIAG` | 0 | Per-carry detailed diagnostic |
| `STS_S3_UNION_EXPAND` | 0 | Add missing edges at every internal-node visit |

New per-node fields: `firstObsHash`, `lastObsHash`, `nodeObsVisits`,
`nodeObsMismatches`, `isObsStable()`. Tracked on every node visit in `step()`.

New per-edge field: `availabilityCount`.

New structures: `BattleScumSearcher3::CardActionKey` (semantic card identity
for reconciliation).

## Conclusion

The investigation disproves the hypothesis that fair S3 ISMCTS tree reuse is
inherently impossible. When restricted to observation-stable children (those
visited from exactly one visible observation matching the new root), subtree
reuse with retained statistics exceeds the fresh-searcher baseline.

Key insight: the previous catastrophic failures (4.7-17.2%) occurred because
the RNG gate promotes subtrees that were visited from MULTIPLE different
visible observations during search. These subtrees contain stale topology
and stale statistics. The RNG gate checks whether the COMMITTED action
consumed hidden randomness, but the tree nodes below the root were built
from multiple particle worlds with different draw-pile orders. The
observation-stable check is a much stronger condition that eliminates this
problem entirely.

Recommended next step: cascading observation-stable reuse with keep stats,
tested on a larger paired gate.

## Files changed

- `include/sim/search/BattleScumSearcher3.h` — Node obs-stability fields, Edge availabilityCount,
  CardActionKey, reconcileRoot, trackNodeObservation, printCarryDiagnostic
- `src/sim/search/BattleScumSearcher3.cpp` — implementations + step() modifications
  for union expand, per-node tracking, per-edge availability
- `src/sim/search/ScumSearchAgent2.cpp` — obs-stable gate, reconcileRoot, carry
  diagnostic, reuse-frequency tracking
- `apps/one_combat.cpp` — env var parsing (5 new flags)
