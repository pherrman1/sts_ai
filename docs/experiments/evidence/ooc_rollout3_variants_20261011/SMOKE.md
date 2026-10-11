# Smoke: one seed per new setting (planning container)

2026-10-11 13:46:59Z–14:12:24Z, binary `3269ece9…` from `0ee840b1`, this folder's `run_unit.sh`, seeds 72000003–005
(not cohort seeds). The three smokes and the launch-gate rerun ran together, 4 units on 4 CPUs, which is the load a worker runs at.
`s4096` changes only the simulation count, which §424 already exercised, so it has no smoke. Every log's `[ooc-mcts-config]`
shows the arm's `wideningK`, `wideningAlpha` and `leafCombats`, `"simulations":2048`, the native leaf, the policy prior and the
production `combat_model`. Raw files: `/mnt/project-files/ooc-rollout3-variants/planning-gate-smoke.tar`.

| arm | seed | rc | won | floor | end HP | s/run | MCTS CPU s | owned / OOC decisions | support aborts | max depth |
|---|---|---|---|---|---|---|---|---|---|---|
| `rollout3 (gate)` | 70000000 | 0 | 1 | 51 | 46 | 1144 | 1046 | 118 / 130 | 9 | 4 |
| `r5` | 72000003 | 0 | 1 | 51 | 25 | 1524 | 1416 | 102 / 121 | 16 | 4 |
| `wbroad` | 72000004 | 0 | 1 | 51 | 60 | 1089 | 985 | 102 / 133 | 28 | 2 |
| `wnarrow` | 72000005 | 0 | 1 | 51 | 21 | 1094 | 1024 | 98 / 124 | 23 | 7 |

Expected cost (**Inference** from these runs and §422's 936 s mean per rollout3 run; the gate seed itself took 1,144 s here):
`s4096` about 2× rollout3, so about 1,900–2,300 s per run, 70–80 CPU-hours, about 2.5 h per worker; `r5` about 1,500 s per run,
about 55 CPU-hours, about 1.7 h per worker; `wbroad` and `wnarrow` about 1,100 s per run, about 40 CPU-hours each, about 1.2 h per
worker. Total about 210 CPU-hours over 32 workers.
