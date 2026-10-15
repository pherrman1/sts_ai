# §486 heart1 out-of-combat policy vs our V4 OOC stack, same combat, paired by seed (pre-registration, 2026-10-15)

Philipp, 2026-10-15 08:21Z: "Open a new thread which takes care of testing the heart1 adapter with our framework".
Accepted design: `/mnt/project-files/az-loop-research/RECOMMENDATION.md` stage 1b ("a paired 128-seed A20 A/B:
heart1 OOC + our default Silver vs our `off` stack, floors primary, wins secondary. IMPROVED → heart1 becomes the
OOC base policy and the prior for stage 2"). Frozen with the run commit, binary hash and weights hash before launch;
independent pre-launch review. The seed counts below are this prereg's proposal; Philipp sets the final counts.

## What is known (baseline)
- heart1 is daniel-ziegler's released PPO out-of-combat policy for silverbot (`heart1.pt`, sha256 `deaba59d…`).
  In its own engine (their `eval_hero`, 10k sims, temperature 0, their seeds) it cleared act 3 in 64/200 A20 games
  (32.0% [25.9, 38.8]) and killed the Heart in 43/200; at A0 (1000 sims) 86/100 Heart kills
  (`/mnt/project-files/az-loop-research/heart1-repro/`). Reached act 3 in 116/200 (58%) at A20.
- Our A20 reference is §457 `off` (the control here, older code): 9/128 act-3 clears, mean floor 32.5, 55/128
  reached act 3. §458 `combo_liz` (OOC MCTS with the A20 CTM, ~11x CPU): 12/128, floor 38.5.
- **Inference:** that comparison is unpaired, across engines and Silver versions. The act-3 gap (heart1 55% clears
  given act 3 reached vs ours ~17%) is the effect this run tests in our engine.
- The adapter (#552, `apps/one_combat/heart1_policy.{h,cpp}`, KB `architecture/out-of-combat.md` "heart1 policy
  adapter") is a native port with checked logit parity on early-game states. Known engine differences heart1
  sees through it are listed in that KB section (the Neow transform curse is fixed on main by ADR-0038).

## Hypotheses
- H1: heart1 as the OOC decision-maker reaches further at A20 than our V4 OOC stack with combat held fixed
  (mean paired floor difference > 0).
- H2 (key secondary): heart1 clears act 3 more often at A20.
- H0 alternatives this run cannot separate: heart1's advantage in its own engine came from engine differences
  (Silver version, rules), or from policy-engine co-adaptation that does not transfer.

## Arms (paired by seed, same binary, `arm_env.sh`)
- `v4` (control): the §457 `off` environment, copied literally (exact-10k Silver via the bestbench budget, V4 OOC
  gates on rest/event/shop/treasure/boss relic at margin 1.0, `STS_COLLECT_KEYS=0`, `STS_REST_WIN=0`,
  `STS_STOP_AFTER_ACT=3`, `STS_OOC_MCTS=0`, `STS_OOC_PUBLIC_FUTURES=8`). Every other setting is the binary's
  default on the run commit (ADR-0030..0038 defaults ON).
- `heart1`: the same environment plus `STS_OOC_HEART1=heart1.bin` (native export, sha256 `1e92f2a6…`, identical to
  the adapter thread's export; `heart1_weights.txt`). heart1 decides every OOC screen it encodes (gold and
  key-less relic rewards are taken first, as silverbot does); screens it does not encode fall back to the same
  chain as `v4`. Combat is the same Silver in both arms.
- Keys: heart1 is offered keys as in silverbot (Recall, emerald, sapphire) whatever `STS_COLLECT_KEYS` says; with
  the act-3 stop the keys bring no Act 4, so collecting them is a pure cost heart1 pays. **Inference:** this biases
  the test slightly against heart1; it is part of the policy as released.
- A20 Act 3 has two bosses; the act-3 stop waits for the second (`run_driver.cpp`). `won` = act-3 cleared.

## Seeds and runs
- Proposed cohorts (`COHORTS`): A20 seeds 107000000–107000511 (512), A0 seeds 107001000–107001255 (256). One
  `bestbench 10000 1 ASC SEED` unit per seed and arm through `tools/seed_guard.sh` (`run_unit.sh`). Cloud workers
  per `worker.sh` (`NWORKERS`), each running a contiguous block of every cohort, 4 units at a time.
- Smokes: 74071950–74071963 in this thread (A20 74071950–959, A0 74071960–963, both arms); raw in
  `smoke.tar.gz`.
- Stalls: a native Silver stall is a `[bestbench-seed-failure]` (rc 1, no row). Such a seed is dropped from both
  arms and listed; any other gap or nonzero rc makes that ascension INVALID (`tools/analyze_heart1_ab_486.py`).
  The analysis is also INVALID unless every `heart1` log shows `[heart1] loaded` and no `v4` log does.

## Analysis (`python3 tools/analyze_heart1_ab_486.py report.json DIR...`)
- **Primary (A20):** mean paired floor difference heart1 − v4, paired seed bootstrap 95% CI (10,000 resamples, RNG
  seed 486 + ascension). **IMPROVED** if the lower CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise.
- **Key secondary (A20):** act-3 clear difference with its CI (same resample indices, same three labels),
  discordant pairs and exact McNemar p.
- **Secondary (A0):** the same two statistics, reported with their labels; no decision rests on A0 alone.
- Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds per run, and
  the share of OOC decisions heart1 took (trace `by`; smoke: 100% of decisions on the screens seen).
- No multiplicity correction; all statistics are reported.

## Decision rule
- A20 floors IMPROVED → heart1 is the OOC base policy and tree prior for stage 2 (fine-tuning in our loop), as
  the accepted plan says. Whether `STS_OOC_HEART1` becomes a default is Philipp's separate call; this run does not
  change any default by itself.
- A20 floors NOT_SHOWN but clears IMPROVED → report as such; Philipp decides on stage 2.
- WORSE or NOT_SHOWN on both → heart1 does not transfer to our engine as is; the ledger records the negative
  result, and stage 2-alt of the plan applies.

## Smoke (descriptive only; no decision rests on it)
- 36 units, all rc=0, both arms at both ascensions: 28 on `a1c8de59` (A20 74071950–959, A0 74071960–963) and 8 on
  the run code `59bb91a` (A20 74071964–966, A0 74071967). heart1 took 99.2% and 100% of OOC decisions on
  `a1c8de59` (10 Match and Keep screens fell back to the chain) and 100% on `59bb91a`. Every heart1 log shows
  `[heart1] loaded`, no v4 log does.
- A20 act-3 clears: heart1 8/13, v4 2/13; A0: heart1 5/5, v4 4/5. **Inference:** a large effect is plausible,
  but 13 seeds say nothing reliable.
- `won` with the act-3 stop: a cleared A20 run ends at floor 52 in both arms; heart1 rows show act 4 (it holds
  the keys, so the game moves to Act 4 before the stop), v4 rows act 3. Floors are comparable.

## Cost (smoke, 4 units at a time on 4 cores)
- Seconds per run: A20 v4 ~41, heart1 ~103; A0 v4 ~62, heart1 ~127. heart1 runs are longer, and a cleared heart1
  run took 101–176 s against 64–82 s for v4's clears (**Unverified** why: longer runs, slower decisions, or
  both; not profiled).
- Proposed cohorts: 512 × (41 + 103) + 256 × (62 + 127) ≈ 122k core-s ≈ 34 core-h. On 16 workers (4 cores each)
  about 32 min of runs per worker plus ~10 min build; on 8 workers about 65 min.
