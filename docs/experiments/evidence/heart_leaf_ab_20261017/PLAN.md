# Pre-registered A20 paired A/B: Heart leaf td2 vs the X2-B leaf (issue #605, §522)

Status: **plan, awaiting the pre-launch review.** Philipp, 2026-10-17 19:59Z in the Heart leaf thread: "yes lets try a
parid a20 a/b." (after td2 failed the CONFIRM gate on Act-1 calibration, §515; this overrides the pre-registered "no
A/B" rule at his request); card 20:03Z: "512 pairs" on 8 workers. Run commit: the reviewed commit carrying this file.

## Question

With student C's prior and rollout policy, rollout3 and 512 simulations fixed, does valuing the rollout3 leaf ends with
the Heart leaf td2 (`models/candidates/heart_leaf_td2`, manifest `1b1ad13e…`) instead of the public X2-B change A20
strength? td2 ranks states better than X2-B on §503 CONFIRM (AUC 0.750 vs 0.726, BCE 0.3345 vs 0.3479) but
under-predicts Act-1 Heart kills.

## Arms (shared seeds, fair play)

| Arm | Difference |
|---|---|
| C (control) | none: rollout3 leaf valued by the pinned public X2-B (main's native leaf) |
| H | `STS_OOC_MCTS_LEAF_HEART_MODEL=<repo>/models/candidates/heart_leaf_td2/heart_leaf.json` |

Common environment, `arm_env.sh` (run under `env -i`; each unit writes its `STS_*` lines to `<unit>.env`): the §504
control arm on current main, A20 Heart objective, keys collected, full runs, `STS_OOC_HEART1=studentc.bin`
(`eff2f74f…`) with `STS_OOC_MCTS_PRIOR=heart1full` (ADR-0042) and `STS_OOC_MCTS_LEAF_POLICY=heart1`, native leaf,
3 leaf combats, 512 sims, cpuct 1.5, widen 4/0.75, depth 32, early stop, tree rules, 8 public futures, exact Silver,
`STS_SILVER_LEARNED_STOP=0`. Both arms also write `STS_OOC_MCTS_ROOT_TRACE` (observation only; HP at decisions).
Command per unit (`run_unit.sh`): `timeout 4h bash tools/seed_guard.sh one_combat bestbench 10000 1 20 <seed> <csv>`.

## Seeds

512 fresh A20 source seeds `111191000..111191511` (coordinator block 111191000-111192999), one run per seed per arm.
Reviewer smoke seeds 111193000-111193099. My smoke used 111159002.

## Endpoints and decision rule

- **Primary:** reached Act 4 (CSV `act` >= 4), H vs C paired by seed. Exact two-sided McNemar on discordant pairs; 95%
  paired-difference CI by seed bootstrap (2,000 resamples, RNG 20261017). IMPROVED if H−C > 0 and p < 0.05; WORSE if
  H−C < 0 and p < 0.05; otherwise NOT_SHOWN.
- **Secondary (same statistics, descriptive):** Heart kills (CSV `won`); paired mean final floor; act-1 deaths;
  MCTS CPU seconds per OOC decision; seconds per run.
- **Descriptive behaviour (Philipp's brief):** Act-4 campfire choice (the last campfire decision of a run that
  reached Act 4) and HP fraction at that decision from the root trace, against the §504 arm C baseline Rest 25,
  Smith 12, Dig 6, Lift 2 of 45 (recomputed by this analyzer from the §504 tars; the brief's 11 Smith counted one
  run differently); per-event chosen options against Golden Idol take 0/19, Nest dagger 0/18, Cleric purify 0/14,
  Neow boss swap 0/128, Shining Light 10/14, Augmenter Mutagenic 16/16.
- **Validity:** units are not rerun (a container restart reruns only an interrupted unit, whole). A unit counts when
  its `.done` line has rc=0 and its CSV has the seed's row; a seed missing a counted unit in either arm is excluded and
  reported. More than 3% of the seeds (15) excluded makes the comparison INVALID. Computed by
  `tools/analyze_heart_leaf_ab.py analyze COHORTS <out dirs>`.

A positive result goes to Philipp for the default decision; nothing changes defaults from this A/B alone. A20
detection power: about ±6 pp on reaching Act 4; Heart-kill differences under about 5 pp will not resolve.

## Budget

§504 arm C runs took 453 s (wall) on average; the Heart leaf adds a 600-tree critic and a 129-tree residual per leaf
end. Smoke, seed 111159002 at `209c5613` (binary `20d03790…`), both arms rc 0: C died on floor 45 (act 3),
324 s, 2.89 MCTS CPU s per OOC decision; H died on floor 33 (act 2), 216 s, 2.53 s per decision; the H log shows
the td2 manifest, critic and residual loaded; the root trace is about 0.5 MB per run. Estimate about 130 CPU-h for 1,024 runs. Execution: 8 hosted workers (Philipp's count), each
running 64 contiguous seeds × 2 arms = 128 units, 4 at a time (`worker.sh`), about 4 h per worker. Each worker
uploads one tar and one DONE file to `/mnt/project-files/heart-leaf-td/ab/`.
