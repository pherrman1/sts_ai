# PG16H24 stuck games (force-stalled), for replay analysis (Philipp 2026-11-15 10:52 CET)
Each game is deterministic given seed, iteration (sample salt = iteration), net net-(iteration-1) and config.json env.
Replay: ppo_loop.start_actors with config env, net, it, seed (see scratchpad sentinel.py pattern in the PG16H24 author thread).
| iteration | worker | seed | net | runtime at stall | RSS | binary | note |
|---|---|---|---|---|---|---|---|
| 6 | W1 | 112103120 | net-0005 (PC only) | >4 h | 6.5 GB | 97aec5b5 | 11-14 |
| 7 | W9 | ~112103744 | net-0006 (PC only) | >3 h | ? | 97aec5b5 | 11-14 |
| 31 | W37 | ? (meta manual_stall_seed) | net-0030 (PC only) | 3h39m | 8.6 GB | dae7894a | 11-15 |
| 33 | W34 | 112117590 | net-0032 (here) | >2.5 h | 7 GB | 97aec5b5 | 11-15 |
| 39 | W26 | 112120607 | net-0038 (here) | 1h36m | ? | dae7894a | 11-15, 1 h rule (Philipp). ps showed 112120605 = part's first seed (bestbench arg), the stuck one is 112120607 (only seed without a game line). fsp's reason text says "> 4 h" (hard-coded). |
