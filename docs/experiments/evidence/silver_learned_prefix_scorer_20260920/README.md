# Silver learned prefix scorer

Offline, source-seed-cross-fitted value prediction from the frozen PR #256 length<=2 CARD/END_TURN surface. This packet is diagnostic only: it changes no production Silver path, MCTS, gameplay seed, or holdout.

Classification: **LEARNED_PREFIX_SCORER_INSUFFICIENT**

Coverage: 247/247 leaves, 6194 candidates; lengths 1=1266, 2=4928.

| arm | params | Teacher-A regret | oracle recovered | Teacher-B reduction | CI p025 |
|---|---:|---:|---:|---:|---:|
| MLP_FACTORIZED_V1 | 79874 | 1.91306 | -42.23% | -53.29% | -1.59667 |
| MLP_FLAT_V1 | 75809 | 0.86137 | 68.87% | 34.52% | -0.09000 |
| RIDGE_PREFIX_V1 | 2859 | 1.42621 | 9.20% | 5.05% | 0.00000 |

Models, fold assignments, hashes, metrics, and fail-closed reference checks are in `analysis.json`; held-out rows are in `crossfit-predictions.jsonl.gz`.

Timing scope: MLP per-leaf timings are pure model-forward timings; input tensors and leaf indices are precomputed outside the timer.

Knowledge impact: benchmarked learned-scorer result only; no stable implementation or production-behavior change.
