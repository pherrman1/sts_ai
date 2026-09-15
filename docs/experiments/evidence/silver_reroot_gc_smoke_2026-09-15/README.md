# Silver reroot GC: repeated canary and bounded flat-1k smoke

Baseline `876e9305a258df3d5a5eafd50e30375b933f8884`; measured candidate
`1e37f2a9d68a403158241886f85c926b37b62f1a` (PR #185). The later evidence
commit changes documentation/artifacts only. Complete commands, model/binary
hashes, build/export provenance, metadata, validation totals and paired rows are
in [provenance.json](provenance.json). Raw CSVs, metadata, compressed complete
stdout/stderr, strict [paired analysis](paired-analysis.txt), and CTest output
are adjacent. No larger benchmark or search-quality qualification was run.

## Repeated real-search canary

Guarded CTest `silver_repeated_reroot_canary` uses the private Silver searcher
with the starter deck, Ironclad 200/200 HP, Jaw Worm, A0, seed `0xBADC0DE`,
floor 1 / act 1. Each search adds exactly 10,000 simulations. The path follows
the first stored outcome of an expanded legal END_TURN action to exercise
compaction across turns. It does not assess recommended-action quality.

| Search / reroot | Cumulative real allocations | Before reroot | Retained nodes |
| --- | ---: | ---: | ---: |
| 1 | 11,635 | 11,635 | 9 |
| 2 | 23,868 | 12,242 | 1 |
| 3 | 35,878 | 12,011 | 79 |
| 4 | 48,231 | 12,432 | 4 |
| 5 | 58,494 | 10,267 | 64 |

All five reroots preserve retained pointers, node/edge visits and evaluation
sums, chance bookkeeping, available best action and dedup hits. Ownership is
checked after each search and compaction. Three reroots occur after cumulative
allocations cross 32,768; all retained graphs stay below the production cap.
58,430 nodes are reclaimed by the fifth reroot. One final 10k continuation
passes ownership checks with 11,795 live nodes and 70,225 cumulative allocations.
Debug and Release output is identical.

The cumulative counter sums real allocations by the compacting PR searcher;
it is not an executed unmodified baseline graph size. The direct searcher
reports the retained cap predicate; session cap regressions separately verify
that historical allocation cannot cause ALLOCATED_CAP, while truly over-cap
reachable graphs still fall back. No dummy nodes or fresh resets enter this
repeated canary. A preliminary selected-action Looter path actually grew the
reachable graph to the cap and could not demonstrate the requested historical-only
case; its failure log is retained.

## Sixteen paired-seed smoke

Question: does removal of orphan transposition statistics cause a crash or an
obvious adverse shift at the current flat-1k Silver/default-OOC configuration?
Fixed design: seeds 0–15, one run per arm, Ironclad A0, project-fair Silver,
exact 1k per private search (including sequential-selection subdecisions),
allocated cap 32,768, adaptive and learned direct Silver leaves OFF, keys OFF,
4 OpenMP threads. Baseline then candidate, both Release; same tracked models
and serverless native default OOC. The baseline is built from exact tracked
source/dependency exports inside the existing worktree, without another Git
worktree. Metadata verifies effective backend, source SHA and configuration;
observed load banners and matching hashes verify shared models.

| Metric | Baseline | PR | PR minus baseline |
| --- | ---: | ---: | ---: |
| Wins | 10/16 (62.5%) | 7/16 (43.75%) | -18.75 pp |
| Mean floor | 45.375 | 46.9375 | +1.5625 |
| Mean end HP | 23.4375 | 15.9375 | -7.5 |

Six pairs both win, five both lose, four win only on baseline (seeds 1, 3, 5,
7), and one wins only on PR (seed 15). Strict paired bootstrap 95% intervals:
win difference [-43.75, +6.25] pp; mean floor difference approximately
[-1.8, +6.6]. Both arms exit 0 with all 16 unique seeds. All telemetry budgets
match 1k per private subsearch; conversion, semantic-resolution, transaction
and knowledge failure counters are zero. Neither arm has an allocated-cap
fallback at flat 1k. Complete Debug CTest: 92/92 pass.

**Interpretation:** an adverse win signal with higher mean floor. This small,
noisy, mixed smoke is not a clean nonregression result and does not establish
harm or improvement. It confirms exercised-path correctness, not search-budget
quality. Stop at the authorized 16 pairs; retain the draft/review boundary.
Timing rows are descriptive only: ordered arms and concurrent builds/checks
are not a controlled performance comparison.
