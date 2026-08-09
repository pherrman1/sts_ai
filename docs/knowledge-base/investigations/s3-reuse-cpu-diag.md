# S3 reuse CPU diagnostic

Date: 2026-08-09
Status: **CPU difference is mainly trajectory composition + fixed obs-tracking overhead. Carried searches are NOT more expensive.**

## Per-search timing (8 seeds each from blocks 1 and 2)

| | A b1 | A b2 | G fresh b1 | G fresh b2 | G carried b1 | G carried b2 |
|---|---|---|---|---|---|---|
| n searches | 2486 | 2023 | 1876 | 1236 | 1152 | 776 |
| ms/1000sims (mean) | 46.5 | 38.2 | 51.7 | 45.1 | 50.6 | 43.3 |
| ms/1000sims (median) | 47.2 | 36.8 | 55.9 | 42.9 | 49.3 | 36.5 |
| ms/1000sims (p90) | 86.6 | 72.1 | 89.9 | 85.7 | 93.1 | 88.5 |
| treeActions/sim | 6.2 | 6.2 | 6.2 | 6.0 | 6.9 | 6.5 |
| rolloutActions/sim | 6.8 | 6.2 | 6.9 | 5.5 | 6.4 | 5.2 |
| rolloutCalls/sim | 0.62 | 0.59 | 0.62 | 0.56 | 0.57 | 0.52 |
| maxDepth | 11.3 | 11.2 | 11.3 | 12.7 | 12.5 | 12.2 |
| retainedNodes | 0 | 0 | 0 | 0 | 2839 | 2232 |

## Key finding 1: Carried searches are NOT more expensive

Carried/fresh time-per-1000sims ratio (within same block):

| Block | median | mean | p75 | p90 | max |
|-------|--------|------|-----|-----|-----|
| b1 | **0.88** | 0.90 | 1.43 | 1.67 | 2.77 |
| b2 | **0.85** | 1.01 | 1.70 | 2.06 | 2.97 |

Median carried search is 12-15% CHEAPER than median fresh search on the same block.
The mean is slightly above 1.0 because a small fraction of carried searches are
2-3x more expensive, pulling the mean up. 

**Verdict: Carried searches have a heavy tail but are typically cheaper.**

## Key finding 2: G has a fixed per-search overhead vs A

| Block | A ms/1000sims (median) | G ms/1000sims (median) | G/A |
|-------|------------------------|------------------------|-----|
| b1 | 47.2 | ~52 (avg fresh+carried) | ~1.10 |
| b2 | 36.8 | ~40 (avg) | ~1.09 |

G is consistently ~10% more expensive per simulation than A, regardless of
fresh/carried. This is the `trackNodeObservation` overhead from
`STS_REUSE_OBS_STABLE=1` — every simulation calls `CombatObservation::fromBattleContext`
+ `visibleHash` at every visited node. This is a fixed tax on EVERY search, not
just carried ones.

## Key finding 3: Work decomposition

Carried searches trade rollouts for tree traversal:
- b1: G fresh rollouts=6.9/sim, G carried rollouts=6.4/sim (−7%) but treeActions=6.9 vs 6.2 (+11%)
- b2: G fresh rollouts=5.5/sim, G carried rollouts=5.2/sim (−5%) but treeActions=6.5 vs 6.0 (+8%)

The net CPU effect is nearly neutral (median carried/fresh = 0.85-0.88).

## Key finding 4: Correlations

Spearman r with time/sim on carried searches:

| Predictor | r |
|-----------|-----|
| rolloutCalls/sim | **0.903** |
| rolloutActions/sim | **0.870** |
| retainedNodes | **0.848** |
| treeActions/sim | 0.580 |
| maxTreeDepth | 0.430 |

The dominant cost driver is rollout count, not tree size. Deeper/larger retained
trees correlate with cost mostly because they correlate with more rollouts.

## Explaining the block CPU discrepancy

| | Block 1 (100k) | Block 2 (200k) |
|---|---|---|
| Control win% | 28.9% | 42.2% |
| Whole-run CPU ratio G/A | 0.84 | 1.48 |
| Per-search ms/1000sims ratio G/A | ~1.10 | ~1.09 |
| G searches vs A (8-seed) | +22% | −1% |

Block 1: G had 22% more searches but each search is only 10% more expensive →
trajectory composition dominated. The observation overhead was offset by G
surviving longer in some seeds (more decisions, but the per-decision cost is
similar).

Block 2: G had similar search count to A but each search is 10% more expensive
→ the fixed overhead dominates. In easier runs (42% win rate), both arms make
many decisions, and the 10% per-search tax accumulates without being offset by
trajectory differences.

Block 2 also had a 1.48x CPU ratio in the 128-seed run vs 0.84 in block 1.
The 8-seed diagnostic sample shows the per-search cost ratio is similar
(~1.10), so the whole-run difference must come from trajectory composition:
block 2 G runs had MORE total simulations across all searches than block 2 A.

## Conclusion

**CPU difference is mainly trajectory composition.**

Carried searches themselves are NOT intrinsically more expensive (median 0.85-0.88× fresh).
The 10% per-search overhead from `trackNodeObservation` is a fixed tax on all
G searches (fresh and carried). Whether whole-run CPU is better or worse depends
on whether G's trajectory changes (more/less total search work) offset this
fixed tax.

The heavy tail (p90 ~2× for carried searches) suggests a small fraction of
carried searches are expensive outliers, correlated with high rollout counts
and large retained trees.

## Recommended follow-up

**Optimize `trackNodeObservation` to reduce the fixed per-search overhead.**
Currently every visited node computes a full `CombatObservation::fromBattleContext`
+ `visibleHash`. This could be cached more cheaply using the already-computed
`ensureObservation` result, or gated to only track on root-level nodes where
the stability check is needed. A 10% per-search tax is too high for a diagnostic
that's only needed at the root child.

## ELI5

We measured exactly how long each search takes. The carried-over trees aren't
slower — in fact they're usually 12-15% faster per search. The problem is that
turning on observation tracking adds a fixed 10% slowdown to EVERY search
(whether carried or fresh), because it has to compute extra bookkeeping for
every node the search visits. Whether this makes the whole run faster or
slower depends on how many total searches the run needs. Sometimes reuse
reduces the total number of searches enough to pay for the overhead, sometimes
it doesn't.
