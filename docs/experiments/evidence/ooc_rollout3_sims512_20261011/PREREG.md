# Pre-registration: rollout3 OOC MCTS at 512 simulations (ledger §424)

Written and committed before any cohort seed ran at 512 simulations. Philipp's go: 2026-10-11 09:04Z, "continue,
lets do 512 sims" in project thread "OOC MCTS 10-floor depth feasibility", answering the suggested next step after
§423 (a cheaper budget, because rollout3 costs about 16x CPU).

## Question

§422: rollout3 (2048 simulations) won 115/128 vs 101/128 for MCTS off (+10.9 pp [+2.3, +19.5]) at 936 vs 57 s per
run. Does rollout3 with a quarter of the simulations still beat MCTS off, and how much of the 2048-simulation result
does it keep?

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting | runs |
|---|---|---|
| `r512` | §422 `rollout3` environment unchanged (its `arm_env.sh` is sourced; production pathb-r2 CTM, V4 prior, `LEAF_COMBATS=3`, native leaf, early stop on), except `STS_OOC_MCTS_SIMS=512` instead of 2048 | new, this run |
| `off` (control) | §422 MCTS off, seeds 70000000–127 | existing |
| `rollout3` (secondary control) | §422 rollout3 at 2048, seeds 70000000–127 | existing |

Controls come from `/mnt/project-files/ooc-rollout3-replication/wNN/`, checked against §422's `data-sha256.txt`.
Reusing them is valid because the binary, seeds and all other environment variables are the same, and the §423 launch
gate showed a §422 rollout3 seed reruns byte for byte in another container
([RERUN-422-70000000.md](../ooc_rollout3_lizard_20261010/RERUN-422-70000000.md)). Early stop stays on as in §422: the visit lock
(`OocMctsPlanner::search`, `rootWinnerLocked(node, remaining)`) stops a search once the leading root action can no
longer be overtaken within the remaining budget, so it is defined relative to whatever budget is set.

## Provenance

- Code commit `cd405b4c` ([CODE_COMMIT](CODE_COMMIT)); the run commit may differ from it only in docs, tools and models
  this arm does not load ([worker.sh](worker.sh) refuses otherwise). Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256) (`39cdac96…`).
- Seeds 70000000–70000127 (the §422 cohort, reused on purpose for pairing). 8 workers; worker W runs seeds
  70000000+16(W−1) .. +15 as one-seed `r512` units, 4 at a time.
- Smoke (planning container, same binary, this `run_unit.sh`): seed 72000002 rc=0, won, 297 s, banner
  `"simulations":512` and the production `combat_model`; 107/133 decisions owned, 23 support aborts (Lizard),
  202 s MCTS CPU. Files: `/mnt/project-files/ooc-rollout3-sims512/smoke/`.
- Expected CPU (**Inference** from §422: 850 s MCTS of 936 s per run): about 300 s per run, about 11 CPU-hours, about
  20 min per 4-CPU worker after the build.
- Per-unit timeout 6 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop
  out of the pairs. No seed is rerun or replaced.
- Output only to `/mnt/project-files/ooc-rollout3-sims512/wNN/`.

## Analysis ([tools/analyze_rollout3_sims.py](../../../../tools/analyze_rollout3_sims.py))

Pairs: cohort seeds with a result row in `r512` and both §422 arms. **Primary:** Δwin = win(r512) − win(off), paired
seed bootstrap 95% CI (10,000 resamples, seed 424).

- **GAIN_KEPT** if the CI lower bound > 0;
- **WORSE_THAN_OFF** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** Δwin = win(r512) − win(rollout3 at 2048) with its CI, flagged `within_5pp_of_2048` when
its lower bound > −5 pp. Also exact McNemar p, Δfloor (CI) and Δ end HP for both comparisons, boss deaths, seconds per
run, MCTS CPU, owned and fallback share, support aborts and simulations per run.

**Reading.** 128 pairs resolve about ±8 pp against off. GAIN_KEPT at about a third of the CPU would make 512 the
budget for any later confirmation. NOT_SHOWN does not show the gain is gone; the secondary comparison then says how far
below 2048 the point estimate fell.

## Validity

- All 128 units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained. Every §422 file the analysis reads must match §422's `data-sha256.txt`.
- Every `r512` log prints `[ooc-mcts-config]` with `"simulations":512`, `"leafValue":"native"`, `"leafCombats":3`,
  `"prior":"policy"` and the production `combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native`.

## Decision

Descriptive screen. No default change whatever the label: OOC MCTS stays off. Philipp decides what comes next.
