# CTM vs low-sim Silver with the synthetic root prior (§407 pre-registration, v2)

**v2 (2026-10-09 ~14:00 UTC):** Philipp stopped the first 128-seed run (seeds
62000000..127, binary `1f53715d`) after an interim look at about 66 seeds and
asked for every post-combat field the CTM predicts, on fresh seeds and 4 cloud
workers × 4 threads. The stopped run is kept as an exploratory record in
`/mnt/project-files/ctm-vs-lowsim-silver/stopped-128-1f53715d/` and is not
pooled. Its interim read (HP: Silver better; deaths: tie; CTM 100–400x faster)
was seen before v2 was frozen, so v2's HP and death results are a replication,
not a blind test. v2 changes only what is recorded and adds the field
comparison; the arms are unchanged except that teacher10k now has 2 replicates
(needed for the field Brier).

Frozen before any v2 seed ran. Requested by Philipp on 2026-10-09: compare the
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
| teacher10k | 10,000 | off | redrawn | 2 (ideal samples; noise floor) |
| prior256 | 256 | v1, w400 | redrawn | 4 |
| prior64 | 64 | v1, w400 | redrawn | 4 |
| plain256 | 256 | off | redrawn | 4 |

Replicate k uses the same redraw and planner seed in every arm. Flat exact root
budgets (`STS_SILVER_EXACT_ROOT_BUDGETS=1`), as in the low-sim screen
(`/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/`). Prior
file `prior-natpert.compact.txt` (sha256 recorded in the manifest), weight 400.
The source and the 10k arms run with the prior forced off by a thread override.

## Post-state fields (added in v2)

Every forecaster also leaves samples of the RAW post-combat persistent state
(the CTM's output type: HP, max HP, gold, potion slots, relic counters, deck,
stolen gold, Smoke Bomb flag): 32 CTM draws (`prepare` + `sample`, as the
planner draws them) and every Silver replicate. The control replay's state is the
truth. Fields: outcome, hp, maxHp, gold, potions, relics (sorted id:counter),
deck (hash of sorted id/upgrade/misc), stolenGold, nonhp_joint (all but HP) and
joint (everything). A dead sample is DEATH in every field. Per field the Brier
loss of the sample distribution, `1 - 2 P(truth) + sum_v P(v)^2`, is estimated
without bias from the match fraction and matching distinct sample pairs; the
mean match probability is reported too.

## Seeds and budget (v2)

Fresh seeds 62100000..62100255 (256 source runs), Ascension 0. Four cloud
workers W = 0..3 with 4 cores each; worker W runs 4 shards of 16 seeds, shard i
starting at 62100000 + 64W + 16i. Expected about 3.5 CPU-min per source run,
about 15 CPU-hours, about 1 hour per worker. The smoke seed is 62109000.

## Decision rule

Primary comparison: prior256 (K=4) minus CTM, on valid states the CTM supports.
Paired mean loss differences with a 95% bootstrap CI over source seeds (10,000
resamples, RNG seed 0), for death Brier and HP MSE.

- SILVER_BETTER: both CIs entirely below 0.
- CTM_BETTER: either CI entirely above 0.
- SILVER_NONINFERIOR: otherwise, both CI upper bounds below 10% of the CTM's
  own loss.
- INCONCLUSIVE: anything else.

Co-primary (v2): the same paired rule, prior256 minus CTM, on the nonhp_joint
field Brier (everything except HP).

Secondary (descriptive): field-level labels for every field and arm; the same labels for prior64, plain256, teacher10k and
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
