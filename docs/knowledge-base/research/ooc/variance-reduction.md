# OOC rollout variance reduction

Last verified: 2026-10-27 against `main` `ed2dcb2b` (issue #883, phases 1–2; offline decomposition §TBD).

## Purpose / research question

Which unbiased, fair-RNG methods give the most precision per CPU-hour for OOC action comparisons (sibling value
differences) and for rollout labels? Related: #881 (sibling noise and bias by root type), #882 (prior versus
search). This page covers estimators, not which teacher is right: variance reduction cannot remove a systematic
teacher or CTM bias (#884).

## Current conclusion

- **The CTM death draw dominates rollout3 noise.** In the §644 common-seed capture it carries 88% of leaf variance and
  87% of sibling-difference variance ([evidence](../../../experiments/evidence/ooc_variance_reduction_audit_20261027/README.md),
  §TBD; pre-calibration CTM, so today's share is likely lower).
- **Candidate 1, go for a small experiment: conditional Monte Carlo on survival** ("survival-weighted rollouts").
  The CTM's survival probability is known at every rollout combat, so the death draw can be integrated out exactly.
- **Candidate 2, go for a small experiment: event-keyed streams.** Today's common seeds share one sequential stream,
  which desynchronises once siblings take different numbers of draws. Map and boss-relic siblings keep the least
  coupling (CRN ratio 0.73–0.87 depending on weighting, against 0.30 at rest sites).
- Latin-hypercube/antithetic draws, martingale control variates and adaptive allocation are sound but second-order
  until candidate 1 is measured. Multilevel Monte Carlo and general importance sampling are not recommended (below).
- No default change follows from this page. Either candidate changes leaf values and therefore play; a play-changing
  use needs its own paired A/B.

## What is implemented (phase 1)

| path | estimand | randomness | coupling between siblings |
|---|---|---|---|
| Live OOC MCTS (A20 default) | rollout3 value: up to 3 CTM combats, greedy heart1/student_sel steps, then the M0-calibrated X2-B (ADR-0057); one rollout per simulation | `OocMctsPlanner` owns one `mt19937_64`; every simulation continues the same sequence (`src/sim/search/OocMctsPlanner.cpp`) | none: each child's Q averages independent draws |
| Sibling capture (`STS_OOC_SIBLING_CAPTURE`, research) | mean of R rollout3 repeats per root child | repeat r seeds `seed_seq{searchSeed, decision, leafKey, kind, r}` (`ooc_mcts_adapter.cpp`, `siblingLeafExtras`) | `STS_OOC_SIBLING_COMMON_SEEDS=1` sets `leafKey` to a constant, so repeat r of every child starts from the same stream (§639, §644) |
| Campfire price observer (§695) | N rollouts per rest action to the next act | streams shared by the actions | same start-of-stream coupling |
| Real-combat forks (stage tables §684, P300 §692, boss-relic forks §690, `act4replay`) | real Silver fights | shared battle seed and Silver planner seed | same native seeds; the shuffle of a deck of different size desynchronises |
| Paired whole-game A/B | Heart kill | same game seed per pair | identical until the first divergence (rho 0.49 after it, §685); AIVAT replay correction SD ratio 0.80 (#872) |

Where rollout randomness is consumed (`evaluateLeafUnobserved`):
- `sampleNoncombatFuture` before every non-combat step and leaf: a new run seed, 14 re-seeded native streams, shuffles
  of five relic pools and the colorless pool, resampled unseen monster/elite queues, the hidden A20 second boss, chest
  contents. The number of draws depends on pool sizes and on how many steps the rollout takes.
- `resolveCombat` → CTM sampler: `uniform() >= survival` is a death; on survival, inverse-CDF draws for max HP, the HP
  class (`hpClasses` are consecutive integers, so the draw is monotone in HP), potions, relic residues, and in the
  near-full CTM an escape draw (only when eligible), a potion loop of variable length, and event draws.
- Rollout policy steps are greedy argmax and draw nothing.

So "same seed" couples siblings only while they consume identical draw sequences. A death ends a rollout after one
draw; a victory takes eight or more. Different rooms, potion states or relic pools shift every later draw.

## Candidates (phase 2)

### 1. Conditional Monte Carlo on combat survival — GO (experiment)
Estimator: at each rollout combat k with CTM survival s_k, draw the post-combat state from the CTM conditioned on
survival (skip the death draw, keep escape), continue, and return W·V_end with W = Π_k s_k; a rollout that ends in a
victory terminal returns W. This is sequential importance sampling with the exact likelihood ratio between the
"always survive" proposal and the CTM, or equivalently Rao–Blackwellisation of each death indicator (conditional
Monte Carlo, Asmussen & Glynn 2007, ch. V.4).
- **Estimand:** unchanged. E[W·V_end] equals today's rollout3 expectation exactly, because the CTM probability used
  as the weight is the probability the sampler uses. (Contrast #872's CTM-only correction, which was biased because the
  CTM is not the real fight; here the CTM *is* the rollout's fight.)
- **Variance:** W ∈ (0, 1], so no importance-weight blow-up. The §644 decomposition suggests a large gain on both
  labels and sibling differences; the indicative one-event bound (≈ 0.08) is optimistic.
- **Cost:** rollouts that would have died continue to the horizon: roughly 1/(1 − 0.13) more combats per rollout at
  ~7.6 ms CPU per rollout3 repeat (§644 capture). Code: expose `survival()` on `PreparedCombatTransition` and the
  unprepared sampler, call the near-full sampler with survival 1 (the existing `sampleConditionedVictory` also forbids
  escape, which would bias Smoke Bomb states), carry W out of `evaluateLeafUnobserved`. One research flag, default off.
- **Failure modes:** Lizard Tail and other non-death branches must keep their own conditioned path; imagined fights
  resolved by native Silver (`playImaginedCombatWithSilver`) have no known survival probability and keep sampling;
  in-tree combat chance nodes are unchanged (only leaf rollouts). A changed leaf changes MCTS play, so any live use is a
  separate A/B.

### 2. Event-keyed (semantic) random streams — GO (experiment)
Estimator: unchanged rollout; only the source of uniforms changes. Each random event takes its own substream keyed by
public identity, e.g. `(repeat seed, act, floor, event kind, occurrence on that floor)` for `sampleNoncombatFuture`
and for each CTM combat, instead of continuing one sequential stream (substreams: L'Ecuyer et al. 2002; counter-based
generators: Salmon et al. 2011).
- **Estimand:** unchanged when keys are unique within one trajectory: every event then gets independent uniforms, as
  now. A key reused within a trajectory would correlate two events and must fail loudly.
- **Expected gain:** siblings keep using the same uniforms for "the fight on floor f" even after their draw counts
  diverge, and the CTM's inverse-CDF HP draw then gives the monotone (comonotone) coupling that is variance-minimising
  for monotone responses (Glasserman & Yao 1992). Largest where today's coupling is weakest: map and boss relic
  (≈ 0.82–0.87 pooled over row pairs), shop (≈ 0.52).
- **Cost:** a seeded `mt19937_64` per event; small. Draw order inside a combat is fixed, so the near-full CTM's
  variable potion loop needs its own subkey after the HP draw to keep relic draws aligned.
- **Placeholder / deck-slot coupling** (issue #881's idea) matters only for real-combat forks, not for rollout3 (the
  CTM sees the deck, not its order). For real fights one would have to keep pile sizes equal with an inert slot that
  every count, draw and shuffle ignores; this touches many card and relic effects and risks biasing the fight.
  **NO-GO for now**: §684 already reached CRN fight correlation 0.68, and the expensive real-fork lines are stopped.

### 3. Antithetic variates / Latin hypercube across repeats — DEFER
With keyed streams, the death and HP uniforms of each combat can be stratified across the R repeats of a leaf (Latin
hypercube, McKay, Beckman & Conover 1979), which keeps every marginal uniform and is never much worse than plain Monte
Carlo (variance ≤ N/(N − 1) of it, Owen 1997). Antithetic pairs (u, 1 − u; Hammersley & Morton 1956) help only if the
value is monotone in the uniforms, which holds for the first combat's HP but not after branching. Repeats then stop
being independent, so standard errors need independent batches. Worth testing only after candidate 1, because it
mostly attacks the same death draw.

### 4. Control variates / martingale correction — DEFER
Henderson & Glynn (2002) and AIVAT (Burch et al. 2018): add Σ_k [g(X_k⁺) − E g(X_k⁺ | X_k)] with a cheap value g;
unbiased for any g when the conditional expectation is exact (here: over the CTM's HP classes). After candidate 1
removes the death term, the remaining HP term needs one X2-B call per HP class, so the gain per CPU is unclear. A
fitted coefficient must be cross-fitted (Chernozhukov et al. 2018) to stay unbiased in small samples. The
whole-game version is #872 (SD ratio 0.80).

### 5. Multilevel / multifidelity Monte Carlo — NO-GO
MLMC (Giles 2008, 2015; Peherstorfer, Willcox & Gunzburger 2018) needs a cheap level whose coupled difference from the
target has small variance. The target here *is* rollout3; the cheaper levels (direct X2-B, rollout1) are
deterministic or share most of its draws already. For longer targets (act end), §607 found coupling collapses with
horizon (paired SD +50%), which is exactly what MLMC needs not to happen.

### 6. Adaptive allocation / sequential stopping — LATER, via #881
For labels and root comparisons, allocate repeats to pairs with high difference variance (KN procedure with CRN, Kim &
Nelson 2001; OCBA, Chen et al. 2000) and stop at an ε-gap (LUCB, Kalyanakrishnan et al. 2012). Optional stopping
biases the selected arm's mean and invalidates fixed-n intervals unless anytime-valid confidence sequences are used
(Howard et al. 2021). MCTS is already adaptive and the OOC gap-ladder stop exists (ADR-0053); #881's sibling gap
distribution decides whether more is worth it.

### 7. Importance sampling / off-policy evaluation — NO-GO (except candidate 1)
The rollout policies are greedy and deterministic, so another policy's actions have no support and per-decision
ratios do not exist (Precup, Sutton & Singh 2000). The only valid ratio found is candidate 1's, where the proposal
differs only at a chance event with known probability.

## Phase 3 protocol (proposed, not run)

Frozen roots: reuse #881's cohort if it exists by then; otherwise replay already-used seeds of one A20 campaign at the
current default (as §695 did) to reach ~48 CARD_REWARD roots plus ~16 map roots. No new seeds.
Arms at each root, all legal children, same continuation policy: A current common seeds; B candidate 1; C candidate 2;
D B + C; E independent streams (control). R = 32 repeats × 8 independent batches (distinct search seeds) per child
and arm. Measured: variance of the sibling difference across batches (the target), mean difference between arms per
child (bias check: B − A within ±2 SE), CPU per repeat, effective repeats per CPU-hour, and the screen split.
Pre-registered rule: a candidate is useful if it cuts sibling-difference variance per CPU-second by ≥ 2× with no
bias flag; NOT_USEFUL at ≤ 1.25×. Cost: ≈ 64 roots × 6 children × 256 × 5 arms ≈ 0.5 M rollouts, about 1–2 core-h
plus the replays.

## Sources
- Asmussen, S. & Glynn, P. W. (2007). *Stochastic Simulation: Algorithms and Analysis*. Springer. Ch. V.
- Burch, N., Schmid, M., Moravčík, M., Morrill, D. & Bowling, M. (2018). AIVAT: a new variance reduction technique for
  agent evaluation in imperfect information games. AAAI.
- Chen, C.-H., Lin, J., Yücesan, E. & Chick, S. E. (2000). Simulation budget allocation for further enhancing the
  efficiency of ordinal optimization. *Discrete Event Dynamic Systems* 10, 251–270.
- Chernozhukov, V. et al. (2018). Double/debiased machine learning. *Econometrics Journal* 21(1), C1–C68.
- Giles, M. B. (2008). Multilevel Monte Carlo path simulation. *Operations Research* 56(3), 607–617; (2015) Multilevel
  Monte Carlo methods, *Acta Numerica* 24, 259–328.
- Glasserman, P. & Yao, D. D. (1992). Some guidelines and guarantees for common random numbers. *Management Science*
  38(6), 884–908.
- Hammersley, J. M. & Morton, K. W. (1956). A new Monte Carlo technique: antithetic variates. *Proc. Cambridge Phil.
  Soc.* 52, 449–475.
- Henderson, S. G. & Glynn, P. W. (2002). Approximating martingales for variance reduction in Markov process
  simulation. *Mathematics of Operations Research* 27(2), 253–271.
- Howard, S. R., Ramdas, A., McAuliffe, J. & Sekhon, J. (2021). Time-uniform, nonparametric, nonasymptotic confidence
  sequences. *Annals of Statistics* 49(2), 1055–1080.
- Kalyanakrishnan, S., Tewari, A., Auer, P. & Stone, P. (2012). PAC subset selection in stochastic multi-armed
  bandits. ICML.
- Kim, S.-H. & Nelson, B. L. (2001). A fully sequential procedure for indifference-zone selection in simulation.
  *ACM TOMACS* 11(3), 251–273.
- L'Ecuyer, P., Simard, R., Chen, E. J. & Kelton, W. D. (2002). An object-oriented random-number package with many
  long streams and substreams. *Operations Research* 50(6), 1073–1075.
- McKay, M. D., Beckman, R. J. & Conover, W. J. (1979). A comparison of three methods for selecting values of input
  variables in the analysis of output from a computer code. *Technometrics* 21(2), 239–245.
- Owen, A. B. (1997). Monte Carlo variance of scrambled net quadrature. *SIAM J. Numer. Anal.* 34(5), 1884–1910.
- Peherstorfer, B., Willcox, K. & Gunzburger, M. (2018). Survey of multifidelity methods in uncertainty propagation,
  inference, and optimization. *SIAM Review* 60(3), 550–591.
- Precup, D., Sutton, R. S. & Singh, S. (2000). Eligibility traces for off-policy policy evaluation. ICML.
- Salmon, J. K., Moraes, M. A., Dror, R. O. & Shaw, D. E. (2011). Parallel random numbers: as easy as 1, 2, 3. SC'11.

## Relationships
- Evidence: §639, §644 (common seeds), §607 (CRN horizon), §684 (real-fight CRN), §685 (whole-game sibling rho),
  §695 (campfire price precision), #872 (AIVAT replay).
- [External evidence and ideas](external-evidence-and-ideas.md); [determinism and RNG](../../behavior/determinism-and-rng.md).

## Open questions
- Today's death share under the calibrated CTM and M0 leaf (the experiment measures it).
- How often common-seed siblings desynchronise, by screen (the experiment's arm C answers it indirectly).
