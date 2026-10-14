# §479 pre-registration (DRAFT, not frozen): Silver leaf-rollout variants × gen-6 tree prior, A20, fight level

Status: **draft, not launched.** Written 2026-10-14 before any evaluation seed was played. Launch needs the
independent pre-launch review (first round at `7b3db2a6`: FIX REQUIRED, addressed here) to pass and Philipp's
explicit go. The frozen SHA, binary sha256 and seed count are filled in at freeze.

Philipp (2026-10-14): 21:24Z "could we do that here? maybe its not worse and we can save some cpu? maybe consider
to do it with the gen 6 prior and without a prior?"; 21:26Z "yes do both. no prior in the rollouts"; 22:08Z "any
chance that we can improve upon the greedy rollout?"; 22:35Z card choice "Both" (learned card table offline fit,
and rollouts-per-leaf arms in this pre-registration).

## Questions
1. **Primary:** at 2,500 simulations, does a uniform-random leaf rollout lose fight score against the production
   greedy rollout (`SilverRolloutAgent`), and how much CPU per simulation does it save?
2. **Labeled secondary:** the same at 10,000 simulations; a learned card-play table in the greedy rollout; 2 and 4
   greedy playouts per leaf at 1,250 and 625 simulations (the same rollouts per decision as 1 × 2,500).
3. **Descriptive:** the gen-6 tree prior under each rollout variant; per-arm CPU per fight, CPU per simulation,
   mean rollout length and playouts per simulation.

Out of scope: a prior that guides rollout actions (cost estimated below, not run).

## Code and harness
- Rollout options are a per-searcher `SilverSearcher::RolloutConfig` (uniform-k, greedy playouts per leaf, card
  table). The `STS_SILVER_ROLLOUT_UNIFORM`, `STS_SILVER_ROLLOUTS_PER_LEAF` and `STS_SILVER_ROLLOUT_CARD_TABLE`
  env vars set the process default (all unset = production). The native backend replaces it with
  `g_nativeSilverRolloutOverride` when that thread-local is set (`NativeSilverBackend.cpp`).
- `one_combat ctmsilvergen N 20 OUT SEED teacher.json 2` with `STS_CTMSILVER_ARMSET=rollout479`
  (`apps/one_combat/combat_datasets.cpp::ctmSilverCompareGen`): one process plays the 10k source run and every
  arm. The source run and the `control` replay use the production rollouts. Each other arm's replays run inside
  a `RolloutScope` that sets that arm's rollout config. The armset refuses to start if any `STS_SILVER_ROLLOUT_*`
  env var is set, so the source game cannot change. All arms therefore replay the same captured fights from the
  same pre-fight states with the same redraw and planner seeds (§476 pairing). The first review showed that
  separate processes per rollout setting do **not** pair (the source game changes), so that layout is dropped.
- The arms CSV records, per arm row: `cpuSeconds`, `simulations`, `decisions`, `rolloutPlayouts` and
  `rolloutActions` (counted in every search, no profiler needed).

## Arms (R = 2 replicates each, plus one `control` at 10k without redraw)
| Arm | Budget | Rollout | Tree prior |
|---|---|---|---|
| `plain2500`, `mlp2500` | 2,500 | greedy, 1 playout | none / gen 6 |
| `plain10000`, `mlp10000` | 10,000 | greedy, 1 playout | none / gen 6 |
| `uniform2500`, `uniformmlp2500` | 2,500 | uniform random, 1 playout | none / gen 6 |
| `uniform10000`, `uniformmlp10000` | 10,000 | uniform random, 1 playout | none / gen 6 |
| `perleaf2_1250`, `perleaf2_mlp1250` | 1,250 | greedy, 2 playouts averaged | none / gen 6 |
| `perleaf4_625`, `perleaf4_mlp625` | 625 | greedy, 4 playouts averaged | none / gen 6 |
| `table2500`, `tablemlp2500` | 2,500 | greedy with `card_table/card_table_g6.txt` | none / gen 6 |

- Uniform = a uniformly random legal action at every rollout step, including potions, END_TURN and card selects
  (`SilverSearcher::chooseUniformRolloutAction`).
- Gen 6 = `combat_policy_mlp_g6_E.txt` (sha256 `ca9bd7f2…3228`), tree prior K = 8, weight 400, root bonus on, as
  §476.
- Card table: offline fit to gen-6 Silver choices (`card_table/README.md`); replaces only the play-priority order.

## Frozen inputs (filled at freeze)
- Code: commit `<freeze>` on `claude/project-thread-8vmyta`, which merges main `2195b648` (includes §476's
  harness, ADR-0035 and ADR-0036). `run.sh` refuses a checkout whose `apps/`, `src/` or `CMakeLists.txt` differ
  from the frozen code commit, and a binary with another sha256 (`BINARY_SHA256`).
- Environment (`env.sh`): §476's settings with `STS_CTMSILVER_ARMSET=rollout479`,
  `STS_CTMSILVER_SWEEP_SIMS=2500,10000`, `STS_CTMSILVER_HALLWAY_EVERY=3`, `STS_CTMSILVER_MLP_PRIOR` and
  `STS_CTMSILVER_CARD_TABLE`. Silver scoring defaults are those of the frozen binary: ADR-0035 leaf terms on,
  ADR-0036 escape penalty `12,35`. No `STS_SILVER_*` scoring overrides.
- Teacher: generated per binary as §476's `run.sh` (`tools/silver_synth_teacher.py <code sha> <one_combat>`, then
  `ooc_policy` from `one_combat vwinrefreshpolicyspec`); teacher_id `silver-flat-exact10k-synth-<sha8>`.
- Seeds: run seeds **105000000 onward** (coordinator block 105M; count set at freeze from the Cost section).
  Smoke seeds already used in this thread: 74071450–74071489 (full-run smokes) and 74071490–74071493 (matched
  `rollout479` smoke). The pre-launch reviewer uses 74071600–74071649.
- Fight selection: as §476: all BOSS, ELITE and OTHER fights of each source run; NORMAL fights kept when
  `ctmSilverReplicateSeed(seed, fightIdx, 0, 0x4A11) % 3 == 0`. Source policy: plain Silver at 10k, A20.

## Metrics
- **Fight score** per replicate: 0 on death, else 53 + curHp + 11 potions + 0.25 gold + 2 maxHp; arm value per
  fight = replicate mean (§476/§460). An ESCAPE (Smoke Bomb) is scored like any survived fight from the
  post-combat state and counted per arm (`escapes`).
- **Win rate** (1 − death share) and **HP lost** (preHp − post-combat curHp; a death loses all preHp).
- **CPU per fight**, **CPU per simulation** (Σ cpuSeconds / Σ simulations), **mean rollout length**
  (Σ rolloutActions / Σ rolloutPlayouts) and **playouts per simulation**, per arm over valid fights.

## Labeled contrasts (`analyze_479.py`, all fights, fight score, 95% bootstrap over source seeds)
CI > 0 → HELPS label, CI < 0 → HURTS label, else `NOT_SHOWN`.
1. `uniform2500 − plain2500`: `UNIFORM_HELPS` / `UNIFORM_HURTS` (**primary**).
2. `uniform10000 − plain10000`: `UNIFORM_HELPS` / `UNIFORM_HURTS`.
3. `table2500 − plain2500`: `TABLE_HELPS` / `TABLE_HURTS`.
4. `perleaf2_1250 − plain2500`: `PERLEAF2_HELPS` / `PERLEAF2_HURTS`.
5. `perleaf4_625 − plain2500`: `PERLEAF4_HELPS` / `PERLEAF4_HURTS`.

Five labels at 95% each, no multiplicity correction; the write-up says so and does not treat one borderline
label as decisive. With about 1,000 fights a `NOT_SHOWN` label means inconclusive at this resolution.

CPU ratios with the same seed bootstrap (no label): per simulation and per fight, for `uniform2500/plain2500`,
`uniform10000/plain10000`, `table2500/plain2500`, `perleaf2_1250/plain2500`, `perleaf4_625/plain2500`.

Descriptive only (no label): `mlp − plain` at 2500 and 10000; `uniformmlp − uniform` at both budgets;
`uniformmlp2500 − mlp2500`; `tablemlp2500 − mlp2500`; `tablemlp2500 − table2500`; `perleaf2_mlp1250 − mlp2500`;
`perleaf4_mlp625 − mlp2500`; `plain2500 − plain10000`. Every contrast also for win rate and HP lost, and on the
boss, elite and normal (NORMAL + OTHER) subsets.

## Decision rules (pre-set; none changes a default by itself)
- **Uniform:** worth a follow-up only if contrast 1 is not `UNIFORM_HURTS` **and** the upper 95% bound of the
  `uniform2500/plain2500` CPU-per-simulation ratio is at most 0.5. Otherwise greedy stays and the ledger records a
  negative.
- **Card table:** `TABLE_HELPS` with the `table2500/plain2500` per-fight CPU ratio at most 1.1 → a confirmation run
  on fresh seeds is proposed to Philipp (who decides any default). `NOT_SHOWN` or `TABLE_HURTS` → no follow-up
  on this table.
- **Rollouts per leaf (each k):** `PERLEAFk_HELPS` → a confirmation run is proposed. `NOT_SHOWN` with the upper
  95% bound of the per-fight CPU ratio at most 0.8 and the score CI's lower bound at least −1.0 → proposed as a
  CPU saver for a confirmation run. Anything else → no follow-up.
- Prior arms are descriptive and decide nothing.

## Exclusions (counted by reason in the analysis)
- `invalid_arm_row`: any arm row of the fight invalid (simulator health, undecided combat, missing decision hook,
  control replay mismatch, source trajectory invalid).
- `incomplete_shard_abort`: an arm has fewer than R = 2 replicates (shard ended mid-fight).
- `truncatedRows`: a CSV line cut off mid-write is dropped.
- Escapes are not excluded (scored as above).

## Cost
Matched smoke (seeds 74071490–74071493, 1 seed per shard on 4 cores): <filled from the smoke below>. The run
size is chosen at freeze so that it gives about 1,000 valid fights, or fewer if Philipp caps the CPU.

## Operation and delivery
As §476: `run.sh OUT TOTAL BASE "<shards>"`, launched detached with a re-armed background watcher; 4 shards per
container; per-shard timeout set at freeze from the smoke cost (at least 3× the expected shard time). A shard
lost with its container is rerun unchanged into a fresh folder. Raw tar with sha256 to
`/mnt/project-files/silver-rollout-2x2/`, verified from a second container before the write-up cites it.

## Cost of a prior that guides rollouts (estimate, not run)
One gen-6 MLP call costs about 6–27 µs (`silver-prior-nn-cost`, `silver-prior-arch-sweep` project notes). The
main engine runs about 73k simulations/s on 4 vCPUs (§360), about 14 µs per whole simulation, so a prior call per
rollout step would cost one to two orders of magnitude more per simulation. **Inference**, not a measurement.

## Write-up
Ledger §479 (re-check main's ledger end first) with this file at the freeze SHA, `analyze_479.py` output and the
raw tar sha256.
