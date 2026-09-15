# Local 17 x 32 OOC MCTS parameter screen

Tested source: `b7b26548a8800899318e5b78ca135c52e0117ed5`. Packaging base: `608bb810c44173fb8c0036df6e89c71da4d778e3`.

All 17 profiles completed on common seeds `12002000..12002031`: Ironclad A0, fair RNG, exact-root-budget 10,000-simulation Silver combat, keys off, Act 3 stop, 12 OpenMP threads. Every arm has 32 result rows and 32 MCTS telemetry rows; source, binary, CTM, profile/environment, startup, ownership, simulation, support and abort-accounting receipts pass `analyze.py`. The strategic-model path and successful load marker are retained per arm; its plan-time hash matches packaging time, but the runner did not re-hash its bytes at execution.

| Rank | Profile | Change from reference | Wins | Win rate | Mean floor | Mean sec/game | Paired delta vs ref |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `12_rollout3` | three additional CTM combats | 26/32 | 81.2% | 50.000 | 2024.4 | +15.6 pp |
| 2 | `13_uniform_leaf` | one CTM combat, uniform continuation | 24/32 | 75.0% | 47.469 | 663.7 | +9.4 pp |
| 3 | `11_rollout1` | one additional CTM combat | 23/32 | 71.9% | 48.469 | 925.9 | +6.2 pp |
| 4 | `15_budget512` | 512 simulations | 23/32 | 71.9% | 47.469 | 48.9 | +6.2 pp |
| 5 | `16_budget10000` | 10,000 simulations | 22/32 | 68.8% | 48.031 | 123.1 | +3.1 pp |
| 6 | `08_depth8` | depth8 | 22/32 | 68.8% | 47.500 | 72.4 | +3.1 pp |
| 7 | `07_broad` | chance widening k4/a.75 | 21/32 | 65.6% | 47.531 | 81.6 | +0.0 pp |
| 8 | `00_ref` | reference: policy T1, c1.5, k2/a.5, depth32, native leaf, visits, 2048 sims | 21/32 | 65.6% | 47.219 | 69.1 | +0.0 pp |
| 9 | `09_depth16` | depth16 | 21/32 | 65.6% | 47.219 | 72.2 | +0.0 pp |
| 10 | `06_narrow` | chance widening k1/a.25 | 20/32 | 62.5% | 47.969 | 64.5 | -3.1 pp |
| 11 | `04_flat` | policy T2, c3 | 20/32 | 62.5% | 46.969 | 72.4 | -3.1 pp |
| 12 | `03_sharp` | policy T.5, c.5 | 20/32 | 62.5% | 46.375 | 65.9 | -3.1 pp |
| 13 | `01_uniform15` | uniform prior, c1.5 | 19/32 | 59.4% | 45.062 | 73.2 | -6.2 pp |
| 14 | `02_uniform3` | uniform prior, c3 | 18/32 | 56.2% | 45.625 | 81.8 | -9.4 pp |
| 15 | `05_greedy` | c0 | 18/32 | 56.2% | 43.969 | 66.4 | -9.4 pp |
| 16 | `14_root_q` | root selection by mean Q | 17/32 | 53.1% | 44.000 | 70.9 | -12.5 pp |
| 17 | `10_no_value` | constant .5 checkpoint leaf | 15/32 | 46.9% | 44.812 | 56.5 | -18.8 pp |

The descriptive screening leader is `12_rollout3` with 26/32 wins (81.2%) and mean floor 50.0. It uses three additional CTM-resolved combats before native leaf scoring. Its mean elapsed time was 2024.4s/game: 29.3x the reference and 41.4x the fastest profile (`15_budget512`). Ranking uses wins, floor, then time rather than treating speed as equivalent to win rate.

The rollout3 telemetry records 7,413,229 successful CTM surrogate samples versus 161,856 for reference (45.8x). Together with the 29.3x elapsed-time ratio, this identifies the added CTM workload; it is not a component-level profiler and does not exclude V4, value-model or other overhead.

Against the reference on these paired seeds, the leader's observed delta is +15.6 percentage points; the deterministic 200,000-resample paired percentile interval is [-6.2, +37.5] points and includes zero. Its unpaired Wilson 95% win-rate interval is [64.7%, 91.1%]. These are descriptive uncertainty summaries, not selection-adjusted inference.

This is discovery evidence. The leader and its uncertainty were selected on the same cohort, there is no V4 control or untouched holdout, and the tested source predates current-main Silver memory/cap changes. It does not qualify a default or current-main gameplay improvement.

Raw CSV, metadata, MCTS telemetry, support reasons, environment receipts, scores and deterministic compressed logs are retained under `raw/`. `file-index.json` binds every other tracked packet file.

Knowledge impact: experiment evidence only. No maintained architecture, behavior, model, support, RNG, or deployment fact changes.
