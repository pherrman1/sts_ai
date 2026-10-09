# Pre-registration: OOC MCTS with a Silver combat resolver vs the CTM (ledger §411, pilot)

Renumbered from §410 after the freeze (§409 went to #467, so the Run 2 CTM scoring became §410). The
harness scripts and `tools/analyze_silver_resolver_pilot.py` keep the old label in their comments so that
the frozen scripts stay byte-identical. The workers ran the later run commit `a516b884` (16-worker
layout, committed before any cohort seed ran).

Written and committed before any cohort seed ran. Philipp's go: 2026-10-09 15:30Z ("Yes do that. But maybe do
matched CPU and matched ooc Simulations for the second check"), replying to the §408 follow-up offer of a
matched-CPU OOC MCTS gameplay pilot with a Silver combat resolver. The cohort size and worker count below
are put to him before launch.

## Question

§408: low-sim Silver forecasts fight outcomes better than the production CTM on every field, but costs
about 37x (prior 64) per forecast. Inside live OOC MCTS, does resolving imagined combats with Silver
instead of the CTM win more runs (a) at the same number of OOC simulations and (b) at the same MCTS CPU?

## Resolver (code `f533ac8e`)

`STS_OOC_MCTS_COMBAT_RESOLVER=silver` makes `SilverCombatTransitionSampler` the OOC MCTS combat model
(`apps/one_combat/ooc_mcts_adapter.cpp`). For each imagined combat it:
- copies the imagined pre-combat state and redraws its six combat RNG streams (ai, cardRandom, misc,
  monsterHp, potion, shuffle; counters kept) from the planner RNG, so the real hidden future never reaches
  the planner (fair play);
- plays the combat with native Silver at `STS_OOC_MCTS_SILVER_SIMS=64` simulations per root, flat budget,
  root prior v1 w400 on (thread override), planner seed from the planner RNG;
- returns DEATH, VICTORY or ESCAPE (Smoke Bomb) with the RAW post-combat state, which the adapter applies
  exactly as a CTM sample. A Silver failure returns UNSUPPORTED, which aborts that search to the V4 fallback
  (counted as a support abort).
Live combats stay plain exact-10k Silver: `STS_SILVER_ROOT_PRIOR_SCOPE=override` keeps the loaded prior
off unless the resolver's thread override turns it on.

Pre-run checks (seed 64009000, not in the cohort): an `off` run with and without the prior environment
(`STS_SILVER_ROOT_PRIOR` + `SCOPE=override`) produced a byte-identical decision trace and result row;
the resolver ran a whole run at 64 and 2048 OOC simulations with no support abort.

## Arms

All MCTS arms use the #418 / §384 `prod` settings (cpuct 1.5, visits root selection, early stop, V4 prior
and leaf policy, widening 2/0.5, depth 32, `screengbm` leaf, leaf combats 0) and differ only as listed.
Shared environment and commands: [arm_env.sh](arm_env.sh), [run_unit.sh](run_unit.sh),
[worker.sh](worker.sh).

| arm | combat model | OOC simulations | role |
|---|---|---|---|
| `prod` | production CTM stack (automatic default) | 2048 | baseline |
| `silv2048` | Silver resolver, 64 sims + prior | 2048 | **matched OOC simulations** |
| `silvcpu` | Silver resolver, 64 sims + prior | S_cpu (below) | **matched MCTS CPU** |
| `off` | MCTS off (flat exact-10k Silver, V4 policy) | – | reference |

**S_cpu calibration (frozen before the cohort).** On seed 64009000, MCTS thread CPU per OOC simulation
(`mctsCpuSec / simulations` from `STS_OOC_MCTS_TRACE`) was 0.3332 ms for `prod` (37.47 s / 112,461) and
4.152 ms for `silv2048` (467.3 s / 112,542). S_cpu = round(2048 × 0.3332 / 4.152) = **164**. Both runs won
with 36 HP, 113 owned decisions, ~22,000 imagined combats each. Their trace rows are
[calibration-prod.mcts.csv](calibration-prod.mcts.csv) and
[calibration-silv2048.mcts.csv](calibration-silv2048.mcts.csv). The calibration binary differed from
`f533ac8e` only in one startup banner line. Calibration ran on a shared 4-CPU
container next to other jobs, so the match is approximate; the realised MCTS CPU per run of each arm is
reported.

## Cohort and budget

- Seeds 64000000–64000127 (128 runs per arm, fresh), 16 blocks of 8. Philipp chose (16:08Z) 16 cloud
  workers × 4 CPU: worker W = 1..16 runs block W−1 in all four arms, `silv2048` as four units of 2 seeds.
  Smoke seed 64009001 (run once before launch, in the §408 thread's container).
- Each worker builds the binary itself (sha256 in [binary.sha256](binary.sha256)).
- Expected CPU per run (smoke, Inference): `prod` ≈ 135 s, `silvcpu` ≈ 135 s, `off` ≈ 55 s, `silv2048`
  ≈ 565 s. Total ≈ 32 CPU-hours, about 35–45 min per worker after a ~25 min build.
- Per-unit timeout 6 h. Silver stalls in live combat are caught per seed by `bestbench`
  (`[bestbench-seed-failure]`); such seeds drop out of every pair that needs them. No seed is rerun or
  replaced.

## Analysis ([tools/analyze_silver_resolver_pilot.py](../../../../tools/analyze_silver_resolver_pilot.py))

Pairs: seeds with a result row in both arms. Primary comparisons:
1. `silv2048 − prod` (matched OOC simulations);
2. `silvcpu − prod` (matched CPU).

Per comparison: Δwin (act-3 boss cleared) with a paired seed bootstrap 95% CI (10,000 resamples, seed
410) and an exact two-sided McNemar test on discordant pairs. Label: A_BETTER if CI lower bound > 0 and
p < 0.05; B_BETTER for the mirror; else NO_DIFFERENCE_DETECTED. Secondary: Δfloor (CI), boss deaths, MCTS
CPU per run, simulations and combat samples per run, support aborts. Descriptive: `silv2048 − silvcpu`,
and each MCTS arm − `off` (does any MCTS arm beat plain play?).

**Reading.** This is a pilot: 128 pairs resolve about ±10 pp. Only a Silver arm labelled A_BETTER
against `prod` would justify a confirmation. NO_DIFFERENCE_DETECTED on `silvcpu − prod` means retiring
the CTM would not cost wins at equal CPU in this pilot; it does not prove equivalence.

## Validity

- All 112 units rc=0 apart from per-seed stall failures, which are listed. Any other nonzero rc, crash or
  missing unit makes the affected comparison INVALID.
- Every `silv*` log names the resolver banner (`silver_sims=64`, `scope=override`); no `prod` log does, and
  `prod` logs name the production CTM artifact.

## Decision

Descriptive pilot. No default changes; OOC MCTS stays off and the CTM is not retired by this entry.
Philipp decides.
