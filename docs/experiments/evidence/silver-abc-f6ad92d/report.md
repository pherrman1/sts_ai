# Fresh Silver A/B/C experiment

## Provenance

- Frozen SHA: `f6ad92dd46df4b0c97312557fadef21be164dcd0`
- Primary seeds: `8..39` inclusive, 32 paired seeds
- Ascension: 0
- Horizon: `STS_STOP_AFTER_ACT=3`
- Fair combat: `STS_FAIR=1`
- Searcher3: `STS_SEARCHER3=1`
- GCP host: designated `sts-test`, 24 logical CPUs
- CPU: Intel Xeon Platinum 8581C @ 2.30 GHz, 12 cores / 24 threads
- Threads: `OMP_NUM_THREADS=24`, `OMP_DYNAMIC=FALSE`
- A: `STS_SILVER_SEARCH=0`, 1000 simulations
- B: `STS_SILVER_SEARCH=1`, 1000 simulations
- C: `STS_SILVER_SEARCH=1`, 3700 simulations, locked before seeds 8–39

The exact source/model sync and build were performed on the GCP disposable
benchmark worktree. The source was stale before sync; it was replaced with
the frozen checkout and rebuilt successfully. No repository executable,
model, search constant, or OOC policy was modified.

Executed commands, with `<out>` replaced by the arm-specific remote result
path, were:

```text
env OMP_NUM_THREADS=24 OMP_DYNAMIC=FALSE STS_FAIR=1 STS_SEARCHER3=1 STS_STOP_AFTER_ACT=3 STS_SILVER_SEARCH=0 ./build/one_combat bestbench 1000 32 0 8 <out>
env OMP_NUM_THREADS=24 OMP_DYNAMIC=FALSE STS_FAIR=1 STS_SEARCHER3=1 STS_STOP_AFTER_ACT=3 STS_SILVER_SEARCH=1 STS_SILVER_TELEMETRY=1 ./build/one_combat bestbench 1000 32 0 8 <out>
env OMP_NUM_THREADS=24 OMP_DYNAMIC=FALSE STS_FAIR=1 STS_SEARCHER3=1 STS_STOP_AFTER_ACT=3 STS_SILVER_SEARCH=1 STS_SILVER_TELEMETRY=1 ./build/one_combat bestbench 3700 32 0 8 <out>
```

The rebuilt GCP `build/one_combat` SHA-256 was
`d73c914296f2252ada60998e59160b5169fa504c5c295c8bc7478ce3f25f721a`.
Model hashes were: `v_rich_trees.txt`
`c866b62512bb7cf8abdebc6175415508cb667fe2d628198ac107fd35591a9447`,
`v_win_trees.txt`
`724a75ccc4bc2394306181db229aa2295433450f9596f1bc1479083dda337e35`,
`v_combat_7k_tuned.txt`
`e26fffdbe21392cc08db841859d46c13188acd16b180323868b04dca55e15ea2`, and
`policy_trees_c.txt`
`43c9dbddbebe52b4dce961b9376fcb76c1ac72a735caf161b646be0fa34f1a55`.

## Runtime calibration

See `calibration/runtime_calibration.csv` and
`calibration/runtime_calibration.md`. The locked budget was selected on the
local all-core calibration (`N_C=3700`, A/C ratio 0.946). On GCP, the primary
wall times were A=57.8 s and C=89.5 s, ratio 1.548. Thus C is not an
approximately equal-wall-clock arm on the actual primary host; A/C results
must be reported with this deviation.

## Primary aggregates

| Arm | Sims | Wins | Win rate | Mean floor | Median floor | Mean hpEnd | Median hpEnd | Mean successful hpEnd | Median successful hpEnd | Sum seed sec | Median seed sec | Wall sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A Searcher3 | 1000 | 15/32 | 46.9% | 44.3 | 50.0 | 20.3 | 0.0 | 43.3 | 33.0 | 949.18058 | 29.4211 | 57.8 |
| B Silver | 1000 | 20/32 | 62.5% | 47.4 | 51.0 | 31.8 | 27.0 | 50.8 | 47.0 | 466.01624 | 15.0256 | 26.3 |
| C Silver | 3700 | 21/32 | 65.6% | 47.5 | 51.0 | 28.5 | 24.5 | 43.4 | 41.0 | 1675.92740 | 55.19595 | 89.5 |

## Paired comparisons

The exact two-sided sign-binomial/McNemar p-values use only discordant
win/loss pairs. The paired floor intervals are the repository report's 95%
bootstrap intervals.

| Comparison | Win delta | Both win | Both loss | First-only | Second-only | Discordant | Exact p | Paired floor delta | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A vs B, equal simulations | +15.6 pp | 13 | 10 | 2 | 7 | 9 | 0.1796875 | +3.125 | [-0.4, +7.1] |
| A vs C, nominal equal-runtime budget | +18.8 pp | 12 | 8 | 3 | 9 | 12 | 0.1459961 | +3.25 | [+0.2, +6.5] |
| B vs C, Silver scaling | +3.1 pp | 16 | 7 | 4 | 5 | 9 | 1.0 | +0.125 | [-2.4, +2.7] |

A/B runtime ratio was B/A = 0.455 by whole-arm wall time; the median
per-seed ratio was 0.4625 and the geometric mean was 0.5015. B was faster on
28/32 seeds. C/A whole-arm wall ratio was 1.548; the median per-seed C/A
ratio was 1.6555 and geometric mean 1.7856. C was faster on 2/32 seeds.
B/C whole-arm wall ratio was 3.403; the median per-seed C/B ratio was 3.5088
and geometric mean 3.5606.

## Silver telemetry

Aggregated from every `[silver-combat]` record in each run log:

| Metric | B 1000 | C 3700 |
|---|---:|---:|
| telemetry records | 806 | 820 |
| decisions | 15,273 | 14,828 |
| simulations | 21,692,000 | 78,436,300 |
| transaction_subdecisions | 34 | 42 |
| reroot_exact | 9,971 | 7,710 |
| reroot_fallback | 4,492 | 6,296 |
| exact reroot rate | 68.94% | 55.05% |
| nodes | 19,521,397 | 68,182,548 |
| chance_outcomes | 19,295,416 | 75,837,686 |
| chance_sibling_reuse | 8,776,341 | 39,783,124 |
| deterministic transpositions | 1,639,002 | 5,723,618 |
| chance transpositions | 1,797,548 | 5,949,598 |
| widening_sampled | 19,295,416 | 75,837,686 |
| widening_capped | 8,842,795 | 38,762,434 |
| depth_sum | 127,732,769 | 504,803,826 |
| chance_depth_sum | 28,138,211 | 114,600,120 |
| simulations / decision | 1,420.28 | 5,289.74 |
| nodes / simulation | 0.89994 | 0.86927 |
| chance outcomes / simulation | 0.88952 | 0.96687 |
| conversion_failures | 0 | 0 |
| semantic_resolution_failures | 0 | 0 |
| transaction_failures | 0 | 0 |
| knowledge_failures | 0 | 0 |

## Raw artifacts

- [A results](A_searcher3_1000/results.csv), [A log](A_searcher3_1000/run.log), [A metadata](A_searcher3_1000/results.csv.meta.json)
- [B results](B_silver_1000/results.csv), [B log](B_silver_1000/run.log), [B metadata](B_silver_1000/results.csv.meta.json)
- [C results](C_silver_equal_runtime/results.csv), [C log](C_silver_equal_runtime/run.log), [C metadata](C_silver_equal_runtime/results.csv.meta.json)
- [Runtime calibration CSV](calibration/runtime_calibration.csv), [calibration notes](calibration/runtime_calibration.md)

The CSVs contain all 32 raw seed rows per arm. Earlier seeds 0–7 and earlier
Smoke Bomb diagnostic/performance rows are not part of this primary cohort.
