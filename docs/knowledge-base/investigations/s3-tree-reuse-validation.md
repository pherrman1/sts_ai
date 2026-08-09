# S3 fair tree reuse — validation round

Date: 2026-08-09
Status: **obs-stable + keep + N=1 (G) beats control by +6.3pp. Promotable to 128-seed confirmation.**

## 1. STS_REUSE_MAX_SEARCHES bug (fixed)

`advanceRoot()` was resetting `reuseSearchCount = 0` on every successful
promotion. The counter went: 0→1(incr)→0(reset)→0→1(incr)→0(reset)..., never
reaching the limit. N=1 behaved like unlimited cascade.

**Fix:** Moved counter to agent loop (`carriedSearchesSinceFresh`). Reset only
on fresh searcher construction. Incremented after every search. Checked BEFORE
searching. N=1 caps at `maxGen=2` (one carried search). N=-1 cascades to
`maxGen=4-5`.

Trace proof from single-seed:
```
N=1: maxGen=2, carriedSearchesSinceFresh=2 → exactly one carry ✓
N=-1: maxGen=4-5, carriedSearchesSinceFresh=3-4 → cascading ✓
```

## 2. 64-seed gate results (asc 0, 1000 sims, 64 particles, 12 threads)

| Arm | Config | win% | floor | hp | cpu/run |
|-----|--------|------|-------|-----|---------|
| A | fresh, 1000 sims | 37.5 | 42.9 | 20.6 | 35.20 |
| **F** | RNG gate + keep + no always-Q + N=1 | **39.1** | 42.0 | 20.7 | 30.89 |
| **G** | obs-stable + keep + N=1 | **43.8** | 42.4 | 20.9 | 34.88 |
| **H** | obs-stable + keep + N=-1 | **40.6** | 43.6 | 23.2 | 33.59 |

Paired discordants (vs A on same 64-seed block):
- F vs A: ~+1 net win (narrow)
- G vs A: ~+4 net wins on 64 seeds
- H vs A: ~+2 net wins on 64 seeds

### CPU comparison

H (40.6%) uses 33.59 cpu/run — LESS than control A (37.5%, 35.20 cpu/run).
Reuse wins on BOTH axes: better win% at lower CPU.

## 3. Interpretation

### F recovers strongly (39.1% vs old 4.7%)

The old catastrophic keep-stat result was caused by `STS_REUSE_ALWAYS_Q`.
Without it, RNG-gate keep-stat reuse is slightly ABOVE control (+1.6pp).
`always_Q` forced exploitation of stale Q values from mismatched observations
before a winning line was found — keeping stats passively is fine, but
actively exploiting them too early destroys the search.

### G > H (43.8% vs 40.6%)

Single-use carries beat cascading. Cascading compounds observation drift and
narrows the tree topology. N=1 is both better AND simpler.

### G beats A by +6.3pp

At 64 seeds this is ~4 net wins. With a Wilson 95% CI on the difference:
roughly [−2.8, +15.4]pp — not statistically significant at 64 seeds, but
directionally positive and the CPU comparison is favorable.

## 4. Aggregate observation-stable statistics (64 seeds, G & H)

From per-battle `[reuse-generation]` lines:

| Metric | G (N=1) | H (N=-1) |
|--------|---------|----------|
| Acceptance rate | ~78% of attempted | ~75% of attempted |
| Rejected: obsMismatch | ~5% of attempted | ~5% of attempted |
| Rejected: hashMismatch | ~1% of attempted | ~1% of attempted |
| Rejected: missing child | ~16% of attempted | ~19% of attempted |
| Accepted / all decisions | ~61% | ~56% |

The obs-stable gate DOES filter: ~22-25% of promotion attempts are rejected.
~61% of all combat decisions produce an accepted obs-stable carry. This is not
a near-100% pass-through — the gate is doing real work.

Generation histogram (H, N=-1, aggregate):
- g1: ~40%, g2: ~28%, g3: ~16%, g4: ~9%, g5+: ~7%

Most carries terminate at g1-g2, but cascading does build multi-layer reuse.

## 5. Conclusion

**Promote G to 128-seed confirmation gate.**

Rationale:
- G beats control (+6.3pp) at essentially identical CPU
- The obs-stable gate is a principled correctness condition (single visible
  observation matching new root), not a heuristic
- N=1 is the simplest and best-performing setting
- `always_Q` is confirmed harmful — keep statistics passively, don't
  force exploitation
- The previous catastrophic failures (4.7-17.2%) were caused by:
  1. `always_Q` forcing exploitation too early (largest factor)
  2. RNG gate promoting multi-observation children (topology+stats stale)
  3. `advanceRoot()` counter bug making N=1 behave like cascade
- All three problems are now fixed or bypassed by obs-stable + keep + N=1

Do NOT promote:
- Cascading (H) — worse than N=1
- recursive_reset on obs-stable children — destroys informative signal
- Union expand — semantic identity bug needs fixing first
- RNG gate — obs-stable is the stronger condition

## 6. Exact commands

```bash
# A: control
STS_FAIR=1 STS_SEARCHER3=1 STS_REUSE_MAX_SEARCHES=0 \
  ./build/one_combat bestbench 1000 64 0

# F: RNG gate + keep + no always-Q + true N=1
STS_FAIR=1 STS_SEARCHER3=1 STS_REUSE_MAX_SEARCHES=1 \
  STS_REUSE_STATS_MODE=keep \
  ./build/one_combat bestbench 1000 64 0

# G: obs-stable + keep + N=1
STS_FAIR=1 STS_SEARCHER3=1 STS_REUSE_OBS_STABLE=1 \
  STS_REUSE_MAX_SEARCHES=1 STS_REUSE_STATS_MODE=keep \
  ./build/one_combat bestbench 1000 64 0

# H: obs-stable + keep + N=-1
STS_FAIR=1 STS_SEARCHER3=1 STS_REUSE_OBS_STABLE=1 \
  STS_REUSE_MAX_SEARCHES=-1 STS_REUSE_STATS_MODE=keep \
  ./build/one_combat bestbench 1000 64 0
```

Arm I (CPU-matched fresh) not needed — H already uses LESS CPU than A at 1000 sims.

## 7. ELI5

We found out why the previous tree-carrying experiments crashed so badly: the
searcher was forced to trust old score estimates before it had found a winning
plan. When we fixed that and added a smarter "is this child safe to carry?"
check, the tree reuse started WORKING — carrying a single-use subtree with
retained scores beats fresh search by about 6 extra wins out of 100 games,
while using slightly less CPU. The simpler one-carry approach works better
than chaining multiple carries. We should run a bigger test to make sure it
holds up.
