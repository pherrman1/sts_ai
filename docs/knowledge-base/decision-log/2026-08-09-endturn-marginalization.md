# 2026-08-09 — S3 END_TURN marginalization prototype

Date: 2026-08-09
Session/task: Prototype local outcome marginalization for END_TURN
transitions in Searcher3 and test whether bucketed expectation improves
decision quality per unit compute. Follows the outcome-bucket and
bucket-value diagnostics which showed strong outcome redundancy and
value homogeneity.

## Decision

**STOP — marginalization adds ~56% search CPU with no clear quality benefit at equal CPU.**

The prototype (`STS_S3_ENDTURN_MARGINALIZE=1`) works correctly — at eligible
leaf-expansion END_TURN boundaries (draw pile ≤8, no reshuffle), it generates
16 particles, buckets by visibleHash (~3-7 unique outcomes), evaluates one
representative per bucket, and backpropagates the weighted expectation. But
the extra evaluations cost more than the variance reduction saves.

## Audit findings (Section 0)

### A. Row-count semantics (corrected)

The 31,317 CSV rows in the bucket-value diagnostic include **thread
duplicates**. The dedup set (`t_bvdSeen`) is per-thread, so different threads
independently measure the same (preState, END_TURN) pair. Each thread writes
its own bucket rows for the same transition.

- **31,317** = total CSV rows (one per visibleHash bucket per thread
  invocation), including thread duplicates
- **~2,600** = estimated unique (transition, bucket) pairs after cross-thread
  dedup
- **113** = unique parent transition identities (seed, floor, encounter,
  turn, decIdx) — this figure is correct
- Transition-level stats (withinVar, nBuckets) vary between threads for the
  same parent and should NOT be cross-thread averaged

The per-bucket statistics (std, mean) are robust since they're computed from
multiple members within a single invocation. The homogeneity conclusion
(near-zero within-bucket std for 99% of buckets) remains valid.

### B. Lethal variance (explained)

The 302 high-variance buckets (std > 5, 0.96% of rows) show bimodal
{100, 75} distributions. **This is rollout noise, not hidden-state variance.**
All members of a bucket share the same `visibleHash` (same hand, same
monsters), so the post-END_TURN lethal status is IDENTICAL across members.
The value difference comes from the noisy rollout estimator: different
rollout runs from the same post-state sometimes find the lethal play and
sometimes don't, due to random action selection. Bucketed evaluation with
better rollout averaging eliminates this noise — the visible observation IS
value-deterministic.

## Prototype implementation

### Eligibility

At leaf-expansion END_TURN boundaries in `step()`:
- Action is `ActionType::END_TURN`
- `drawPile.size() <= g_s3EndTurnMarginalizeMaxPile` (default 8)
- No reshuffle required (draw pile not empty or discard empty)
- State is non-terminal (`UNDECIDED`)

| Metric | Value (2 seeds @1000 sims) |
|--------|---------------------------|
| Eligible END_TURN leaves | ~600/search |
| Marginalized | ~500/search (75-80% of eligible) |
| Ineligible (large pile/reshuffle) | ~100/search |
| Particles per event | 16 |
| Mean unique buckets | 3-7 |
| Mean bucket continuation evals | 3-7 |

### Shadow comparison

A 1% diagnostic sample computes both ordinary (1-particle) and marginal
(16-particle bucketed) evaluations at the same leaf:

| Metric | Value |
|--------|-------|
| Shadow comparisons | ~8/search |
| Mean ordinary eval | ~102.4 |
| Mean marginal eval | ~103.6 |
| Mean difference | ~1.2 |

The marginal estimate is very close to the ordinary estimate — consistent
with the bucket-value homogeneity finding (same visible outcome → same value).

## Gameplay smoke test (8 seeds, A0, fair S3, 64p, N=1 reuse)

### Equal simulations

| Arm | Sims | Win% | Floor | HP | CPU/run |
|-----|------|------|-------|----|---------|
| A: control | 1000 | 25.0% | 44.1 | 20.6 | 23.49s |
| B: marginalized | 1000 | 25.0% | 44.1 | 7.9 | 36.78s |
| **Δ** | 0 | 0pp | 0 | −12.7 | **+56%** |

### Equal CPU (B budget reduced to match A)

| Arm | Sims | Win% | Floor | HP | CPU/run |
|-----|------|------|-------|----|---------|
| A: control | 1000 | 25.0% | 44.1 | 20.6 | 23.49s |
| B: marginalized | 550 | 12.5% | 47.5 | 13.0 | 24.54s |

8 seeds is too noisy for win-rate conclusions (±1 flip = 12.5pp). Floor and
HP show no consistent advantage.

## Why the CPU cost dominates

The baseline MCTS evaluates **one** continuation per END_TURN (one particle →
one rollout). Marginalization evaluates **3–7** continuations (one per unique
bucket), each with its own multi-rollout and leaf blend. The ~3-7× increase
in evaluation work per END_TURN leaf outweighs the variance reduction benefit,
because:

1. The baseline's single-particle estimate is already fairly good (the shadow
   comparison shows it's within ~1.2 of the marginal estimate on average).
2. The marginalization cost is ≈ N/bucket × (multiRollout + leaf blend),
   where N=16 particles but only ~4 unique outcomes. Each bucket evaluation
   incurs a full multi-rollout + leaf blend.
3. The per-search marginalization time is small (~0.1-0.15s) but adds up
   across ~500 events per search.

The theoretical attractiveness (87.8% reduction from 64→8 evaluations)
doesn't translate to practice because the baseline never did 64 evaluations;
it did one.

## Variance test (Section 12)

Not run. The shadow comparison provides a proxy: the marginal estimate is
within ~1.2 of the ordinary estimate on average. The variance reduction from
marginalization appears modest relative to the cost increase.

## Rationale

- The decision rule: "STOP immediately if marginalization causes >2x search
  CPU with no large variance reduction / obvious quality benefit."
  - CPU increase: +56% (not >2×, but substantial)
  - No obvious quality benefit at equal CPU in the 8-seed smoke test
  - The hypothesis that "bucketed estimator has 10× lower variance" is not
    supported — the ordinary estimator is already fairly accurate
- The equal-sims comparison shows identical win rate (25%) but worse HP,
  suggesting the extra evaluations per sim reduce the total number of
  simulations that reach deep tree exploration.
- At equal CPU, the reduced sim budget (550 vs 1000) means ~45% fewer tree
  descents, which offsets any per-leaf improvement.

## Files changed

| File | Change |
|------|--------|
| `include/sim/search/BattleScumSearcher3.h` | `endTurnMarginalEval` declaration, 3 new globals + 10 thread-local diag counters |
| `src/sim/search/BattleScumSearcher3.cpp` | `endTurnMarginalEval()` (~140 lines), marginalization hook in `step()` leaf-expansion path (~10 lines), diag output in `printReuseDiagnostics()`, 3 new globals |
| `apps/one_combat.cpp` | 3 env-var parse blocks |

## Status and follow-up

- **Status: STOP — marginalization is too expensive for the variance reduction it provides.**
- The outcome redundancy findings (45.5% of draws have ≤8 unique outcomes,
  99% of buckets are value-homogeneous) remain scientifically valid but don't
  translate to a practical MCTS speedup under the current architecture.
- Possible future uses (not MCTS):
  - Training target generation (cheap, low-variance labels for END_TURN states)
  - Root-only tactical calculation (where cost is less constrained)
  - Offline leaf-value relabeling with marginal expectation
- An optimization not explored: share the multi-rollout across all buckets
  (since they share the same pre-END_TURN RNG state), or use the vnet
  directly without rollout for bucketed evaluation.

## ELI5

> **"Instead of guessing one possible next hand, we looked at the handful of
> genuinely different hands and averaged them. Did the better estimate save
> enough MCTS guessing to justify the extra work?"**

**No — the extra work cost more than the better guess saved.** Looking at 16
possible draws and averaging 4 genuinely different hands gives a slightly
more accurate estimate of how good the turn will be, but it takes ~3-7×
longer per END_TURN decision. The baseline approach (one random draw, one
rollout) is already close to the right answer most of the time, and the
search makes better use of the saved time exploring other parts of the tree.

It's like checking 4 weather forecasts instead of 1 before deciding to bring
an umbrella. If the forecast is usually right, the extra checks don't change
your decision often enough to justify the time.
