# Fight-luck control variates for paired A20 A/Bs: offline estimate and the fight-replay mode (2026-10-26)

**Question.** Experiment 6 of the 2026-10-26 deep-research report (thread "Shrink A/B variance with AIVAT"): how much
of a paired A20 A/B's per-seed variance can AIVAT-style control variates at fight chance events remove, and what does
an unbiased version need? No new gameplay seeds.

## 1. Offline estimate (existing corpora only)

**Data.** The unit tars of §676 (`/mnt/project-files/ctm-calibration-ab/units`, 512 seeds × A, C), §661
(`value-level-ab`, 1,024 × A, M, S, MS) and §683 (`ooc-map-only-search`, 1,024 × OFF, MAP, D): six paired
comparisons, all runs integrity-passed; every run ends in a fight death or a Heart kill. Per-arm kill rates reproduce
the recorded results.

**Estimator.** Per run, `Y_hat = Y - beta * sum_k [V(post_k) - E(pre_k)]` over a set of fights k. `V` = xgboost
P(Heart kill | post-fight state) (act, floor, HP, gold, potions, 150 card ids, upgrades, 120 relic ids), cross-fitted
by campaign (each campaign scored only by a model trained on the other two); 0 after a death, the outcome after the
Heart. Baselines `E`: (pass 1) a second GBM on the pre-fight state; (pass 2) the A20 default CTM stack at main
`8cce22b` (`ctmscorerows` with the winning-HP histogram, a local uncommitted print patch), `E = (1 - p_death) *
sum_h P(h) V(post with HP h)` with the same V, Heart `E = 1 - p_death`. Replay projection: `m` fresh replays per
corrected fight make `E` exact and add `beta^2 * sum_k Var_k / m` (Var_k from the CTM), beta variance-optimal.

**Result** (paired SD relative to raw; raw paired SD 0.39-0.44, unpaired ~0.60; mean over the 6 comparisons
[range]; `variance2.json`):

| fights corrected | CTM baseline, no replay | replay m = 1 | m = 2 | m = 4 | m = 8 |
|---|---|---|---|---|---|
| Heart only | 0.73 [0.70, 0.76] | 0.89 | 0.84 | 0.80 [0.78, 0.82] | 0.77 |
| bosses + Act 4 | 0.61 [0.58, 0.64] | 0.86 | 0.79 | 0.73 [0.72, 0.74] | 0.68 |
| all fights | 0.62 [0.56, 0.66] | 0.85 | 0.78 | 0.71 [0.70, 0.72] | 0.66 |

- The CTM-only baseline is **biased**: it moves the six point estimates by -2.0 to +3.2 pp (all fights), and two
  shifts exclude 0 (§661 S-A -1.37 -> +1.39 pp; §683 D-OFF 0.00 [-2.64, +2.64] -> +3.18 [+1.43, +4.95]). Its
  per-arm correction means are +1 to +7 pp, so V and the CTM are not mutually consistent and the inconsistency
  differs by arm. Not usable as a primary metric.
- Pass 1 (separate learned baseline): Heart-only 0.64-0.71x, but summing over all fights raised the SD to 1.4-2.4x.
- Fight HP/death luck is about 60-65% of the paired variance; the rest (OOC reveals, potion use, real decision
  effects) is untouched.
- Projected minimum detectable effect at 1,024 paired seeds (80% power, 5% two-sided): ~3.6 pp raw, ~2.6 pp with
  all fights at m = 4.

## 2. `one_combat fightreplay` and its identity gate

`apps/one_combat/fight_replay.cpp` re-plays recorded real fights (heartoutcomegen `combat_transition_row_v2` rows
plus a `replayContext` built by `tools/fight_replay_rows.py` from the same run's trajectory: keys, map node, second
Act-3 boss) under the process's real-combat configuration. Real combat is a deterministic function of the run seed,
floor and recorded pre-combat state (BattleContext::init seeds four streams and the Silver planner from seed + floor
and carries misc/potion; the agent RNG is never drawn in combat), so replicate 0 with the recorded seed must
reproduce the recorded outcome and post state byte for byte; any difference fails the mode. Replicates >= 1 redraw
the seed and the carried streams (counters kept). `tools/aivat_estimate.py` trains the frozen V on other campaigns
and computes the paired estimate with `beta = m / (m + 1)`.

**Identity check.** §676 units 111392000-111392008 (18 runs, 415 fights incl. burning elites, all bosses and 8
Hearts), current main + this change, the units' frozen env with `STS_OOC_HEART1` pointed at the same student_sel
(`cf6bf7fb`) and `STS_SILVER_ACT4_STRONG=0` (§676 predates #852): **415 of 415 reproduced exactly**.

**Cost** (same runs, identity replays): real combat is ~86 CPU-s per run under §676's config (act-1 boss 8.7 s,
act-2/3 bosses 22-28 s, Heart 22.6 s; hallway fights < 1.5 s). Bosses are ~70% of it, so replaying all fights costs
about the same as bosses only. Under today's Act-4 strong default the Heart costs more (not measured here).

**Fresh-replicate smoke.** The 62 boss fights of the same 18 runs, 2 fresh replicates each (`SEED_BASE` 7700001):
all 62 identity replays exact again; 60 of 62 fights had at least one replicate whose outcome or end HP differs
from the recorded fight. Fresh battle seeds depend on (SEED_BASE, run seed, fight index, replicate), so the two arms
of a seed share them (common random numbers across arms). `tools/aivat_estimate.py estimate` ran end to end on these
9 seed pairs (V trained by `train` on the §661 + §683 units, sha256 `8efcc81f…`); 9 pairs say nothing about the
variance, which is what the pilot measures.

**Pilot proposal (not run).** Post-hoc replay of the §676 guard: its ~24,000 non-event fights, identity + m = 4 fresh
replicates under the frozen env above, V = the §661 + §683 model, `beta = 0.8`. Projected cost ~5 × 86 CPU-s × 1,024
runs ≈ 120 CPU-h (16 cloud workers × 4 lanes ≈ 2 h). Projection to test: paired SD ratio ~0.71 (0.70-0.72 across the
six offline comparisons); the corrected C-A difference must agree with the raw +2.15 pp within noise. Needs
Philipp's typed authorization and worker count.

## Files
- Offline estimate: `extract2.py`, `analyze.py` (pass 1), `ctmrows.py` + patched `ctmscorerows`, `analyze2.py`
  (pass 2), `variance.py` / `variance2.py` -> `variance.json` / `variance2.json`.
- Write-up: https://claude.ai/artifact/RBaP5FZd1RXijtmYosQjsC
