# §455 pre-registration: Silver AZ MLP prior, generation 1, CPU-matched fight-level check

Written 2026-10-13 before any eval seed was played. Philipp asked to run it
("Could we now throw some compute at 'build MLP prior gen 1'?", 14:42Z). Plan:
`/mnt/project-files/silver-az-mlp/PLAN.md` §2.5-§2.6.

## Question
Does the gen-1 MLP tree prior (random init, trained on the §397 + §404
corpora, PR #517) at 2k simulations beat plain Silver at matched CPU? This is
the loop's generation-1 kill gate.

## Frozen inputs
- Code: main `4f0cfb4c7c1297fc9393f2ead01505e3fda06f9b` (#517 merged).
  Release `one_combat` sha256 `fdc44395…a52f` (`BINARY_SHA256`; a clean and an
  incremental build gave the same file).
- Model: `combat_policy_mlp_gen1.txt` sha256 `a5f4505a…64d2` (copy in this folder;
  same file as `../gen1/`). Offline fold-4 CE 1.220 / top-1 56.1%.
- Harness: `one_combat ctmsilvergen N 0 OUT SEED teacher.json 2` with
  `STS_CTMSILVER_ARMSET=mlpprior` (`env.sh`): A0, project-fair, flat exact
  root budgets, c = 25, frozen §452/§453 OOC policy and teacher construction.
  One plain-10k source run per seed; every combat of it is replayed by each arm
  with 2 replicates on a shared redraw of the combat RNG (paired across arms).
- Arms: `plain2k` (2,000 sims), `plain_cpu` (2,300 sims, plain), `mlp8_2k`
  (2,000 sims, MLP prior at the root and at non-root decision nodes with >= 8
  simulations, bonus w * P / (n + 1), w = 400, untried edges in prior order).
  `plain_cpu` = 2,300 is conservative: review CPU match on 106 fights (seeds
  74044000-74044003) put `mlp8_2k` at 1.058x `plain2k` per fight (matched plain
  about 2,100-2,150); the implementer's 47-fight smoke gave 1.145x.
- Seeds: 85000000-85000127 (128 source seeds), sliced by `worker.sh W N`
  (N = 8 or 16 workers, 4 shards each).

## Metric and analysis (`analyze_gen1.py`, frozen here)
Fight score per replicate: 0 on death, else 53 + curHp + 11 * potions + 0.25 *
gold + 2 * maxHp (as §452/§453). A fight counts when every arm row is valid
(control replay matched). Arm score per fight = mean of its 2 replicates;
contrasts paired per fight; 95% CI = bootstrap over source seeds (10,000
resamples, RNG seed 0).

- **Primary:** `mlp8_2k - plain_cpu`, all fights, score.
- **Kill rule (PLAN §2.6):** if the primary CI lower bound is <= 0, the loop
  stops at generation 1 (label KILL); otherwise CONTINUE.
  Labels: CI > 0 MLP_PRIOR_HELPS, CI < 0 MLP_PRIOR_HURTS, else NOT_SHOWN.
- **Secondary (descriptive):** `mlp8_2k - plain2k`, `plain_cpu - plain2k`;
  boss and elite subsets; death rate; realised CPU per fight and per decision
  per arm (`cpuPerFightVsPlain2k`). If realised `plain_cpu` CPU is below
  `mlp8_2k`'s, the write-up says so; it does not change the primary.

## Validity
- Expected: about 3,300 valid fights (§452/§453 scale). A worker with a shard
  rc != 0 or a sha mismatch is reported, not re-run with changed settings.
- Excluded fights (invalid control replay) are counted in the write-up.

## Write-up
Ledger §455 (EXPERIMENTS.md + ledger file), evidence packet with this file,
`analyze_gen1.py` output and the per-worker tars' sha256.
