# §460 pre-registration: Silver AZ MLP prior, generation-3 milestone (fight level)

Written 2026-10-13 before any eval seed was played. Philipp asked for gen 3 ("Can we do a gen 3 silver
prior?", 19:32Z); PLAN `/mnt/project-files/silver-az-mlp/PLAN.md` §2.5 puts a fight-level milestone
after generation 3. Same harness and analysis as §455 (`../gen1-eval/PREREG.md`), plus a gen-1 arm.

## Questions
1. Does the gen-3 MLP tree prior at 2k beat plain Silver at matched CPU? (primary)
2. Does iterating (gen 3) beat the gen-1 prior that §455 evaluated? (iteration question, PLAN §7)

## Frozen inputs
- Code: main `37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08`. Release `one_combat` sha256 `9098ee11…b0f7`
  (`BINARY_SHA256`).
- Models (copies here): gen 3 `combat_policy_mlp_gen3.txt` f57b7fdd…5315 (window bootstrap + gen-2 +
  gen-3 self-play, run B; offline orig fold-4 CE 1.2192); gen 1 `combat_policy_mlp_gen1.txt`
  a5f4505a…64d2 (§455).
- Harness: `one_combat ctmsilvergen N 0 OUT SEED teacher.json 2`, `STS_CTMSILVER_ARMSET=mlpprior`
  with `STS_CTMSILVER_MLP_PRIOR_PREV` (`env.sh`): A0, project-fair, flat exact budgets, c = 25, frozen
  §452/§453 OOC policy and teacher. One plain-10k source run per seed; every combat replayed by each
  arm with 2 replicates on a shared redraw of the combat RNG.
- Arms: `plain2k`; `plain_cpu` (2,300 sims, as §455; conservative, gen-3 costs the same per node as
  gen 1); `mlp8_2k` (gen 3, K = 8, w = 400, root bonus on as in §455); `mlp_prev8_2k` (gen 1, same).
  The self-play teacher had the root bonus off (PLAN §2.2); the evaluated play configuration is §455's.
- Seeds: 90000000-90000127 (128 source seeds; coordinator block 90M), `worker.sh W N`, N = 8 or 16.

## Metric and analysis (`analyze_gen3.py`, frozen here)
Fight score and pairing exactly as §455 (0 on death, else 53 + HP + 11 potions + 0.25 gold + 2 maxHP;
replicate mean; paired per fight; 95% bootstrap CI over source seeds, 10,000 resamples, seed 0;
a fight counts only when every arm row is valid).
- **Primary:** `mlp8_2k - plain_cpu`, all fights, score. Labels: CI > 0 MLP_PRIOR_HELPS, CI < 0
  MLP_PRIOR_HURTS, else NOT_SHOWN.
- **Iteration:** `mlp8_2k - mlp_prev8_2k`, all fights, score: GEN3_BEATS_GEN1 / GEN3_WORSE_THAN_GEN1 /
  NOT_SHOWN. PLAN §2.6 converged rule (point < +0.3, CI includes 0, and offline TV < 0.03) is
  reported; TV gen 3 vs gen 2 is 0.036, so the loop is not declared converged at this milestone.
- **Decision:** continue the loop to gen 6 unless the primary is NOT_SHOWN or HURTS *and* the
  iteration contrast is not GEN3_BEATS_GEN1; then the write-up recommends stopping and keeping the
  better of gen 1 / gen 3 (any further step needs Philipp's go).
- **Secondary (descriptive):** `mlp_prev8_2k - plain_cpu` (replication of §455), contrasts vs
  `plain2k`, boss/elite subsets, death rate, realised CPU per fight and per decision per arm.

## Validity
About 3,300 valid fights expected. Shard rc != 0 or a sha mismatch is reported, not re-run with
changed settings. Excluded fights are counted by reason in the write-up. Fights completed before a shard abort (rc != 0, e.g. a native Silver
"exceeded 1000 decisions" stall at 37b7d33e) count; a fight where any arm has fewer than R = 2
replicates is excluded as `incomplete_shard_abort`, and the rest of that shard's seeds are lost
and reported, with no rerun. (Added 2026-10-13 after the pre-launch review, before any eval seed.)

## Write-up
Ledger §460 with the gen-2/gen-3 training evidence, this file, the analysis output and tar sha256s.

## Smoke (not evidence)
`worker.sh` with TOTAL=4 on seeds 74057000-74057003 (N = 1): 4/4 shards rc 0, 84 valid fights, all
four arms present; realised CPU per fight vs plain2k: mlp8_2k (gen 3) 1.02x, mlp_prev8_2k 1.02x,
plain_cpu 1.17x. `analyze_gen3.py` runs on the output.
