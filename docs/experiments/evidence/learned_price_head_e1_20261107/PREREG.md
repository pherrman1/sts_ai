# E1 of the learned price head: fight luck against the leaf pilot's CRN pairs (pre-registration, 2026-11-07)

Status: **FROZEN for launch** once `campaign.manifest` carries `code_commit` and `binary_sha256` and the prelaunch
review has passed. Nothing in this file was written after any E1 row existed; the author's smoke (below) was read
only for identity and cost.

## Question

Philipp's idea (2026-11-07, 09:31 CET): a net that guesses Silver's price table per encounter from the whole-game
context, trained in a loop like the OOC net. The design doc (https://claude.ai/artifact/PzKavVUBmYiitvHLFhg7qp)
proposes to train such a price head on two kinds of labels: fight luck (one fresh replay of each fight; cheap, HP
and potions only) and CRN fork pairs (the leaf pilot's labels; every field, expensive). E0 (offline, §698 replays,
student_sel with production combat) found an HP price of 0.109 ± 0.035 pp per HP from fight luck (z = 3.1).

E1 asks: **under the leaf pilot's policy and combat, on the same source runs, does fight luck give the same HP
price at the fight end as the pilot's CRN pairs?** If it does, the expensive label factory is only needed for the
fields luck cannot see (max HP, gold, counters).

Philipp's go (project chat, 2026-11-07 17:45 CET, "jap find ich gut, mach das") answered the coordinator's plan: E1 on
the pilot's seeds, about 88 core-h, started after the pilot's stop at 21:38 CET so it does not compete with the
pilot's workers.

## Setup

**Source runs = the leaf pilot's.** E1 replays the pilot's first seed block, **111780000-111788191** (8,192 seeds,
the pilot's units 1-1,024; at 18:15 CET 1,010 of them were uploaded and two had failed in continuations). No new
seeds. The policy and combat are the
pilot's, unchanged (`../fight_end_pairs_pilot_20261107/PREREG.md`):

- net-0420 (sha256 `8c0bd16c…`) plays the whole out-of-combat part (`ooc=ppo`, `STS_OOC_HEART1_PPO=1`,
  temperature 0, salt 0, `STS_OOC_MCTS=0`);
- combat B: flat Silver 1,000 sims per root, learned stop and Act-4 strong off, g7f_E root and tree prior, default
  leaf;
- `run_unit.sh` sets exactly the pilot's environment.

**Generator call.** Each unit runs
`one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,luck=1,luck_identity=1 -`:

- `n=0`: no forks. The source run is the pilot's; the reservoir only counts eligible fight ends.
- `luck=1`: at the start of every source fight (all rooms, acts 1-4), one detached copy of the state plays only that
  fight on fresh streams: a new battle seed (combat streams and Silver planner) and new carried misc/potion streams
  with their counters kept, as `fightreplay` redraws them (E0's instrument). The copy gets its own agent with the
  fight's budget and exits the battle as the run does. One `luck` row per fight holds the real fight end and the
  replayed one.
- `luck_identity=1`: the unit's first seed also replays each fight unchanged (replicate 0), which must reproduce the
  real fight exactly.
- The replays never touch the run (own copy, own agent; the run's health counters and battle-exit hooks restored).
  `fightendpairselftest full` checks that source and fork rows are identical with and without `luck=`.

**Engine.** Code commit `065e4280` = the pilot branch (#1003, c3433e78) + `luck=`, `luck_identity=`, `n=0` and
the fight-start hook of `finishOocCounterfactual` (default off); binary `26775caf3c986e38…` (preset
linux-gcc-release-x86-64-v3; the same build of the pilot tip reproduced the pilot's binary `968615927ae7fc8d…`
exactly). RUN_COMMIT = this campaign's commit on top.

**Units and workers.** 512 units of 16 seeds (`units.txt`); 20 workers with 4 lanes each, queue schedule. No stop
rule: every unit runs. A unit that fails all four attempts is dropped whole and listed in the RESULT.

**Expected cost.** The pilot's 8,080 uploaded source runs of this block used 20.6 s CPU each on average (median
12.8 s). In the smoke one fresh replay per fight cost 0.88 of the source run, and the source run itself 7% more
than the pilot's on the same seeds. With the identity replays (one seed in 16) that is about 41 s per seed, so
8,192 × 41 s ≈ **94 core-h** (about 90-100). The go's "about 88 core-h" assumed 14 s per source run (the pilot's
first unit). A unit takes about 11 min (5-25 min); 20 workers × 4 lanes need about 1.5 h.

## Smoke (author, before freezing)

The frozen binary (the draft build had the same sha) with the pilot's environment in a cloud container:

- seeds 111780000-111780007 (the pilot's first unit), `luck=1`, identity replays on all eight: G1 8 of 8 source
  rows equal to the pilot's; G2 32 of 32 fork states equal; G3 143 of 143 identity replays reproduce their fight
  (every act × room cell of acts 1-4, two Heart fights); no replay errors;
- seeds 111781809 and 111786448 (in the pilot's two failed units): the source runs play through with `luck=1`
  (the pilot's failures were stalls in continuations, which E1 does not play); no replay errors;
- CPU as under Expected cost.

Only identity flags, error counts and CPU were read; no luck value and no replay outcome was looked at.

## Validity gates (checked before any outcome is analysed)

- **G1 source identity.** For every seed with an E1 and a pilot source row, the rows agree in `valid`, `won`,
  `heartKill`, `floor`, `fightEnds`, `eligible`, `ineligible`, `ppo` and `cost.silverSimulations`. Any mismatch:
  **INVALID** (the replays changed the run); fix, no analysis.
- **G2 fork identity.** For every pilot fork (seed, fightIndex) with a base copy, E1's luck row of that fight has
  `real.state` equal to the base copy's `state`. Any mismatch: **INVALID**.
- **G3 replay identity.** On the identity seeds (the first seed of each unit, 512 runs), every replicate-0 replay
  reproduces its real fight (`identity` true). Any mismatch: **INSTRUMENT_FAIL**, reported by encounter; no ratio
  decision.
- **G4 replay health.** A fight whose fresh replay threw (`error`) or had a simulator health failure leaves the
  luck regressors (its luck stays in the residual; the replay is independent of the run given the fight start, so
  this does not bias). More than 2% of fights in acts 1-3: **INVALID**.
- **G5 exchangeability.** Mean luck u = y_real − y_replay of HP and of survival, per act × room class (acts 1-3,
  NORMAL, ELITE, BOSS, OTHER; cells with at least 100 fights): |z| < 3.5 in every cell. Otherwise
  **INSTRUMENT_FAIL** (the replay is not a draw of the same fight).

## Analysis (`analyze.py`, pre-registered)

**Rows.** E1 units count with rc 0 and 16 source rows (per unit id the first tar that counts: every attempt of a
unit replays the same deterministic runs). Pilot units count as in the pilot's `analyze.py` (its first tar per
unit id, rc 0 and 8 source rows). The comparison uses the seeds present in both (set S); the pilot's failed units
leave S, and β_luck on all E1 seeds is reported as well.

**Luck regression (as E0, M = 1).** For each fight f with a valid replay, y = s·(1, HP, potions, max HP, gold,
upgrades, misc, counter relics), s = won (combat victory), counter relics = relic ids whose data differs between the
real and the replayed end in at least 50 fights (outcome-blind). u_f = y_real − y_replay. Per source run g, sums of
u_f over its fights form the regressors:

- survival s_a and potions k_a for acts a = 1, 2, 3 (rooms NORMAL, ELITE, BOSS);
- **HP h_a123, pooled over acts 1-3 (rooms NORMAL, ELITE, BOSS): primary**;
- controls pooled over acts 1-3: max HP, gold, upgrades, misc, counters; event fights (room OTHER, acts 1-3):
  survival, HP and potions as own columns;
- act 4 as E0: s_ss, h_ss, k_ss (Shield and Spear) and s_heart.

R_g = the source run's `heartKill`. OLS with intercept, HC1 standard errors. With one replay the regressor is
y_real − y_replay, whose variance is twice the luck variance, so every luck coefficient is scaled by
(M + 1)/M = 2. **β_luck** = 2 × coefficient of h_a123, in pp per HP.

**CRN slope.** Pilot forks in acts 1-3 (seeds in S) with a valid base copy and at least one valid HP copy
(`hp:-3`, `hp:-8`, `hp:-15`). Per fork i, the least-squares line through the origin over its valid HP copies,
θ_i = Σ_k k·(y_base − y_k) / Σ_k k², y = `heartKill`. Each fork gets the weight w_i = π_i⁻¹ · v_i:

- π_i⁻¹ = eligible / sampled of its source run (the pilot's inverse inclusion probability, its deviation 1);
- v_i = the luck weight of its fight. The pooled OLS coefficient weights each fight's price by the variance of its
  HP luck net of the other regressors, a property of the fight start. v_i estimates it without the fork's own
  luck: the mean of ũ_f² over E1 fights in the same cell (act, encounter, start-HP band 1-30 / 31-50 / 51+), where
  ũ_f is the fight's HP luck minus its least-squares fit on the same fight's survival, potion, max-HP and gold luck
  (fight level, per act). A cell with fewer than 30 fights falls back to (act, room, band), then (act, room).

**β_CRN** = Σ w_i θ_i / Σ w_i, in pp per HP. With both weights, β_luck and β_CRN estimate the same luck-weighted
mean of fight-end HP prices over all won NORMAL/ELITE/BOSS fights in acts 1-3.

**Ratio.** ρ = β_luck / β_CRN on S. CIs: percentile bootstrap over the source seeds of S, 2,000 resamples, seed
20261107. Each resample refits the OLS (resample counts as row weights) and recomputes β_CRN on the same seeds; the
v weights stay fixed.

## Decision (pre-registered)

1. INVALID or INSTRUMENT_FAIL if a gate fails (see above).
2. **INCONCLUSIVE (CRN unresolved)** if β_CRN ≤ 0 in more than 2.5% of the resamples.
3. **GO** if the 90% CI of ρ lies inside [0.67, 1.5]. Luck labels then train the price head for HP; a ρ ≠ 1 inside the
   band is reported as a calibration factor.
4. Otherwise **FAIL** if the 95% CI of ρ excludes 1.
5. Otherwise **INCONCLUSIVE**.

No default changes in any case; `luck=` stays a research option.

## Descriptive

- β_luck and β_CRN per act and per act × room (same weights; per-act and per-room HP columns in their own fits);
  the pilot's own β (π⁻¹ weights only) on S and its ratio to β_luck.
- Potion price: 2 × k_a against the CRN `pot` copies (y_base − y_pot, weights π⁻¹); survival values 2 × s_a.
- Luck variance per game by act (HP², potions²), residual variance, fights per game: the inputs of the design doc's
  cost model under net-0420.
- β_luck on all E1 seeds (not only S).
- Cost: CPU per source run and per replay by act; replay errors and health failures; identity statistics.

## Deviations

Deviations are reported in the RESULT.
