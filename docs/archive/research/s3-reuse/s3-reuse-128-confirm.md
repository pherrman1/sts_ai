# S3 obs-stable reuse — 128-seed confirmation gate

Date: 2026-08-09
Commit: `ecebb0e`
Status: **ARCHIVED intermediate result.** Superseded by the final promotion record.

## 1. N=1 semantics verified

Single-seed trace confirms exactly one carried search per fresh tree:
- `carriedSearchesSinceFresh` max = 2 (1 fresh + 1 carried)
- `maxGen` = 1 or 2
- Seacher rebuilds after second search

## 2. Seed block

New independent block, never used in S3 reuse development:
```
seed start  = 100000
seed end    = 100127
n           = 128
```

## 3. Exact commands

```bash
# A: control
STS_FAIR=1 STS_SEARCHER3=1 STS_REUSE_MAX_SEARCHES=0 \
  ./build/one_combat bestbench 1000 128 0 100000 \
  /tmp/reuse_confirm_control.csv

# G: obs-stable + keep + N=1
STS_FAIR=1 STS_SEARCHER3=1 \
  STS_REUSE_OBS_STABLE=1 STS_REUSE_MAX_SEARCHES=1 \
  STS_REUSE_STATS_MODE=keep STS_REUSE_ALWAYS_Q=0 \
  ./build/one_combat bestbench 1000 128 0 100000 \
  /tmp/reuse_confirm_obsstable_n1.csv
```

## 4. Result table

| Metric | A (control) | G (obs-stable + keep + N=1) | Delta |
|--------|-------------|------------------------------|-------|
| Wins | 37 | 46 | +9 |
| Win% | 28.9% | 35.9% | **+7.0pp** |
| Floor | 38.6 | 40.6 | +2.02 |
| HP end | 13.3 | 15.1 | +1.80 |
| CPU/run | 38.10s | 31.91s | **−16.3%** |
| Wall | 437s | 362s | −17% |

## 5. Paired discordant table

```
         G win  G loss
A win      23      14
A loss     23      68
```

- WL = 14 (A wins, G loses)
- LW = 23 (A loses, G wins)
- Net = +9 discordant wins = +7.0pp

## 6. Statistical tests

- **McNemar exact binomial**: p = 0.1877 (37 discordant pairs, b=14)
- **Bootstrap 95% CI on win diff**: [−2.3pp, +16.4pp] (100k resamples)
- Not significant at α=0.05 on 128 seeds, but directionally strongly positive

## 7. Floor / HP paired deltas

- Floor delta: mean +2.02, median 0.0
- HP delta: mean +1.80, median 0.0
- No regression on either metric

## 8. CPU

- CPU ratio (G/A) = 0.837 — G is **16.3% cheaper**
- Reuse reduces CPU because carried tree work reduces expensive enumeration/rollout

## 9. Reuse acceptance statistics (G, 128 seeds aggregate)

| Metric | Count |
|--------|-------|
| Attempted | 40,452 |
| Accepted | 32,716 (80.9%) |
| Rejected: obsMismatch | 6,933 |
| Rejected: hashMismatch | 803 |
| Rejected: other | 0 |

Generation histogram: g1=20,367, g2=12,349

## 10. Correctness

No battle stalls, no assertions, no NaNs, no empty-action failures.
Zero correctness issues across 128 seeds.

## 11. Comparison with 64-seed development gate

| Block | A win% | G win% | Delta | CPU ratio |
|-------|--------|--------|-------|-----------|
| 64-seed (0-63, dev) | 37.5% | 43.8% | +6.3pp | 0.99 |
| 128-seed (100000-100127, confirm) | 28.9% | 35.9% | +7.0pp | 0.84 |

Consistent positive signal across independent seed blocks. The absolute win rates
differ because different seed blocks have different difficulty, but the delta is
reproducible (+6-7pp). The CPU advantage is larger on the confirmation block.

## 12. Decision: KEEP EXPERIMENTAL

The evidence is strongly positive but does not meet the mechanical p<0.05 bar
at 128 seeds (p=0.19, CI crosses zero).

However:
- Both independent blocks show +6-7pp
- CPU is 16% cheaper
- Floor and HP are positive
- Zero correctness failures
- The obs-stable condition is principled, not heuristic

**Recommendation**: Run one more independent 128-seed block. If the combined
256-seed evidence maintains the direction, promote to default.

Do not make obs-stable reuse the default until the combined p-value crosses
significance or a third independent block confirms.

## 13. ELI5

We tested the tree-carrying trick on 128 brand-new game seeds it had never
seen before. The trick won 9 more games than the normal method (36% vs 29%),
while using 16% less computer time. That's a really good sign — it worked on
both the practice seeds and the test seeds. But with only 128 test games, we
can't be 95% sure it wasn't luck. One more batch of 128 seeds should settle it.
If it keeps winning, we make it the new default.
