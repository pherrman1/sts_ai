# §459 smoke

Planning container, binary `16426481…` built from `440cf556` ([binary.sha256](binary.sha256)), this directory's
`run_unit.sh` and `arm_env.sh`, 4 units in parallel (one per CPU). Seeds 74050003–74050004, not in the cohort.

| arm | seed | rc | won | floor | end HP | sec | OOC decisions | owned | fallback | simulations | MCTS CPU s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| planner | 74050003 | 0 | 1 | 51 | 47/97 | 377 | 116 | 113 | 3 | 207,838 | 308 |
| greedy | 74050003 | 0 | 1 | 51 | 31/97 | 407 | 118 | 115 | 3 | 218,770 | 328 |
| planner | 74050004 | 0 | 1 | 51 | 44/127 | 635 | 124 | 121 | 3 | 263,619 | 539 |
| greedy | 74050004 | 0 | 1 | 51 | 69/132 | 598 | 125 | 122 | 3 | 268,087 | 508 |

- Every log prints `[ooc-mcts-config]` with `"leafValue":"native"` … `"simulations":4096` and
  `[native OOC shop deck-size correction ON]`; only the `greedy` logs carry `rollout_shop=greedy`. No
  `[bestbench-seed-failure]`.
- Each unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8`, the pinned `STS_WIN_NET`, `STS_OOC_SHOP_DECK_SIZE_FIX=1` and
  its arm's `STS_OOC_MCTS_ROLLOUT_SHOP`. The OOC decision traces of the two arms first differ at line 18 on both
  seeds, so the option reaches play.
- Cost: about 400–640 s per run, so a worker's 32 units take about 1–1.5 h on 4 CPUs; 128 pairs ≈ 40 CPU-hours.
