# Stages 1–2 result: neither referee matches real play, so the decision metric is NOT QUALIFIED (2026-10-23)

256 A20 games on seeds 111360000–111360255, RUN_COMMIT `799361fc` (code `31479012`), v3 binary `41b26423…`,
32 workers × 4 lanes, `schedule queue`. [`verify.txt`](verify.txt) (`tools/cloud/verify_campaign.py`): 256 of 256
units OK, one duplicate, one run commit, 32 of 32 worker DONE files. Unit tar hashes: [`tars.sha256`](tars.sha256).
Analysis: [`analyze_compare.py`](analyze_compare.py) on the extracted units → [`result.json`](result.json). Play is
the stage-3 control arm A. All 256 games are valid, and 57 of them killed the Heart (22.3%).

## Stage 1: the referee
Neither candidate passes the level gate (|referee − real| ≤ 0.05 in every act). Over each act's searched roots, real
is the mean outcome of the root's game (1 = it killed the Heart) and the referee is the mean value of the played
action:

| act | roots | games | real Heart rate | R_full | R_full − real [95% CI] | R_act | R_act − real [95% CI] |
|---|---|---|---|---|---|---|---|
| 1 | 6,711 | 256 | 0.231 | 0.081 | −0.150 [−0.202, −0.101] | 0.177 | −0.054 [−0.105, −0.005] |
| 2 | 5,667 | 228 | 0.276 | 0.111 | −0.166 [−0.220, −0.114] | 0.204 | −0.072 [−0.132, −0.018] |
| 3 | 3,412 | 157 | 0.407 | 0.176 | −0.230 [−0.302, −0.164] | 0.191 | −0.215 [−0.289, −0.142] |
| 4 | 447 | 91 | 0.696 | 0.486 | −0.209 [−0.288, −0.134] | 0.486 | −0.209 [−0.283, −0.130] |

- **R_full** (rollouts to the end of the game) is far too pessimistic in every act. From act-1 roots its rollouts kill
  the Heart at about a third of the real rate (0.081 vs 0.231). Stage 0 saw the same bias over shorter horizons:
  rollouts die more often than real runs.
- **R_act** (rollouts to the act's end, then M0's calibrated X2-B) misses narrowly in acts 1 and 2 (−0.054, −0.072)
  and by far in acts 3 and 4 (−0.215, −0.209). From an act-4 root it equals R_full.
- Both pass the precision gate. The SE of M0's mean advantage over its 880 flips is 0.0014 under both (gate 0.002),
  and M0's flips cost 1.03 core-hours of referee CPU (gate 10). The mean paired variance at a flip is 0.092 for R_full
  and 0.021 for R_act.

## Stage 2: the decision metric
Under the PREREG, no qualified referee means the metric is **NOT QUALIFIED**. Both referees' numbers below are
exploratory.

| arm | flips | flip rate | act 1 / 2 / 3 / 4 | search CPU (core-h) |
|---|---|---|---|---|
| M0 | 880 | 5.42% | 288 / 332 / 260 / 0 | 44.7 |
| S | 707 | 4.35% | 235 / 257 / 215 / 0 | 50.4 |
| MS | 867 | 5.34% | 282 / 317 / 268 / 0 | 49.6 |
| G1B | 915 | 5.64% | 344 / 324 / 247 / 0 | 49.5 |
| STU | 1,071 | 6.60% | 354 / 334 / 319 / 64 | 28.5 |
| TD2 | 921 | 5.67% | 330 / 324 / 267 / 0 | 44.5 |
| NULL | 759 | 4.67% | 231 / 244 / 229 / 55 | 46.2 |

Predicted change in Heart kills per game against the played arm A (pp, 95% seed bootstrap; halves are the even and
odd seeds):

| arm | R_full | halves | R_act | halves |
|---|---|---|---|---|
| M0 | +0.90 [+0.01, +1.81] | +1.25 / +0.56 | +1.42 [+0.39, +2.57] | +2.03 / +0.80 |
| S | +0.85 [+0.12, +1.57] | +0.96 / +0.73 | +0.41 [−0.11, +0.92] | +0.80 / +0.02 |
| MS | +0.96 [+0.07, +1.88] | +1.56 / +0.37 | +0.40 [−0.56, +1.53] | +1.52 / −0.71 |
| G1B | −0.11 [−1.16, +0.92] | +0.15 / −0.37 | −3.99 [−5.04, −2.98] | −3.46 / −4.51 |
| STU | −1.40 [−2.60, −0.23] | −1.43 / −1.38 | −1.95 [−2.96, −1.01] | −2.02 / −1.87 |
| TD2 | +1.48 [+0.53, +2.50] | +1.67 / +1.29 | −1.35 [−2.26, −0.36] | −1.01 / −1.69 |
| NULL | +0.49 [−0.43, +1.47] | +0.20 / +0.79 | −0.07 [−0.79, +0.68] | −0.09 / −0.05 |
| M0 main effect | +0.51 [−0.22, +1.28] | | +0.70 [−0.23, +1.83] | |
| blend main effect | +0.45 [−0.05, +0.96] | | −0.30 [−0.70, +0.10] | |

Retrospective checks (PREREG stage 2):

| check | R_full | R_act |
|---|---|---|
| STU (§504): upper bound < 0 | pass (−0.23) | pass (−1.01) |
| TD2 (§522): inside [−3.5, +2.1] | pass (+1.48) | pass (−1.35) |
| G1B (§615): inside [−1.0, +7.2] | pass (−0.11) | **fail (−3.99)** |
| NULL: interval contains 0 | pass | pass |

- With the level gate set aside, R_full passes all four checks and R_act fails G1B. That is weak support for R_full.
  The three past A/Bs ran on older stacks, so the checks test direction and size only. STU's check is marginal: on
  the first 245 games, R_full's upper bound was +0.10 pp, which fails.
- **R_act is not X2-B-free.** Its act-end value is M0's own function of X2-B. So it scores M0's flips with M0's
  value, and it scores the flips of a head that disagrees with X2-B (G1B) with X2-B. That fits G1B's large negative
  prediction under R_act and its near-zero one under R_full.

**Prospective row** (the first entry of the predicted-against-observed table; predictions exploratory):

| contrast | stage-3 A/B, observed | R_full predicted | R_act predicted |
|---|---|---|---|
| M − A | +1.37 [−1.17, +4.00] | +0.90 [+0.01, +1.81] | +1.42 [+0.39, +2.57] |
| S − A | −1.37 [−3.91, +1.17] | +0.85 [+0.12, +1.57] | +0.41 [−0.11, +0.92] |
| MS − A | +1.56 [−1.17, +4.30] | +0.96 [+0.07, +1.88] | +0.40 [−0.56, +1.53] |
| M0 main effect | +2.15 [+0.10, +4.25] | +0.51 [−0.22, +1.28] | +0.70 [−0.23, +1.83] |
| blend main effect | −0.59 [−2.25, +1.07] | +0.45 [−0.05, +0.96] | −0.30 [−0.70, +0.10] |

- Every prediction lies inside the A/B's interval. The A/B's intervals are too wide to tell the referees apart.
- Both referees put M0's own gain near the observed M − A, and its main effect below the observed one.
- For S, both predict a small gain where the A/B saw a loss. The intervals overlap.

## Two findings beyond the gates
- **A leaf changes few picks.** The leaf arms change the played pick at 4.4–5.7% of searched roots. Re-seeding the
  same search (NULL) changes 4.7%. Under the student_sel prior with the learned stop, a leaf's flips are about as
  frequent as search noise. Only the rollout student (STU), which replaces the rollouts, flips more (6.6%).
- **Act 4 never reaches a leaf.** At all 447 act-4 roots, the five leaf arms (M0, S, MS, G1B, TD2) ran identical
  searches: the same simulations, visits and Q for every action, and all picked the played action. Every act-4
  rollout ends in a death or a Heart kill, so act-4 decisions rest on the rollouts alone (CTM combats and the rollout
  policy). From act-4 roots those rollouts kill the Heart at 0.486, where real play kills it at 0.696.
  - So the stage-3 A/B's higher act-4 conversion under M0 (57.1% → 60.7% kills per arrival) comes from the states
    the runs arrive in, not from act-4 decisions.
  - Only STU and NULL change act-4 picks.

## Run notes
- Launched 09:05Z. W8–W31 restarted at 09:42Z after a container limit, and the last unit landed at 15:35Z: 6.5 h of
  wall against the PREREG's estimate of about 3 h.
- CPU: the seven side searches took 313 core-hours (69.5 s per searched root; the pilot measured about 40 s), and the
  referee took 11.0 core-hours (1,201,344 rollouts, 32.8 ms each). The played games come on top.
- There were no rollout errors, no non-terminal R_full rollouts, no arm errors and no excluded games.
- **Speed varies by container.** Per simulation, the median act-1 side search ranged from 3.8 to 12.1 ms between
  workers on the same binary.
  - Unit 111360180 ran twice, on W21 (5,733 s) and W24 (3,476 s), with identical records apart from `cpuSeconds`. The
    verifier used W21's tar (the first in name order); `tars.sha256` lists both.
  - The last unit, 111360219, took 4 h 10 min (median 1 h 25 min). It reached the Heart with 83 searched roots
    (median 71), ran on a slow container and started at 11:25Z.
  - Next time, once the queue is empty, a second copy of each straggler could run on an idle worker. Results are
    deterministic, so the first copy to finish is enough.

## Inference
- The plan's decision metric cannot gate stage 4 yet. Its referee has to match real outcomes first, and the
  rollouts are the problem. R_full's level is between a third and 70% of real play's. R_act helps where M0's value
  replaces most of the rollout (acts 1 and 2). In act 3 its gap is nearly R_full's, so the act-3 rollouts themselves
  die far too often.
- The predictions that do exist agree with the stage-3 A/B, for M0 in particular. They are the first prospective
  point, under a referee that did not qualify.
- Act-4 choices depend on rollout fidelity, not on any leaf. If act 4 loses HP or kills (canary: live Heart losses
  arrive with low HP), look at the rollouts' act-4 combats, not at V.

## Decision
None by itself (PREREG). Proposed next steps, each needing its own design:
- Gate stage-4 candidates on the guardrails (per-act calibration, drift) and on paired A/Bs, not on this metric.
- Check the CTM's act-4 predictions (Shield and Spear, the Heart) offline against the real outcomes of the stage-3
  A/B's 4,096 games.
- A referee closer to real play needs rollouts that play and fight more like real play, not a better leaf.
