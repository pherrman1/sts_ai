# Map-root value-of-computation audit (#927 rank 6): prior ≥ 0.98 roots take 55% of map simulations and change 1.9% of picks

Offline, no seeds. Literature ranking item 6 ([search-and-value-literature.md](../../../knowledge-base/research/search-and-value-literature.md),
#927). Requested by Philipp 2026-11-01 07:25Z ("Neuer thread für ... 6"). Only the free audit; the follow-up SPRT needs
his typed go.

## Data

- **Primary:** §727 arm A (production A20 stack, RUN_COMMIT `3d62ff5e`, `STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25`,
  map-only search at full budget per ADR-0061), 1,536 complete games, seeds 111312000-111313535 (already used),
  `/mnt/project-files/value-chooser-ab/units`.
- **Replication:** §683 arm MAP (`772df240`, `STS_OOC_MCTS_SCREENS=map`, full budget), 1,024 games, seeds
  111374100-111375123 (already used), `/mnt/project-files/ooc-map-only-search/units`.
- Unit: every searched map root (`by=mcts`, screen 5) with more than one action. Singleton roots (no simulations) are
  excluded: 31,991 in A, 21,265 in MAP. No aborted roots. Every root ran 4,096 simulations; the logged 4,096 checkpoint's
  most-visited action equals the played action at 23,826/23,826 (A) and 16,322/16,322 (MAP) roots.
- Checkpoint picks use the production rule `visits_q_id` (visits, then Q, then lower id). **Inference (code read,
  `OocMctsPlanner::search`):** the root at checkpoint k is the tree a k-simulation search with the same seed would
  have, because simulations run sequentially from one RNG and no selection term depends on the total budget at a
  full-budget root (stops are off there). So "pick at 1,024" is what a 1,024-simulation search would play.
- `analyze.py ARM UNITS_DIR OUT_JSON` (this directory) → `vc_A.json`, `map683.json`.

## Decision rule (from #927, stated before this audit)

"If roots with prior ≥ 0.98 change > ~3% of decisions or use little CPU, drop. Else SPRT [−1.5, 0]."
"Change" = played action ≠ prior argmax. "Little CPU" was not quantified in #927; this audit uses < 25% of map
simulations (set after the first pass over A, before the replication; disclosed).

## Result

| | A (§727, 1,536 games) | MAP (§683, 1,024 games) |
|---|---|---|
| searched non-singleton map roots | 23,826 (15.5 per game) | 16,322 (15.9 per game) |
| map simulations per game | 63,536 | 65,288 |
| **roots with prior top ≥ 0.98: share of roots = share of simulations** | **54.6%** (CPU-weighted by act 54.7%) | 54.4% |
| **… played ≠ prior argmax** | **1.94% ± 0.12** (252/13,020; 0.16 per game) | 1.95% (173/8,884) |
| … pick at 1,024 ≠ pick at 4,096 | 1.54% (201) | 1.60% |
| … pick at 1,024 ≠ prior argmax | 0.39% (51) | 0.35% (31) |
| roots with prior top < 0.98: played ≠ prior argmax | 11.6% | 12.5% |
| all roots: played ≠ prior argmax | 6.3% (1.0 per game) | 6.7% |
| all roots: pick at 1,024 ≠ pick at 4,096 | 3.74% (0.58 per game) | 3.87% |
| all roots: pick at 2,048 ≠ pick at 4,096 | 2.44% | 2.29% |

By prior-top bin (A; MAP within ±2.1 pp in every bin, see `map683.json`):

| prior top | roots | share of map sims | played ≠ prior | 1,024 ≠ 4,096 | ≠ prior already at 1,024 |
|---|---|---|---|---|---|
| < 0.5 | 319 | 1.3% | 38.9% | 16.0% | 93 |
| 0.5-0.8 | 4,809 | 20.2% | 17.6% | 8.6% | 532 |
| 0.8-0.9 | 2,124 | 8.9% | 6.4% | 4.9% | 33 |
| 0.9-0.95 | 1,686 | 7.1% | 5.6% | 4.7% | 17 |
| 0.95-0.98 | 1,868 | 7.8% | 2.9% | 2.3% | 13 |
| 0.98-0.99 | 1,180 | 5.0% | 3.1% | 2.4% | 8 |
| 0.99-0.999 | 3,545 | 14.9% | 2.8% | 2.4% | 14 |
| ≥ 0.999 | 8,295 | 34.8% | 1.4% | 1.1% | 29 |

Secondaries (A):
- With prior ≥ 0.8, departures from the prior appear late: at 128 simulations the pick is the prior argmax in all but
  4 of 18,698 such roots; at 1,024 in all but 114; of the 426 flips from 1,024 to 4,096 in these bins, 425 move
  away from the prior. Below 0.8, 56 of 465 flips move back to the prior.
- When the search departs at prior ≥ 0.98, its own Q gap is not small: median Q(played) − Q(prior argmax) +0.069
  (90th percentile +0.120), prior argmax median 1,430 visits, played action 2,666. A rough z with an independent leaf
  SD of 0.13 (rollout-cost measurement 2026-10-31) has median 16. **Inference:** these departures are a stable
  leaf-vs-prior disagreement, not Q noise; whether the leaf is right there is what §710 could not show (search-departs
  roots +1.4 pp [−5.3, +8.7], 26 roots).
- Estimated map-search CPU ≈ 650 s per game (acts 1-3 at 7.5/10.6/14.4 ms per simulation, rollout-cost measurement;
  **Inference**, not timed here).

## Decision

By the #927 rule: prior ≥ 0.98 roots change 1.9% < 3% of picks **and** use 55% of map simulations (not little) →
**not dropped; the 1,024 vs 4,096 non-inferiority SPRT is justified.** The audit does not say whether the
removed departures were good or bad; only play can.

Sizing for that SPRT (Inference from these rates): a 1,024 cap on all map roots changes 0.58 picks per game and saves
75% of map simulations (≈ 490 s per game); a 1,024 cap only on prior ≥ 0.98 roots changes 0.13 picks per game and
saves 41%. With on average 0.58 changed picks per game under the global cap, many paired games stay identical until late or
never diverge, which lowers the paired variance of the SPRT on the [−1.5, 0] pp Heart-kill band (Inference). The SPRT needs Philipp's typed
go, worker count, new seeds and frozen provenance.
