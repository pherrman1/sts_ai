# §441 smoke and pairing gate

Planning container, binary `8f5edf76…` built from `b039e846` ([binary.sha256](binary.sha256)), this directory's
`run_unit.sh` and `arm_env.sh`, 4 units in parallel, 1 thread each. Raw: `/mnt/project-files/ooc-uniform-441/smoke.tar`.

## Pairing gate: §433 `combo` seed 76000000 on this binary

The §433 unit (`ooc-rollout3-confirm/w01.tar`, binary `bab14cd5…`) rerun with `arm_env.sh combo` (§433 combo plus the
`STS_OOC_PUBLIC_FUTURES=0` pin):

- result row identical apart from `sec` (won 1, floor 51, end HP 33/80);
- OOC decision trace, MCTS action trace and MCTS support trace byte-identical;
- MCTS summary row identical apart from `mctsWallSec` and `mctsCpuSec`.

**PASS**: the §433 `combo`, `rollout3` and `off` units on 76000000–76000127 serve as paired controls. (`sec` 511 →
364 s, the §436/§437 speedups.)

## Smoke: `uniform` on 77009000–77009002

| seed | rc | won | floor | sec | OOC decisions | owned | V4 fallback | simulations |
|---|---|---|---|---|---|---|---|---|
| 77009000 | 0 | 1 | 51 | 477 | 138 | 105 | 33 | 215,851 |
| 77009001 | 0 | 0 | 33 (act 2 boss) | 263 | 82 | 69 | 13 | 149,535 |
| 77009002 | 0 | 1 | 51 | 507 | 134 | 110 | 24 | 234,576 |

Every log prints `[ooc-mcts-config]` with `"prior":"uniform"`, `"leafPolicy":"uniform"`, `"leafValue":"native"`,
`"leafCombats":3`, `"simulations":4096`, `"wideningK":4`, `"wideningAlpha":0.75` and
`combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native`. No `[bestbench-seed-failure]`.

Cost: about 420 s per run (the §433 `combo` arm took 1,536 s per run on the old binary), so a worker's 16 seeds take
about 30–60 min on 4 CPUs.
