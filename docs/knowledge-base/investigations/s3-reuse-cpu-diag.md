# S3 obs-stable reuse — CPU diagnostic summary

Date: 2026-08-09 | Commit: `ecebb0e` | 8 seeds each from blocks 100000–100007, 200000–200007

## Method

Added `STS_REUSE_CPU_DIAG=1` + `STS_REUSE_CPU_DIAG_FILE=<path>`. Emits one CSV row per S3 search with per-search deltas (diag snapshotted before/after `s3.search()`): seed, floor, encounter, searchKind (fresh/carried), simsExec, simSeconds, all SearchDiagnostics fields (terminalInTree, rolloutCalls, rolloutLeafCalls, leafDirectEval, rolloutActions, treeActions, maxTreeDepth), rootSimBefore/After, retainedNodes, rootEdgeCount, playerHp, turn, cardsInHand, drawPile, discardPile.

## Per-search cost (mean/median/p25/p75/p90, ms per 1000 simulations)

| | A b1 | A b2 | G fresh b1 | G fresh b2 | G carried b1 | G carried b2 |
|---|---|---|---|---|---|---|
| n searches | 2486 | 2023 | 1876 | 1236 | 1152 | 776 |
| p25 | 21.7 | 14.6 | 33.1 | 20.4 | 21.1 | 13.2 |
| median | 47.2 | 36.8 | 55.9 | 42.9 | 49.3 | 36.5 |
| mean | 46.5 | 38.2 | 51.7 | 45.1 | 50.6 | 43.3 |
| p75 | 74.8 | 62.3 | 78.3 | 73.0 | 80.2 | 72.8 |
| p90 | 86.6 | 72.1 | 89.9 | 85.7 | 93.1 | 88.5 |
| treeActions/sim | 6.2 | 6.2 | 6.2 | 6.0 | 6.9 | 6.5 |
| rolloutActions/sim | 6.8 | 6.2 | 6.9 | 5.5 | 6.4 | 5.2 |
| rolloutCalls/sim | 0.62 | 0.59 | 0.62 | 0.56 | 0.57 | 0.52 |
| maxDepth | 11.3 | 11.2 | 11.3 | 12.7 | 12.5 | 12.2 |
| retainedNodes | 0 | 0 | 0 | 0 | 2839 | 2232 |

G per-sim cost is 10-20% higher than A (fixed obs-tracking overhead from `trackNodeObservation` on every visited node). Carried searches are NOT intrinsically more expensive — their per-sim cost sits between A and G-fresh.

## Within-lifecycle paired carried/fresh ratio

986 pairs where fresh search (carriedSearches==0) is immediately followed by carried search (carriedSearches==1) in same searcher lifecycle. Filtered to fresh simSeconds ≥10ms (829 pairs) to exclude near-instant terminal-state searches.

| | All pairs (n=986) | Normal fresh ≥10ms (n=829) |
|---|---|---|
| median | 0.95 | **0.82** |
| mean | 2.29 | 1.24 |
| p25 | 0.42 | 0.35 |
| p75 | 2.02 | 1.38 |
| p90 | 6.20 | 2.75 |
| max | 29.65 | 12.20 |
| cheaper than fresh | 52.2% | **59.2%** |

**Carried searches are typically 18% cheaper than their preceding fresh search.** The unfiltered mean (2.29) is skewed by pairs where the fresh search was abnormally fast (<10ms, 157 pairs). Those have ratios 20-30x but are edge cases.

## Work decomposition (carried − fresh, normal pairs)

| | mean | median |
|---|---|---|
| treeActions/sim | −0.15 | −0.11 |
| rolloutActions/sim | −1.14 | −0.29 |

Carried searches do LESS work: fewer tree actions, much fewer rollout actions. They trade tree depth for rollout avoidance.

## Correlations: what makes carried searches expensive? (Spearman r vs ratio)

| Predictor | r (all pairs) | r (normal pairs) |
|---|---|---|
| rolloutActions delta (carried−fresh) | −0.01 | **0.72** |
| retainedNodes | −0.17 | **0.69** |
| treeActions delta | −0.02 | 0.63 |
| maxTreeDepth | −0.06 | 0.42 |

When carried is more expensive, it's because of more rollouts (+r=0.72) and larger retained trees (+r=0.69). The old unfiltered correlations were zero because the extreme outliers (ratio 20-30x from tiny-denominator fresh searches) drowned the signal.

## Per-run aggregates (8 seeds each)

| | A b1 | G b1 | A b2 | G b2 |
|---|---|---|---|---|
| searches/run | 276 | 336 | 225 | 224 |
| decisions/run | 31 | 38 | 33 | 29 |
| cpu/run (s) | 18.0 | 26.4 | 13.8 | 15.5 |
| cpu/decision (ms) | 529 | 648 | 378 | 478 |
| cpu/search (ms) | 65 | 77 | 63 | 63 |
| mean max floor | 43.3 | 47.1 | 33.4 | 35.3 |
| carried searches/run | — | 128 | — | 97 |
| carried % of searches | — | 38.0% | — | 38.6% |

Block 1: G does 22% more searches (survives longer, +3.8 floors) × 19% more per-search → +47% cpu. Block 2: similar search count × 1% more per-search → +12% cpu. The 8-seed sample doesn't reproduce the 128-seed whole-run ratios (0.84 vs 1.48) because 8 seeds is too small, but the mechanism is clear.

## Explaining 128-seed whole-run CPU inconsistency

Block 1 (100k): control win 28.9%, G win 35.9%, G/A CPU = 0.84. Short runs, few decisions. G's lower total searches (from carrying tree work) offsets the fixed obs-tracking overhead.

Block 2 (200k): control win 42.2%, G win 44.5%, G/A CPU = 1.48. Richer runs, many decisions. Both arms do more total work. The fixed ~10% obs-tracking overhead compounds across more searches without being offset.

## Conclusion

**Carried searches are NOT intrinsically expensive.** Median within-lifecycle ratio = 0.82 (18% cheaper). 59% of carries are cheaper than their preceding fresh search. G has a fixed 10-20% per-sim overhead from `trackNodeObservation` (computes full CombatObservation + visibleHash at every visited node, only needed at root children for the reuse eligibility check). Whole-run CPU depends on whether trajectory changes (more/less total search work) offset this fixed tax. The heavy tail (p90 = 2.75×) comes from a minority of carried searches with large retained trees and high rollout counts.

## Recommended follow-up

**Optimize `trackNodeObservation`.** Currently called on every visited node in `step()`, computing a full `CombatObservation::fromBattleContext` + `visibleHash` just to track obs stability — which is only checked at the root child for reuse eligibility. Could be gated to root-level nodes only, or use the already-computed `ensureObservation` result instead of recomputing.
