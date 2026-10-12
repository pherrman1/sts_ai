# §449 smoke

Planning container, binary `85b1482b…` built from `94f78fbb` ([binary.sha256](binary.sha256)), this directory's
`run_unit.sh` and `arm_env.sh`, 4 units in parallel (one per CPU). Seeds 82009000–82009001, not in the cohort.

| arm | seed | rc | won | floor | end HP | sec | OOC decisions | owned | fallback | simulations | MCTS CPU s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vwin | 82009000 | 0 | 1 | 51 | 39/87 | 835 | 133 | 130 | 3 | 282,096 | 774 |
| x2bpub | 82009000 | 0 | 1 | 51 | 44/106 | 810 | 123 | 120 | 3 | 242,593 | 701 |
| vwin | 82009001 | 0 | 1 | 51 | 8/80 | 824 | 125 | 121 | 4 | 240,292 | 726 |
| x2bpub | 82009001 | 0 | 1 | 51 | 27/80 | 729 | 116 | 112 | 4 | 214,601 | 640 |

- Every log prints `[ooc-mcts-config]` with `"prior":"policy"`, `"leafPolicy":"v4"`, `"leafValue":"native"`,
  `"leafWinModel":null`, `"leafCombats":3`, `"simulations":4096`, `"wideningK":4`, `"wideningAlpha":0.75` and
  `combatModel` `pathb_r2_lizard` with the near-full brew fallback. No `[bestbench-seed-failure]`.
- Each unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8` and its arm's `STS_WIN_NET`. The OOC decision traces of the two
  arms first differ at line 3 on both seeds, so the swapped model reaches play.
- Cost: about 800 s per run, so a worker's 32 units take about 1.8 h on 4 CPUs; 128 pairs ≈ 57 CPU-hours.
