# §451 smoke

Planning container (4 CPUs), binary `015c90e2…` built from `19cfc1ae` ([binary.sha256](binary.sha256)), this
directory's `run_unit.sh` and `arm_env.sh`, 6 units 4 at a time. Seeds 83009000–83009001, not in the cohort.

| arm | seed | rc | won | floor | end HP | sec | OOC decisions | owned | fallback | simulations | particle revisits | MCTS CPU s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s8192 | 83009000 | 0 | 1 | 51 | 38/80 | 1,679 | 127 | 124 | 3 | 540,772 | 220,863 | 1,578 |
| s8192 | 83009001 | 0 | 1 | 51 | 31/51 | 1,363 | 133 | 130 | 3 | 567,758 | 225,623 | 1,280 |
| wide | 83009000 | 0 | 1 | 51 | 63/100 | 724 | 128 | 125 | 3 | 270,430 | 0 | 624 |
| wide | 83009001 | 0 | 1 | 51 | 41/82 | 750 | 142 | 139 | 3 | 295,299 | 0 | 680 |
| combo | 83009000 | 0 | 0 | 33 | 0/80 | 512 | 84 | 82 | 2 | 181,466 | 57,563 | 467 |
| combo | 83009001 | 0 | 1 | 51 | 48/98 | 807 | 142 | 139 | 3 | 304,462 | 96,283 | 731 |

- Every log prints `[ooc-mcts-config]` with `"prior":"policy"`, `"leafPolicy":"v4"`, `"leafValue":"native"`,
  `"leafCombats":3`, `"wideningAlpha":0.75` and the arm's `"simulations"` (8192 / 4096 / 4096) and `"wideningK"`
  (4 / 8 / 4). No `[bestbench-seed-failure]`. Each unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8`.
- `wide` has zero particle revisits (outcome particles = simulations), as computed in the PREREG.
- OOC decision traces first differ from `combo` at line 9 / 41 (`s8192`) and 8 / 36 (`wide`), so both settings
  reach play.
- Cost: `s8192` about 1,500 s per run, `wide` and `combo` about 750 s. A worker's 48 units take about 3.3 h on
  4 CPUs; 384 runs ≈ 105 CPU-hours.
