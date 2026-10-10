# Pre-registration: rollout3 OOC MCTS replication on the current stack (ledger §422)

Written and committed before any cohort seed ran. Re-frozen before the review to move seeds from 69100000–127 (smoke 69109000, stopped unfinished) to 70000000–127: the first range overlaps the V4 gold data run (69100000–69124999). Philipp's go: 2026-10-10 19:36Z, the
"128 pairs, cloud" option on the decision card "Run the rollout3 replication on 128 paired seeds
across cloud workers?" in project thread "OOC MCTS 10-floor depth feasibility".

## Question

§277 (2026-09-15, source `48fae046`, V2 CTM, seeds 12003000–031): OOC MCTS with the V4 policy prior,
2048 simulations and a native `v_win` leaf after 3 additional CTM combats ("rollout3") won 28/32,
against 24/32 for V4 without MCTS (+12.5 pp, paired CI [−3.1, +28.1], PROMISING_INCONCLUSIVE).
Since then the CTM changed (#468, pathb-r2 with escape) and the default stack without MCTS wins about
78% (§384, §411). Does rollout3 on the current stack win more runs than the current default (MCTS off)?

Context for the design (not evidence): on 4 fresh seeds (69000005–008, this branch's base plus a
diagnostic-only local patch) rollout3 won 4/4 at 817–1960 s per run on one CPU, with 4–22% of
decisions falling back to V4 after support aborts. §391's boss-rollout leaf failed because a 0/1
boss-survival value is saturated (act-1 root Q ≈ 0.997) and noisy; rollout3's `v_win` leaf does not
have that problem by construction.

## Arms ([arm_env.sh](arm_env.sh))

Shared: the §411 / #418 live base (Ironclad A0, fair RNG, exact-10k Silver live combat, allocated reuse,
adaptive and learned stop off, V4 OOC policy with all strategic gates and margin 1.0, keys off,
`STS_REST_WIN=0`, act-3 stop, default `v_win`/`v_rich` models).

| arm | setting |
|---|---|
| `off` | `STS_OOC_MCTS=0` (current default stack) |
| `rollout3` | §277 profile unchanged: `SIMS=2048`, `LEAF_COMBATS=3`, `LEAF_VALUE=native`, `LEAF_POLICY=v4`, `PRIOR=policy`, temperature 1, cpuct 1.5, widening 2/0.5, `MAX_DEPTH=32`, visits root selection, `EARLY_STOP=1`; combat model = current production CTM default (#468) |

## Differences from §277 (besides the CTM)

The control is the §411 / #418 research base (flat exact-10k Silver, V4 OOC policy), not the
production defaults (which use learned stopping). Relative to §277:

| | §277 (2026-09-15, `48fae046`) | this replication |
|---|---|---|
| combat model in imagination | V2 CTM (`combat_transition_near_full_except_smoke_v2`) | production pathb-r2 stack with escape (#468) |
| hidden noncombat futures in search | copied simulator RNG | sampled futures (`sampleNoncombatFuture`, live default since 2026-09-20) |
| campfire rest | win-rate rest (`STS_REST_WIN` unset, the default then) | `STS_REST_WIN=0` (default rest) |
| OMP threads per process | 12 | 1 |
| control | V4, MCTS off | MCTS off on the same base (flat exact-10k Silver) |

Lizard Tail: states with an active, unqualified Lizard Tail abort the root to V4 (fail closed), as in
§277's code. In the smoke all 75 support aborts were Lizard Tail aborts. Per-seed fallback share and
Lizard Tail abort counts are reported descriptively; the replication tests rollout3 as it actually runs.

## Provenance

- Code commit `cd405b4c` (main; [CODE_COMMIT](CODE_COMMIT)); each worker builds `one_combat` itself
  (Release preset, GCC 13.3) and refuses to run unless the sha256 equals [binary.sha256](binary.sha256).
  Models are the tracked files at that commit.
- Seeds 70000000–70000127 (fresh), 16 blocks of 8. Worker W = 1..16 runs block W−1 in both arms
  ([worker.sh](worker.sh), [run_unit.sh](run_unit.sh)). Smoke seed 70009000 (not in the cohort), run once
  in the planning container before launch.
- Expected CPU (Inference from the 4-seed look): rollout3 ≈ 1,350 s/run, off ≈ 100 s/run;
  ≈ 52 CPU-hours total, about 50 min per 4-CPU worker after the build.
- Per-unit timeout 6 h. Silver stalls in live combat are caught per seed by `bestbench`
  (`[bestbench-seed-failure]`); such seeds drop out of the pair. No seed is rerun or replaced.

## Analysis ([tools/analyze_rollout3_replication.py](../../../../tools/analyze_rollout3_replication.py))

Pairs: seeds with a result row in both arms. **Primary:** Δwin = win(rollout3) − win(off), paired seed
bootstrap 95% CI (10,000 resamples, seed 422).

- **REPLICATED** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

Descriptive: exact McNemar p, Δfloor (CI), Δ end HP, boss deaths per arm, seconds per run, rollout3
MCTS CPU, ownership/fallback share (overall and per seed), support aborts and Lizard Tail aborts per
seed, simulations per run. The script refuses a label (INVALID) when a cohort seed is missing from
either arm or a unit failed, unless the gap is a listed `[bestbench-seed-failure]` seed.

**Reading.** 128 pairs resolve about ±8 pp. REPLICATED would justify improvement screens (uniform
prior, outcome merging, no early stop; one variable at a time on these seeds) and a confirmation
before any default change. NOT_SHOWN does not show the arms are equal.

## Validity

All 160 units rc=0 apart from listed per-seed stall failures; any other nonzero rc, crash or missing
unit makes the result INVALID until explained. Every rollout3 log prints `[ooc-mcts-config]` with
`"leafValue":"native"`, `"leafCombats":3`, `"prior":"policy"`, `"simulations":2048` and the production
combat model `selfplay/models/combat_transition_deepsets_pathb_r2.native`; no `off` log enables OOC MCTS.

## Decision

Descriptive replication. No default change; OOC MCTS stays off whatever the label. Philipp decides.
