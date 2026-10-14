# §476 pre-registration: gen-6 Silver MLP prior at Ascension 20, with a simulation sweep (fight level)

Written 2026-10-14 before any evaluation seed was played. Philipp (17:46Z): "can we evaluate the gen 6
prior on A20? also maybe how it performs with fewer simulations? maybe dont do full runs, just select a
few hundred / 1000 fights".

## Questions
1. At A20, does the gen-6 MLP tree prior (model E) beat plain Silver at the same simulation budget, at
   the production budget (10,000) and at 1/4 (2,500) and 1/16 (625)? (primary, one label per budget)
2. At A20, does gen 6 beat the gen-5 prior at the same budget? (iteration, one label per budget)
3. Descriptive: how fight score, win rate and HP loss change with the budget, with and without the prior,
   and whether gen 6 at a lower budget reaches plain Silver at a higher one.

## Frozen inputs
- Code: commit `339da3b1` (main `e8410510` plus the `mlpsweep` armset in
  `apps/one_combat/combat_datasets.cpp::ctmSilverCompareGen`). Release `one_combat` sha256 in
  `BINARY_SHA256` (`1c774367…520b`). `run.sh` refuses a checkout whose `apps/`, `src/` or
  `CMakeLists.txt` differ from `339da3b1` or a binary with another sha256.
- Models: gen 6 = E, `../silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt`
  (`combat_policy_mlp_v2`, encounter + monster embeddings, sha256 `ca9bd7f2…3228`, offline orig
  fold-4 CE 1.1749); gen 5 = `combat_policy_mlp_gen5.txt` here (copy of
  `/mnt/project-files/silver-az-mlp/gen5/model/`, sha256 `5e9f975a…9e8a`, CE 1.1954).
- Harness: `one_combat ctmsilvergen 24 20 OUT SEED teacher.json 2` with `env.sh`
  (`STS_CTMSILVER_ARMSET=mlpsweep`, `STS_CTMSILVER_SWEEP_SIMS=10000,2500,625`,
  `STS_CTMSILVER_HALLWAY_EVERY=3`): Ascension 20, project-fair RNG, flat exact budgets, c = 25, the §460
  OOC policy and flat exact-10k teacher (`tools/silver_synth_teacher.py`). One plain-10k source run per
  seed; every captured fight (all combats, hallway fights subsampled, below) is replayed by a 10k control
  (no redraw, must reproduce the source) and by each arm with R = 2 replicates on a shared redraw of
  the combat RNG (same redraw and planner seed for every arm at a given replicate).
- Arms, for each budget b in {10000, 2500, 625}: `plain<b>` (no prior), `mlp<b>` (gen 6, tree prior
  K = 8, weight 400, root bonus on as in §455/§460) and `mlpprev<b>` (gen 5, same settings).
- Fight selection: all BOSS, ELITE and event (OTHER) fights of each source run; NORMAL fights only
  when `ctmSilverReplicateSeed(seed, fightIdx, 0, 0x4A11) % 3 == 0` (about one in three), so bosses and
  elites are a larger share than in a full run. The source policy is A0-trained (as in the §403 A20
  corpus), so A20 runs mostly end in Acts 1–3 and the fight mix follows where they die.
- Seeds: 104000000–104000095 (96 source seeds; coordinator block 104M), `run.sh OUT` in one cloud
  container, 4 shards × 24 seeds. Expected about 1,000 fights (smoke: 10.5 fights per seed) and
  about 8 core-hours.

## Metric and analysis (`analyze_476.py`, frozen here)
Fight score and pairing as §460: per replicate 0 on death, else 53 + curHp + 11 potions + 0.25 gold +
2 maxHp; arm value per fight = replicate mean; paired per fight; 95% bootstrap CI over source seeds
(10,000 resamples, seed 0). A fight counts only when every arm row is valid (control reproduced the
source) and every arm has R = 2 replicates. Also per fight: win rate (1 − death share) and HP lost
(preHp − post-combat curHp; a death loses all preHp).
- **Primary (three labels):** `mlp<b> − plain<b>`, all fights, score: CI > 0 `G6_HELPS`, CI < 0
  `G6_HURTS`, else `NOT_SHOWN`.
- **Iteration (three labels):** `mlp<b> − mlpprev<b>`, all fights, score: `G6_BETTER` / `G6_WORSE` /
  `NOT_SHOWN`.
- Six labels at 95% each, no multiplicity correction; the write-up says so and does not treat one
  borderline label as decisive.
- **Secondary (descriptive):** `mlpprev<b> − plain<b>`; budget contrasts `mlp2500 − plain10000`,
  `mlp625 − plain2500`, `mlp625 − plain10000`, `plain2500 − plain10000`, `plain625 − plain10000`,
  `mlp2500 − mlp10000`, `mlp625 − mlp10000`; every contrast for win rate and HP lost; subsets boss,
  elite, normal (NORMAL + OTHER); CPU per fight and per decision per arm. The prior arms cost a few
  percent more CPU than plain at the same budget (smoke: 1.02–1.06x); no matched-CPU plain arm is run,
  so a primary HELPS is "at equal simulations", not "at equal CPU" (§460 is the matched-CPU A0 check).
- **Decision:** none on defaults (the MLP prior stays opt-in). The labels feed Philipp's call on
  whether to use gen 6 at A20 and at lower budgets.

## Validity
A shard rc != 0 or a sha mismatch is reported, not rerun with changed settings. Fights finished before
a shard abort (for example a native Silver stall, or the 6 h per-shard timeout) count; a fight with
fewer than R = 2 replicates in some arm is excluded as `incomplete_shard_abort` and the rest of that
shard's seeds are lost and reported, with no rerun. Excluded fights are counted by reason.

## Write-up
Ledger §476 with this file, the analysis output and the sha256 of the raw tar on the share
(`/mnt/project-files/silver-gen6-a20-476/`, checked from a second container).

## Smoke (not evidence)
Seeds 74071200–74071203 (1 seed per shard, working tree equal to `339da3b1`): 4/4 rc 0, 42 valid
fights (9 boss, 23 elite, 8 normal, 2 event), control 42/42, 461 s wall on 4 cores (about 29 core-s per
fight). CPU per fight vs plain at the same budget: gen 6 1.02x (10k), 1.03x (2.5k), 1.04x (625).
`analyze_476.py` runs on the output.
