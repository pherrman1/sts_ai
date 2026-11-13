# Cheap rollouts, stage 2: playout policies at prior-playout roots of G16 runs (pre-registration, 2026-11-13)

**Authorization.** Philipp, 2026-11-13, thread "Design cheaper guided combat rollouts": after the plan
(`/mnt/project-files/cheap-rollouts/PLAN.md`, stages 0-2) he wrote "Let's go all auf 40 worker" (14:23 CET). This is
a data run on §797's seeds, not a gate; a whole-run gate of a candidate needs the stage-2 result first.

AUTHORIZATION: Philipp, 2026-11-13 14:23 CET, in this thread: "Let's go all auf 40 worker" (stages 0-2, 40 workers).

## Background

- §790 (E0): G16 without its prior playouts (boss rooms, Act 4) loses 5.5 pp Heart at 0.27× CPU. §792: about 70 % of
  G16's edge comes from Act 1-3 boss prior playouts. Step 0 (#1034): bosses and Act 4 hold 86 % of G16's CPU, at
  74-172 µs per simulation against 7-19 µs in hallway fights.
- Stage 0 (this thread, `one_combat rolloutpolicybench`, 20 §797 boss roots at 2k): a prior playout costs about 25
  g7f_E calls per simulation at 6 µs each, 85 % of it in the MLP and 15 % in feature extraction (182 µs/sim vs 17 for
  greedy playouts with the root table).
- Stage 1 (this thread, 3,000 §797 boss roots, 1.14 M captured playout prior calls): a 32/16 student distilled from
  g7f_E's playout distribution has KL 0.023 nats on held-out seeds (fold 4) and its pick carries on average 95 % of
  the teacher's top probability (top-1 64 %: the teacher's playout distribution is flat, top probability 0.36 over 5.1
  edges). It costs 2.2 µs per call; once per playout turn (turn table) it needs 9.7 instead of 24.9 calls per
  simulation. Measured at 2k: student every step 0.55× and student turn table 0.32× the prior playout's CPU per
  simulation; g7f_E turn table 0.49×; prior in the first playout turn only 0.23×.

## Question

At G16's prior-playout roots, does a cheaper playout policy choose root actions as well as the g7f_E prior playout at
the same CPU, and nearly as well as G16's own 16k search at a fraction of its CPU?

## Data run

- **Generator.** `one_combat silverazgen` with §797's environment ([record_env.sh](record_env.sh): §775's G16 arm,
  net-0420 out of combat, whole-run Gumbel root k 16 at 16,000 with max backup 4, boss prior playouts, Act 4 strong),
  without §797's budget ladder, plus `STS_AZGEN_ROLLOUT_LADDER`.
- **Arms.** After the played search of every searched multi-edge root whose played search uses prior playouts (boss
  rooms of Acts 1-3, Shield and Spear, the Heart), one fresh searcher per arm, configured as the played one (same root
  prior, tree prior K 8, root table, max backup, Gumbel k 16; no reuse) except for its playout policy, with its own
  Gumbel seed:

  | arm | playout policy |
  |---|---|
  | asplayed:4000 | g7f_E prior every playout step (as played), 4,000 sims: cross-check of §797's 4k ladder pick |
  | greedy:16000, greedy:64000 | greedy SilverRolloutAgent with the g7f_E root table (GP16's boss playouts) |
  | tt:16000 | g7f_E once per playout turn (turn table: best-scored legal edge of the turn's table) |
  | ft1:16000 | g7f_E prior in the playout's first turn, greedy after |
  | st:16000 | 32/16 student (`students/s32.txt`) every playout step |
  | sttt:16000 | the same student once per playout turn |
  | ste:16000 | per-encounter 32/16 students (`students/enc_*.txt`, warm-started from s32) every step |

  Students: trained offline on 2,400 roots of seeds with seed % 5 in 0-3 (silver_az_mlp.py train, fold 3 early
  stopping), [tools/cheap_rollouts](../../../../tools/cheap_rollouts). Each pick is recorded as an index into the
  played root's edges, with thread CPU seconds, rolloutPrior calls and playout actions.
- **Reference.** As §797: each pick is scored by the played tree's max-backed Q of that edge (16k with reuse, prior
  playouts). This favours picks like the played search's; that bias works against every cheap arm, so it makes the
  result conservative for them.
- **P1 frontier.** §797's ladder picks of the same roots (g7f_E prior playouts at 1k, 2k, 4k, 8k, 16k, fresh
  searches). Their CPU is scaled to this run's machines per run by the ratio of the played search's CPU (`mainCpu`,
  the same search in both runs). The new asplayed:4000 arm checks the scaling (its CPU vs §797's 4k ladder CPU after
  scaling).
- **Seeds.** 111980000-111980255 (§797's block: the same 256 games). `run_unit.sh` refuses any other seed.
- **Sentinel.** Every run's played choices (`chosen` per root row) must equal §797's rows of that seed. A run that
  differs is reported and dropped from the analysis; more than 8 differing runs → the run is INVALID (play is not
  bit-identical).
- **Code / binary.** Code commit and binary sha256 in campaign.manifest.

## Analysis (frozen with this file)

- **Units that count.** Units with rc 0 that `verify_campaign.py` lists as OK and that pass the sentinel. More than 20
  of 256 runs dropped → INCOMPLETE (reported, no candidate declared).
- **Rows.** Searched multi-edge prior-playout roots where every new arm and all five §797 ladder picks are matched
  (edge ≥ 0) and every picked edge has a finite max-backed Q. Drops counted by reason.
- **Loss per root and arm.** loss = Q_ref(best) − Q_ref(pick), Q_ref the played tree's max-backed Q, best its maximum
  over visited edges (Silver score units). Mean loss and mean CPU per arm over all rows.
- **Calibration (must hold).** loss(greedy:16000) − loss(P1 16k) > 0 with a run-clustered bootstrap 95 % CI above
  0. Otherwise the metric does not reproduce §790's ordering: result INVALID_METRIC, no candidate.
- **P1 frontier function.** F(c) = the lower convex hull of the five P1 points (mean CPU, mean loss), linearly
  interpolated in CPU; below 1k's CPU, the line to (0, loss of the prior's top action).
- **Per candidate C in {tt, ft1, st, sttt, ste}:**
  - Δ_C = loss_C − F(CPU_C): better than P1 at the same CPU when negative;
  - r_C = CPU_C / CPU(P1 16k);
  - g_C = (loss_C − loss(P1 16k)) / (loss(greedy:16000) − loss(P1 16k)): share of the greedy-to-prior gap left.
  Run-clustered bootstrap (10,000 resamples, seed 20261113) at 99 % (Bonferroni for 5 candidates). CPU is resampled
  with the loss, so F is evaluated at each resample's CPU_C.
- **Decision rule (as in the plan).** C is a **GATE_CANDIDATE** if r_C ≤ 0.35, the CI upper bound of
  loss_C − loss(P1 16k) is ≤ 0.25 × the gap point estimate, and Δ_C's CI upper bound is < 0. **CHEAPER_EQUAL** if only
  Δ_C's CI upper bound is < 0 (beats P1 at the same CPU, but not near 16k at ≤ 0.35×). Otherwise **NOT_SHOWN**.
  If any GATE_CANDIDATE exists, the one with the smallest r_C goes to a whole-run gate against §775's G16 (PLAN.md;
  its own pre-registration and Philipp's go). No candidate → ledger, the cheap-playout line is parked or redesigned.
- **Co-reported.** Everything per encounter (Heart, Act-3 bosses, Act 1-2 bosses, Shield and Spear); greedy:64000 on
  the frontier; the asplayed:4000 CPU check; prior calls and playout actions per simulation per arm; fold-4 seeds
  (held out from student training) separately for st, sttt and ste.
- **Not in this run.** Philipp's hypernetwork idea (a model that writes a tiny per-encounter/context playout model):
  its offline upper bound (a tiny model fitted per root, tools/cheap_rollouts/tiny_oracle.py) is run in the thread; a
  hypernetwork arm would be a follow-up.
