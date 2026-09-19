# Silver UID fragmentation diagnostic

Decision: `SILVER_UID_FRAGMENTATION_AMBIGUOUS`

This is diagnostic evidence only. Production Silver search behavior is
unchanged: exact `equalForSearch()` remains authoritative, relaxed matches are
never returned, visits are never shared, and chance edges are never modified.

## Provenance and command

- Baseline `main`: `46206a59817d1b664566b5f46682110c7bc991bc`
- Snapshot: `docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`
- Cohort: hard64 DEV, all 64 cases; HOLDOUT was not run
- Budget: 1,000 simulations per decision
- Threads: `OMP_NUM_THREADS=4`
- Command: `OMP_NUM_THREADS=4 bash tools/seed_guard.sh build/linux-gcc-debug-ccache/silver_hard_combat_replay docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --uid-fragmentation`
- Raw output: `hard64-dev-uid-fragmentation.jsonl`
- Raw output SHA256: `e2ba18fef958964748aed4877c162b53b6ae335cff1a60b4780b30d856e3584f`
- All 64 rows completed with `status=ok`.

The diagnostic comparator is exact for every `BattleContext` field except the
hand multiset and the unknown draw-pile multiset. Known top and bottom cards,
full-order-observed state, discard/exhaust/limbo/stasis, queues, potions,
player, monsters, card-select state, scalar counters, and `nextUniqueCardId`
remain exact. Card matching reuses
`Action::areCardsEquivalentForSearch`, so special-data cards remain
identity-sensitive.

## Aggregate

| Measure | Total | Rate / note |
| --- | ---: | --- |
| Exact decision nodes created | 2,063,754 | denominator |
| Relaxed node-allocation candidates | 78,176 | 3.788% |
| Sampled chance outcomes | 2,064,149 | denominator |
| Relaxed chance-sibling candidates | 33,461 | 1.621% |
| Chance candidates, END_TURN | 19,951 | category 0 |
| Chance candidates, CARD | 12,043 | category 1 |
| Chance candidates, OTHER | 1,467 | category 2 |
| Node candidates, hand-only | 206 | |
| Node candidates, draw-only | 281 | |
| Node candidates, both hand and draw | 77,689 | strongest swap signature |
| Chance candidates, hand+draw swap | 33,376 | |

Node candidates occurred in 64/64 cases and chance candidates in 63/64.
Median and maximum candidates per case were 726.5 and 6,718 for node
allocations, and 313 and 3,072 for chance siblings.

## Top cases

### Relaxed node-allocation candidates

| Case | Candidates | Nodes created | Hand-only | Draw-only | Both |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12100014/9 | 6,718 | 43,482 | 0 | 0 | 6,718 |
| 12100007/7 | 5,463 | 54,067 | 11 | 0 | 5,452 |
| 12100029/5 | 4,782 | 30,071 | 0 | 0 | 4,782 |
| 12100021/2 | 4,582 | 26,061 | 0 | 0 | 4,582 |
| 12100050/9 | 3,721 | 26,079 | 0 | 0 | 3,721 |
| 12100053/7 | 3,524 | 24,921 | 0 | 0 | 3,524 |
| 12100026/8 | 2,887 | 33,894 | 0 | 0 | 2,887 |
| 12100018/8 | 2,822 | 39,847 | 0 | 0 | 2,822 |
| 12100037/28 | 2,784 | 65,621 | 1 | 26 | 2,757 |
| 12100017/16 | 2,511 | 46,124 | 0 | 20 | 2,491 |

### Relaxed chance-sibling candidates

| Case | Candidates | Sampled | Hand+draw swap | END_TURN | CARD | OTHER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 12100014/9 | 3,072 | 56,434 | 3,072 | 2,837 | 235 | 0 |
| 12100029/5 | 2,594 | 24,898 | 2,594 | 2,592 | 2 | 0 |
| 12100007/7 | 2,234 | 63,928 | 2,226 | 1,679 | 555 | 0 |
| 12100021/2 | 1,857 | 17,721 | 1,857 | 1,857 | 0 | 0 |
| 12100053/7 | 1,474 | 32,231 | 1,474 | 1,220 | 254 | 0 |
| 12100018/8 | 1,252 | 48,872 | 1,252 | 801 | 451 | 0 |
| 12100019/5 | 1,182 | 20,064 | 1,182 | 709 | 182 | 291 |
| 12100039/17 | 1,110 | 59,137 | 1,110 | 732 | 378 | 0 |
| 12100026/8 | 1,012 | 35,390 | 1,012 | 799 | 213 | 0 |
| 12100037/28 | 1,004 | 60,028 | 1,004 | 393 | 497 | 114 |

The high-count rows are distributed across multiple cases. Their candidate
classification is overwhelmingly the hand+unknown-draw swap signature; the
focused comparator fixtures also cover ordinary-card UID swaps, special-data
protection, known-pile boundaries, discard/exhaust, and queued-card identity.

## Decision and boundary

The 3.788% node rate is between 1% and 5%, and the 1.621% chance rate is
between 1% and 10%. This is therefore intermediate/ambiguous under the
requested prioritization heuristic, with node allocation fragmentation as the
dominant event type. This result does not authorize identity canonicalization.
A later design must separately prove semantic lowering, persistent deck-card
identity, queue/reference safety, temporary-vs-deck separation, special-data
protection, and retained-root exactness.

Knowledge impact: experiment/diagnostic evidence; production Silver search
behavior unchanged.
