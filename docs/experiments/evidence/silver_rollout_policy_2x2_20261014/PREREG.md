# Pre-registration (DRAFT, not frozen): Silver rollout policy × tree prior, A20, fight level

Status: **draft, not launched.** Written 2026-10-14 before any evaluation seed was played. Launch needs
Philipp's explicit go and a pre-launch independent review; the frozen SHA and inputs below are filled in at
freeze.

Philipp (2026-10-14, 21:24–21:26Z): "could we do that here? maybe its not worse and we can save some cpu?
maybe consider to do it with the gen 6 prior and without a prior ... no prior in the rollouts ... maybe test
how expensive it would be".

## Questions
1. **Primary:** does a uniform-random rollout policy (`STS_SILVER_ROLLOUT_UNIFORM=1`) give a CPU saving per
   simulation, and what does it cost in fight score, win rate and HP lost, against the greedy
   `SilverRolloutAgent` (default), at matched root states?
2. **Secondary:** does the gen-6 tree prior (model E, K = 8, weight 400, as §476) change the answer, for
   each rollout policy? (2×2: rollout {greedy, uniform} × tree prior {none, gen 6}.)
3. **Descriptive:** mean rollout length, CPU per simulation, and CPU per fight for each arm.

Out of scope: a prior that guides rollout actions. Cost is estimated in the write-up, not run (see Cost).

## Arms
Two budgets, each a full 2×2 (four arms per budget): `G-none`, `U-none`, `G-g6`, `U-g6`, at b in
{10000, 2500}. Primary contrasts are at 2500 (the CPU-cheap regime where a saving would matter); 10000 is the
production budget and is reported with the same labels.

- `G-*`: default greedy rollout (`SilverRolloutAgent`).
- `U-*`: uniform random legal action at every rollout step, including potions, END_TURN and card selects
  (`SilverSearcher::chooseUniformRolloutAction`, flag `STS_SILVER_ROLLOUT_UNIFORM=1`, code at commit
  `7aff01db` + `56ec049b`). The default path is byte-identical with the flag off.
- `*-g6`: gen-6 tree prior (`combat_policy_mlp_g6_E.txt`, sha256 `ca9bd7f2…3228`), K = 8, weight 400,
  settings as §476. `*-none`: no prior.

**Rollouts-per-leaf arms (added 2026-10-14 22:35Z, Philipp's card choice "Both"):** greedy policy with k
independent playouts averaged per leaf (`STS_SILVER_ROLLOUTS_PER_LEAF=k`, commit `d5e60d64`), at budgets that keep
the number of rollouts per decision equal to `G-none` at 2500: `G2-*` = k 2 at 1250 sims and `G4-*` = k 4 at 625
sims (with and without the gen-6 prior, as the harness pairs them). Secondary contrasts: `G2-none − G-none@2500`
and `G4-none − G-none@2500` (score, win rate, HP lost, CPU per fight). Smoke hint only (32 full A20 runs,
74071458–489, not evidence): k 4 at 625 matched k 1 at 2500 on mean floor (30.5 vs 30.5) at about 55% CPU;
k 1 at 10000 did not beat k 1 at 2500 there either, so full runs at that size do not resolve these arms.

**Process layout (no per-searcher option needed):** the rollout settings are process-wide, so each setting runs
as its own `ctmsilvergen` process on the same seeds: (UNIFORM 0, PER_LEAF 1, sims 10000,2500), (UNIFORM 1,
sims 10000,2500), (PER_LEAF 2, sims 1250), (PER_LEAF 4, sims 625). The coordinator reports that pairing holds
across processes because redraw and planner seeds depend only on (seed, fightIdx, k); the smoke checks it by
requiring every process's control replay to reproduce the same source fights. If it does not, the run is not
launched.

## Frozen inputs (to fill at freeze)
- Code: branch `claude/project-thread-8vmyta`, commit = freeze SHA (per-arm option commit on top of
  `56ec049b`), base main at freeze (main `8045737c` at drafting; #547 and #549 may have merged).
- Binary: `one_combat` Release, sha256 = TBD.
- Environment: as `silver_gen6_a20_sweep_476_20261014/env.sh` (§476), with `STS_CTMSILVER_ARMSET` set to the
  new armset name, and `STS_SILVER_ESCAPE_PENALTY` / ADR-0035 leaf terms at their defaults (pinned in the
  frozen env file; ADR-0036 escape penalty `12,35` if #549 has merged, else the default at freeze).
- Teacher: generated per binary with `tools/silver_synth_teacher.py <code sha> <one_combat> teacher.json`, then
  `ooc_policy` filled from `one_combat vwinrefreshpolicyspec` under the frozen env, as §476's `run.sh`
  (teacher_id `silver-flat-exact10k-synth-<sha8>`; `STS_EXECUTABLE_GIT_SHA` must equal the code sha).
- Seeds: run seeds **105000000–105000999** (coordinator block 105M, reserved; §479 for the write-up).
  Smoke seeds **74071450–74071457** already used (2026-10-14 CPU smoke, not evidence). Remaining smoke
  seeds: 74071458–74071499.
- Fight selection: as §476: all BOSS, ELITE and OTHER fights of each source run; NORMAL fights kept when
  `ctmSilverReplicateSeed(seed, fightIdx, 0, 0x4A11) % 3 == 0`. Source policy: plain Silver at 10k, A20.
- Replicates: R = 2 per arm on a shared redraw of the combat RNG, as §476.

## Metrics
- **Fight score** and pairing as §476/§460: per replicate 0 on death, else 53 + curHp + 11 potions +
  0.25 gold + 2 maxHp; arm value per fight = replicate mean.
- **Win rate** (1 − death share) and **HP lost** (preHp − post-combat curHp; a death loses all preHp).
- **CPU per simulation** per arm: process CPU of the fight divided by simulations executed (from the Silver
  tree profile, `STS_SILVER_TREE_PROFILE`).
- **Mean rollout length** per arm: rollout actions per rollout (tree profile rollout depth), and rollout calls
  per simulation.
- **CPU per fight** per arm, and the ratio to `G-none` at the same budget.
- Each fight in every arm is measured on the same root state (same source state, same redraw seed), so arm
  differences are not confounded by early deaths.

## Labels and analysis
Paired per fight, 95% bootstrap CI over source seeds (10,000 resamples, seed 0), as §476.

- **Primary (at 2500 sims, two labels):**
  - `U-none − G-none`, score: CI > 0 `UNIFORM_HELPS`, CI < 0 `UNIFORM_HURTS`, else `NOT_SHOWN`.
  - CPU per simulation ratio `U-none / G-none`: reported with its bootstrap CI, no label.
- **Secondary (descriptive):** the same contrast at 10000; `G-g6 − G-none` and `U-g6 − U-none` (prior effect
  under each policy); the 2×2 interaction `(U-g6 − U-none) − (G-g6 − G-none)`; win rate and HP lost for each
  contrast.
- Labels are reported per budget with no multiplicity correction; the write-up says so.
- With about 1,000 fights, `NOT_SHOWN` means inconclusive at this resolution.

**Decision rule (pre-set):** uniform is worth a follow-up only if `U-none − G-none` is not `UNIFORM_HURTS`
at 2500 **and** CPU per simulation for `U-none` is at most 0.5× `G-none` (a saving of at least half). Anything
else: greedy stays, and the result is recorded in the ledger as a negative. No default changes either way.
The prior arms are reported, not decision-bearing.

## Cost of a prior that guides rollouts (estimate, not run)
Not a tested arm. Estimate in the write-up: one gen-6 MLP call costs about 6–27 µs (`silver-prior-nn-cost`,
`silver-prior-arch-sweep`). The main engine does about 73k simulations/s on 4 vCPUs (§360), so a whole simulation
is about 14 µs. A prior call per rollout step therefore costs roughly one to two orders of magnitude more per
simulation than the simulation itself. This estimate is an inference, not a measurement.

## Validity
A shard rc != 0 or a sha mismatch is reported, not rerun with changed settings. A fight with fewer than R = 2
replicates in some arm is excluded and counted by reason. The control replay must reproduce the source fight.
The run is launched detached and watched as §476 (background watcher re-armed; container loss rerun
unchanged into a fresh folder).

## Write-up
Ledger entry (next free §, check main's ledger first), this file with freeze SHA and analysis output, the raw
tar sha256 on `/mnt/project-files/silver-rollout-2x2/`, checked from a second container before citing.
