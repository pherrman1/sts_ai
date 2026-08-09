# S3 obs-stable reuse — remove tracking overhead

Date: 2026-08-09 | Commit: current HEAD (ecebb0e + optimization)

## Semantic audit

`advanceRoot()` only inspects `root.edges` — immediate root children. The agent
loop checks `promotedChild->isObsStable()` on the immediate child of the root
edge matching the committed action. After promotion, the child becomes new root,
its children become new `root.edges`. **Only depth==2 nodes (immediate root
children from the current root) are ever promotion candidates.** Tracking at
all tree depths was unnecessary overhead.

## Change

One line in `BattleScumSearcher3::step()`:

```cpp
// Before:
if (g_reuseObsStable || g_reuseCarryDiag || g_s3UnionExpand)
    trackNodeObservation(*cur, state);

// After:
if (g_s3UnionExpand || g_reuseCarryDiag || (g_reuseObsStable && depth == 2))
    trackNodeObservation(*cur, state);
```

`STS_REUSE_OBS_STABLE` now tracks only at `depth==2`. Union-expand and
carry-diag retain full-depth tracking (experimental/diagnostic only, not in
deployed candidate). Added `g_obsHashCalls` counter to `writeCpuDiagRow`.

## Equivalence check (16 seeds: 100000–100007, 200000–200007)

| | Before optimization | After optimization |
|---|---|---|
| Block-1 G win% | 75% | 75% |
| Reuse decisions | same outcome | identical |
| Correctness failures | 0 | 0 |

## CPU comparison (16 seeds combined, ms/1000sims mean)

| | A fresh | G-old fresh | G-new fresh | G-old carried | G-new carried |
|---|---|---|---|---|---|
| ms/1000sims | 42.8 | 49.1 (+14.7%) | **42.4 (−0.9%)** | 47.7 | 40.2 |
| hash calls/sim | 0 | — | 1.2 | — | 1.2 |

**G-new fresh is now 0.9% BELOW A fresh — the 14.7% overhead is completely eliminated.**

Hash calls dropped from ~depth×nodes_visited per sim (e.g. ~12 for depth-12
tree) to ~1.2 per sim (one per root child visit, plus occasional second visits).

## Decision: MERGE OPTIMIZATION

The depth==2 tracking is provably sufficient for the obs-stable reuse
correctness condition. The 16-seed comparison confirms identical reuse
decisions, identical win rates, and complete elimination of the per-search
overhead tax. No behavior changes to the reuse algorithm.

## Files changed

- `include/sim/search/BattleScumSearcher3.h` — `g_obsHashCalls` extern
- `src/sim/search/BattleScumSearcher3.cpp` — depth==2 gate, `g_obsHashCalls` counter, CSV column
- `src/sim/search/ScumSearchAgent2.cpp` — reset `g_obsHashCalls` before each search

## ELI5

We found the search was doing expensive bookkeeping on every single node in
the tree, but the reuse check only needed it on the immediate children of the
root. We moved the bookkeeping to only those children. The search got 15%
faster — faster than the original fresh search — and the reuse decisions
stayed exactly the same.
