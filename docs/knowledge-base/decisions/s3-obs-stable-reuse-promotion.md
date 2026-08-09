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

Result on 16-seed diagnostic:

| | A fresh | G-old fresh | G-new fresh |
|---|---|---|---|
| ms/1000sims | 42.8 | 49.1 (+14.7%) | 42.4 (−0.9%) |

The measured ~14.7% fresh-search overhead was fully eliminated in the
diagnostic sample; optimized G was ~0.9% faster than baseline A in that
comparison.

## Historical failures (retained as lessons)

| Mechanism | Conclusion |
|-----------|------------|
| RNG gate alone | Insufficient; RNG unchanged does not imply observation/topology compatibility |
| keep + always_Q | Catastrophic; forcing inherited Q exploitation too early was the largest identified failure |
| keep without always_Q | Recovered strongly (4.7% → 39.1%) |
| recursive_reset | Removes useful inherited statistics and still cannot repair stale topology |
| intended N=1 before counter fix | Actually cascaded; results cannot be interpreted as single-use |
| true cascade | Worse than true N=1 in corrected development gate |
| obs-stable + keep + true N=1 | Selected configuration |
| full-depth obs tracking | Semantically unnecessary for reuse and ~15% slower in diagnostic |
| depth==2 obs tracking | Equivalent reuse decisions with measured overhead removed |

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

The search now keeps useful tree work when the next visible game state matches
what the search expected, instead of always starting from zero.

Across 256 new confirmation games, this version won about 4.7 percentage
points more often than fresh search, and both test blocks favored reuse.
That is a consistent positive signal, although the experiment was not large
enough to prove the improvement statistically.

The original speed penalty turned out to be unnecessary bookkeeping.
Restricting observation tracking to the only nodes that can actually be
reused removed that measured overhead without changing reuse decisions.

The optimized one-step reuse is now the default, while
`STS_REUSE_MAX_SEARCHES=0` restores fresh-tree behavior.
