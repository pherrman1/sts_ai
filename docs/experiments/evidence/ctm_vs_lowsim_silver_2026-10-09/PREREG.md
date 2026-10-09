# CTM vs low-sim Silver with the synthetic root prior (§407 pre-registration)

Frozen before any §407 seed ran. Requested by Philipp on 2026-10-09: compare the
speed and accuracy of the CTM stack with low-sim Silver plus the synthetic root
prior, as input to a possible CTM retirement. This run only measures; it changes
no default and retires nothing.

## Question and framing

Both candidates can resolve a combat inside OOC planning. The comparison scores
each as a **forecast of the combat outcome from the fight's start state**:

- Ground truth: the source fight, played by exact-10k Silver (frozen teacher,
  production OOC policy, fair RNG) on the real hidden future. `d = 1` on a loss;
  `y` = terminal HP on a win, 0 on a loss.
- CTM: the production stack (`combat_transition_deepsets_lizard_t2.native` with
  the pinned standard Brew fallback and the active-Lizard correction), as the
  OOC planner loads it. Forecast `p = P(death)`, `h = (1 - p) * E[HP | win]`.
- Silver arms replay the same entry state with the six BattleContext RNG
  streams redrawn (counters kept), as a planner would resolve a hypothetical
  fight. With K replicates, `p` = loss fraction, `h` = mean `y`.
- Losses: death Brier `(p - d)^2` and HP squared error `(h - y)^2`.
- Speed: thread CPU per forecast (CTM: predictor-input capture plus
  expectation, mean of 20 repeats; also capture plus prepare plus one sample).
  Silver: summed replay CPU of the K replicates.

The Run 2 retrained CTM (FAST0 / FASTX) exists only on Philipp's machine and is
not part of this cloud run. **Open question:** whether it changes the answer.

## Arms (`one_combat ctmsilvergen`, every fight of every source run)

| arm | budget | root prior | hidden future | replicates |
|---|---|---|---|---|
| control | 10,000 | off | source | 1 (must reproduce the source fight) |
| teacher10k | 10,000 | off | redrawn | 1 (an ideal single sample; noise floor) |
| prior256 | 256 | v1, w400 | redrawn | 4 |
| prior64 | 64 | v1, w400 | redrawn | 4 |
| plain256 | 256 | off | redrawn | 4 |

Replicate k uses the same redraw and planner seed in every arm. Flat exact root
budgets (`STS_SILVER_EXACT_ROOT_BUDGETS=1`), as in the low-sim screen
(`/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/`). Prior
file `prior-natpert.compact.txt` (sha256 recorded in the manifest), weight 400.
The source and the 10k arms run with the prior forced off by a thread override.

## Seeds and budget

Fresh seeds 62000000..62000127 (128 source runs), Ascension 0, four shards of
32 seeds (62000000+32i, i = 0..3) in one cloud container, one thread each.
The smoke seed 62009000 (25 fights, 151 s wall) gives roughly 1.5 to 2 CPU-min per
source run, so about 4 CPU-hours. 128 rather than 64 because fight deaths are rare
(about one per lost run) and the Brier comparison needs them.

## Frozen provenance

- Code SHA `1f53715d` (branch `claude/project-thread-wfsdk0`, main `82c4946a` plus
  this mode); Release `one_combat` sha256
  `3e918355c594d362eac3ae1648d3133d88e3c9e4b857e43cc6bde155b5264031`.
- Teacher `teacher.json` here (exact-10k ordinary Silver, frozen V4 OOC policy as
  in #400); environment `env.sh` here (`$RUN` = run directory).
- Prior sha256 `573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee`.
- CTM artifacts: tracked production files, hashes recorded in each manifest.
- Command per shard: `tools/seed_guard.sh $RUN/one_combat ctmsilvergen 32 0
  $RUN/shardI 6200000X $RUN/teacher.json 4`.

Smoke (seed 62009000, not part of the cohort): 25 fights, CTM supports 24
(one Smoke Bomb state), control replay 24/25; the one miss is a Smoke Bomb
escape whose source label is itself quarantined (`escape`).

## Decision rule

Primary comparison: prior256 (K=4) minus CTM, on valid states the CTM supports.
Paired mean loss differences with a 95% bootstrap CI over source seeds (10,000
resamples, RNG seed 0), for death Brier and HP MSE.

- SILVER_BETTER: both CIs entirely below 0.
- CTM_BETTER: either CI entirely above 0.
- SILVER_NONINFERIOR: otherwise, both CI upper bounds below 10% of the CTM's
  own loss.
- INCONCLUSIVE: anything else.

Secondary (descriptive): the same labels for prior64, plain256, teacher10k and
the K=1 versions of each; bias of `p` and `h`; per-act breakdown; CTM support
coverage and unsupported reasons; the noise floor (half the teacher10k K=1
loss); CPU ratio Silver/CTM.

Retirement reading: an accuracy label alone does not retire the CTM. Any
retirement proposal must also state the measured CPU ratio, because OOC MCTS
resolves many combats per decision.

Validity: a state counts only if its source trajectory and label are valid, the
control replay reproduces the source fight, and every arm row is valid. Escape
fights (quarantined labels) are excluded and counted. A control mismatch on a
state with a valid source label is reported; more than 1% of such states stops
the interpretation.

## Analysis

`python3 tools/analyze_ctm_vs_silver.py report.json shard0 shard1 shard2 shard3`
