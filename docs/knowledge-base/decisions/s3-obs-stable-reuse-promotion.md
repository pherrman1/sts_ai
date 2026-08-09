# S3 obs-stable reuse — promotion to default

Date: 2026-08-09 | Status: **PROMOTED TO DEFAULT**

## Default configuration

The fair Searcher3 path (`STS_FAIR=1 STS_SEARCHER3=1`) now defaults to:

```text
g_reuseObsStable   = true   (only promote obs-stable root children, tracking at depth==2)
g_reuseMaxSearches = 1      (one carried search per fresh tree)
g_reuseStatsMode   = 0      (keep inherited subtree statistics)
g_reuseAlwaysQ     = false  (no forced Q exploitation)
g_reuseReconcileRoot = false (experimental, not enabled)
g_s3UnionExpand    = false  (experimental, not enabled)
```

## Fresh-tree opt-out

```bash
STS_REUSE_MAX_SEARCHES=0
```

restores fresh-searcher-every-decision behavior. Even with this flag,
`advanceRoot` still promotes the subtree — but the searcher is rebuilt before
the next search, so the promoted tree is never searched.

## Evidence summary

256 independent confirmation seeds (100000–100127, 200000–200127):

| | Fresh | Obs-stable N=1 | Delta |
|---|---|---|---|
| Wins | 91 (35.5%) | 103 (40.2%) | +4.7pp |
| Discordants | 34 A-only | 46 G-only | +12 net |

Both confirmation blocks positive (+7.0pp, +2.3pp). Development block also
positive (+6.3pp on 0–63, not included in formal statistics).

McNemar exact p = 0.2185 (not statistically significant at conventional levels).
Documented as "consistent positive evidence" rather than "proven superiority."

## CPU optimization

Original obs-stable tracking (`trackNodeObservation`) ran at every visited
tree node, computing `CombatObservation::fromBattleContext(state).visibleHash()`.
This added ~15% per-simulation overhead.

Semantic audit: only `root.edges` (depth==2) can be promoted via `advanceRoot`.
Restricted tracking to `(g_reuseObsStable && depth == 2)`.

Result on 16-seed diagnostic: G fresh per-1000-sims went from +14.7% vs A
to −0.9% vs A. 106% of overhead eliminated.

## Historical failures (retained as lessons)

| Approach | Result | Why |
|----------|--------|-----|
| Raw RNG-gate reuse | 4.7% | Multi-observation tree promotes stale topology |
| always_Q | 4.7% | Forces exploitation before winning line found |
| recursive_reset on RNG-gate | 17.2% | Helps but topology still stale |
| Cascade (N=-1) | 40.6% | Worse than N=1 (43.8%) |
| Full-depth obs tracking | +15% overhead | Unnecessary — fixed to depth==2 |
| **obs-stable + keep + N=1** | **40.2%** | **Winner** |

## Smoke test

- Default invocation: produces reuse, maxGen=2, carry acceptance ~75-80%
- STS_REUSE_MAX_SEARCHES=0: no carried searches executed
- Explicit G flags: identical to default
- ctest: 15/15 pass
- Zero correctness failures

## Files changed

- `include/sim/search/BattleScumSearcher3.h` — removed g_obsHashCalls extern
- `src/sim/search/BattleScumSearcher3.cpp` — defaults changed, depth==2 gate, removed g_obsHashCalls
- `src/sim/search/ScumSearchAgent2.cpp` — removed g_obsHashCalls reset

## ELI5

Tree reuse now works and is the default. When the search finds a good move and
the next game state matches what it expected, it keeps its work instead of
throwing it away. This wins about 5 more games per 100. The old speed problem
was unnecessary bookkeeping that we removed — now it's as fast as the original.
If you want the old behavior back, set one flag and it's gone.
