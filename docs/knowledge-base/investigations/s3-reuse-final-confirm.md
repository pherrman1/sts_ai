# S3 obs-stable reuse — final 128-seed confirmation (block 2)

Date: 2026-08-09
Commit: `ecebb0e`
Status: **KEEP EXPERIMENTAL — consistently positive direction but p=0.22, CPU inconsistent between blocks**

## Block 2: seeds 200000–200127 (128 seeds)

| Metric | A (control) | G (obs-stable + keep + N=1) | Delta |
|--------|-------------|------------------------------|-------|
| Wins | 54 (42.2%) | 57 (44.5%) | +2.3pp |
| Floor | 41.4 | 41.5 | +0.14 |
| HP end | 20.5 | 19.6 | −0.83 |
| CPU/run | 31.08s | 46.01s | **+48%** |

Paired discordants:
```
         G win  G loss
A win      34      20
A loss     23      51
```
WL=20 (A wins, G loses), LW=23 (A loses, G wins). Net: +3 wins.

McNemar exact p = 0.7608. Bootstrap 95% CI: [−7.8pp, +12.5pp].

Reuse acceptance: 43,415 attempted, 33,309 accepted (76.7%).
Rejected: 8,872 obsMismatch, 1,249 hashMismatch.
Gen histogram: g1=21,166, g2=12,151.

Zero correctness failures.

## Combined: 256 independent confirmation seeds (blocks 1 + 2)

Block 1 (100000–100127): WW=23 WL=14 LW=23 LL=68
Block 2 (200000–200127): WW=34 WL=20 LW=23 LL=51

| | A (control) | G (obs-stable + keep + N=1) | Delta |
|---|---|---|---|
| Wins | 91 (35.5%) | 103 (40.2%) | **+4.7pp** |
| Floor | — | — | +1.08 |
| HP end | — | — | +0.49 |

Combined paired:
```
         G win  G loss
A win      57      34
A loss     46     119
```
WL=34, LW=46. Net: +12 discordant wins.

**McNemar exact p = 0.2185** (80 discordant pairs, b=34).
**Bootstrap 95% CI: [−2.0pp, +11.7pp]**.

## CPU inconsistency across blocks

| Block | Control CPU | G CPU | Ratio | G cheaper? |
|-------|-------------|-------|-------|-------------|
| 0–63 (dev) | 35.20 | 34.88 | 0.99 | ~equal |
| 100000–100127 | 38.10 | 31.91 | 0.84 | **−16%** |
| 200000–200127 | 31.08 | 46.01 | 1.48 | **+48%** |

Block 2's CPU regression is the opposite of block 1's CPU advantage. Control win
rates differ substantially (28.9% vs 42.2%), suggesting the seed blocks exercise
different combat distributions. The 48% CPU increase in block 2 may reflect
that observation-stable carries fail more often in richer/easier runs, causing
additional search work without reuse savings.

## Decision: KEEP EXPERIMENTAL

The direction is consistently positive across all three blocks (+6.3, +7.0, +2.3pp).
Combined 256-seed delta = +4.7pp, discordants 46 vs 34 favor G.
But the promotion threshold is not met:

1. ✓ Block 2 non-negative (+2.3pp)
2. ✓ Combined G wins > A wins (103 > 91)
3. ✓ Combined LW > WL (46 > 34)
4. ✗ **McNemar p = 0.22** (threshold: p < 0.05)
5. ✓ Floor/HP approximately flat (combined: +1.08 floor, +0.49 HP)
6. ✗ **CPU inconsistent** — block 2 is 48% more expensive

The CPU inconsistency is the most concerning signal. On block 1, reuse saved
16% CPU; on block 2, it cost 48% more. This suggests the CPU impact depends on
the seed block's combat characteristics and cannot be guaranteed.

## Cross-block win-rate deltas

| Block | Seeds | A win% | G win% | Δ |
|-------|-------|--------|--------|-----|
| Dev | 0–63 | 37.5 | 43.8 | +6.3pp |
| Confirm 1 | 100000–100127 | 28.9 | 35.9 | +7.0pp |
| Confirm 2 | 200000–200127 | 42.2 | 44.5 | +2.3pp |
| **Combined confirm** | **256** | **35.5** | **40.2** | **+4.7pp** |

All blocks positive. No block shows G < A.

## ELI5

We tested the tree-carrying trick on a second batch of 128 brand-new games.
It won 3 more games than normal (44.5% vs 42.2%) — still positive, but a
smaller lead than the first batch. Over all 256 test games combined, the
trick won about 4.7pp more often (+4.7pp), a consistent positive direction
but not quite statistically bulletproof yet (p=0.22). The bigger concern is
that the trick's CPU cost varies wildly — on one batch it saved 16% time,
on this batch it cost 48% more. We can't guarantee it'll be faster. Keep it
as an experimental option, not the default, until we understand the CPU
behavior better.
