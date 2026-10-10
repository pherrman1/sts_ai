# OOC MCTS root selection × cpuct screen (pre-registration, 2026-10-09)

Written before any cohort seed ran. Authorized by Philipp (2026-10-09 17:42Z, thread "New CTM stack"):
"do a paired screen pls on 128 seeds … Normal vs pick by Q … change puct, select 4 different values for both
normal and pick by Q", about 30 min wall.

## 1. Question

In the #418 live A/B (§412), OOC MCTS picks the most-visited root action, and with cpuct 1.5 the visits follow the V4
prior because Q gaps between options are ~0.01 while the prior bonus is ~0.03–0.04. On seed 63000084 the search's own
Q preferred a different option at several roots (Neow, F8 card, F11 path, F12 shop). Does picking the root action by
mean Q, and/or a different cpuct, win more runs than the current setting?

## 2. Arms (all paired on the same seeds)

Base = the §412 `cand` arm verbatim: OOC MCTS on, new CTM pathb-r2 (candidate files + manifest env), 2048 sims,
early stop on, V4 prior (temperature 1), screen-GBM leaf, leaf combats 0, widening 2/0.5, depth 32, fair native
Silver exact 10k real combat, Ironclad A0, stop after Act 3 boss. Only two settings vary:

| Arm | Root selection | cpuct |
|---|---|---|
| v05 / v10 / **v15** / v30 | visits (current) | 0.5 / 1.0 / **1.5 (current = control)** / 3.0 |
| q05 / q10 / **q15** / q30 | mean Q (`STS_OOC_MCTS_ROOT_SELECTION=q`) | 0.5 / 1.0 / 1.5 / 3.0 |

With Q selection the planner skips the visit-lock early stop (`OocMctsPlanner.cpp:232`), so Q arms always spend the
full 2048 sims per root; this is part of the treatment. Unvisited actions are never picked (`:298`).

## 3. Seeds, binary, inputs

* Cohort `65000000..65000127` (128 seeds, fresh; assigned by the coordinator). Smoke seed `65009000`.
* Binary: `one_combat` built from `648334e38dc5c92bc57a9b531f2f9f3308a732ff` (the §412 build), sha256
  `dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169`; each worker builds it and checks the hash.
* Candidate CTM files from `/mnt/project-files/ctm-pathb/live-ab-cloud/candidate/` (FAST `90806c25…`, STD1 `b9188de0…`,
  manifest `d9d8377e…`), as in §412. Model hashes are listed in `worker.sh`.
* Every unit runs through `tools/seed_guard.sh`, one thread per process.

## 4. Execution

32 cloud workers × 4 CPU. 512 units of 2 seeds (64 blocks × 8 arms, frozen order in `worker.sh units_all`); unit i goes
to worker `i mod 32 + 1`, 16 units per worker, 4 at a time. Outputs are written locally and copied to
`/mnt/project-files/ooc-mcts-q-select-screen/wWW/` when a unit ends (no appends on the share). Worker 1 first runs the
smoke (all 8 arms on seed 65009000; checks rc 0, one CSV row, banners for cpuct and root selection, the candidate line,
and `analyze.py check`). Every worker's `run` waits for `SMOKE_PASS` and stops on `SMOKE_FAIL`. Estimated cost:
~122 s/run for visits arms and ~180 s/run for Q arms (§412 cand CPU, MCTS part doubled), ~43 CPU-hours, ~20–25 min
of running after a ~5 min build.

A Silver stall caught by bestbench (`[bestbench-seed-failure]`) or a timeout loses those seeds; they are not rerun or
replaced. Any other failure stops the worker and is reported.

## 5. Analysis (frozen `analyze.py`, stdlib only)

* **Primary:** paired win-rate difference `q15 − v15` on seeds complete in both arms. 95% CI from a paired bootstrap
  over seeds (10,000 resamples, RNG seed 20261009), exact McNemar p.
  * `Q_BETTER` if the CI lower bound > 0, `Q_WORSE` if the upper bound < 0, else `NO_DIFFERENCE_DETECTED`.
  * `_INCOMPLETE` is appended if any arm misses more than 5% of the 128 seeds.
* **Secondary (screen):** every other arm minus `v15` the same way, plus mean floor difference. An arm whose CI lower
  bound is above 0 is flagged `CI_ABOVE_0` and listed as a confirmation candidate. With 7 comparisons and the best arm
  picked after the fact, a flag is a reason for a fresh-seed confirmation run, not for a default change.
* **Descriptive:** per-arm win rate, mean floor, mean HP of won runs, boss deaths by act, non-boss deaths, CPU s/run.

## 6. Decision rule

No default changes from this screen (OOC MCTS is off by default, ADR-0027). If the primary is `Q_BETTER` or any arm is
`CI_ABOVE_0`, the next step proposed to Philipp is a confirmation of that one arm vs `v15` on fresh seeds. Otherwise
the result is recorded as negative or inconclusive in the ledger.
