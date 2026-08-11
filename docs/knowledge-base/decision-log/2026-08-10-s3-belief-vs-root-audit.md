# 2026-08-10 — Searcher3 belief maintenance versus root allocation audit

Date: 2026-08-10
Session/task: Diagnostic-first comparison of real-observation belief maintenance
and root-action allocation. No gameplay-default change is authorized by this
task.

## Pre-implementation audit

`BattleScumSearcher3` constructs `Belief::initial` from the current visible
`BattleContext`. `HiddenBattleState` stores a hidden draw-pile order, six pairs
of RNG seeds, a weight, and an id; it does not store RNG counters or an
observation history (`include/sim/search/CombatObservation.h`). Initial
particles randomize all six seed pairs and shuffle the currently visible draw
pile contents (`CombatObservation.cpp::HiddenBattleState::sampleParticles`).

Each `step()` samples one particle, copies the root `BattleContext`, installs
the particle's six RNG seed pairs, and installs its draw order when the pile
size and multiset still match. Otherwise `applyParticle` shuffles the copied
draw pile with the searcher's RNG (`BattleScumSearcher3.cpp::applyParticle`).

Hypothetical observations inside MCTS are not real evidence. The five
`belief.update` call sites in `BattleScumSearcher3::step` are guarded by
`g_s3InternalBeliefUpdate`, whose default is false after issue #58. This keeps
the root belief unchanged during simulated descent; enabling the historical
flag is explicitly outside the recommended regime.

At a real action boundary, the current behavior differs by agent path:

- Non-fair S3 executes the real action, promotes the tree with `advanceRoot`,
  then calls `Belief::update` on the resulting real observation.
- Fair S3 normally uses `playoutBattleFair`; it may carry an obs-stable child
  through `advanceRoot` and re-key the searcher, but it does not update or
  rebuild the carried belief at the real boundary. If the reuse gate rejects
  the child or the reuse limit is reached, the next decision constructs a new
  belief from the new live state.

`Belief::update` only zero-weights particles whose stored draw order fails the
current positional consistency check. There is no normalization, resampling,
or rejuvenation. If all weights reach zero, `Belief::sample` falls back to a
uniform particle; equal positive weights also use uniform sampling. Thus a
stale carried particle can trigger an approximate draw-pile shuffle in
`applyParticle`, and fair obs-stable reuse can carry stale belief state even
when the promoted tree observation is stable.

This audit motivates two opt-in measurements: real-boundary compatibility and
diversity/fallback statistics for the carried belief, plus fresh 250/500/1000/
4000-simulation root comparisons whose regret is measured from the 4000-search
Q values. The diagnostics must not call `Belief::update` during hypothetical
search and must not alter the selected gameplay action.

Status: pre-implementation audit complete; diagnostic implementation follows.

## Diagnostic implementation

The existing STS_S3_BELIEF_AUDIT hook now writes real-decision boundary rows to
STS_S3_BELIEF_AUDIT_FILE. It records compatibility against the current exact
draw-order predicate, compatible draw-order/RNG-signature diversity, uniform
ESS, stale fraction, fallback-shuffle fraction, and whether the fair searcher
was carried or rebuilt. The new STS_S3_ROOT_RACE_DIAG hook writes one row per
root action to STS_S3_ROOT_RACE_DIAG_FILE, using fresh isolated probes at
250/500/1000/4000 simulations and computing regret from the 4000-simulation
Q values. Both hooks are off by default and do not call hypothetical
Belief::update.

## Diagnostic experiment

Configuration: fair Searcher3, A0, 64 particles, 1,000 simulations per live
decision, current native floor/win models, build/v_combat_7k_tuned.txt at
alpha 0.3, build/policy_trees_c.txt, no PVNet/dist VNet, 24 OpenMP threads,
seeds 93000–93031 on GCP sts-test. STS_S3_INTERNAL_BELIEF_UPDATE remained
at its default off state. One real decision state per seed received the
250/500/1000/4000 root probes; the 4000 budget was capped to this sample
because it was materially more expensive than the ordinary search.

Results:

| Area | Result |
|---|---:|
| belief rows / seeds | 9,462 / 32 |
| mean compatible fraction | 0.1004 |
| mean stale fraction | 0.8996 |
| mean fallback-shuffle fraction | 0.2090 |
| mean distinct compatible draw orders | 0.3244 |
| mean distinct compatible RNG signatures | 6.43 |
| mean ESS | 64.0 |
| carried / rebuilt boundaries | 7,802 / 1,660 |
| root states | 32 |
| P(a250 != a4000) | 1/32 = 3.1% |
| P(a500 != a4000) | 1/32 = 3.1% |
| P(a1000 != a4000) | 1/32 = 3.1% |
| shallow/deep disagreement events | 3 |
| disagreement deep regret | 1.417 native units, all in 0.5–2 |
| disagreement clusters | none in END_TURN, large action sets, or particle availability mismatch |

The compatibility and stale metrics use the current exact positional
drawOrderConsistent predicate, so they are evidence of maintenance pressure,
not proof that this predicate is the correct posterior likelihood. ESS is
reported as 64 because fair S3 does not apply real-boundary reweighting and
the particles remain uniformly weighted.

## Decision

**RECOMMEND_NEXT: BELIEF_FILTERING**

The real-observation audit shows substantial incompatibility and diversity
collapse under carried fair beliefs: roughly 90% of particles are stale by the
current consistency rule, only 10% remain compatible on average, and fallback
shuffle would be required for roughly one in five particles. In contrast,
root allocation disagreed with the 4000-simulation reference only 3.1% of the
time at each tested shallow budget; all three disagreement events were modest
(0.5–2 native units) and did not cluster around large or particle-mismatch
roots. Root racing is therefore not the next major line.

The next experiment should implement only a flagged real-boundary belief
maintenance prototype: exact compatibility/likelihood handling first, then
normalization and measured resampling/rejuvenation of still-unobserved hidden
degrees of freedom. It must preserve the default-off hypothetical-update
guard and use paired seeds. Do not promote it from this diagnostic.

## ELI5

Searcher3 has two possible weak spots: it may be carrying outdated guesses
about the hidden deck, or it may be spending its search budget on the wrong
root move. We checked both. After real moves, most carried deck guesses no
longer match the observed situation, while shallow searches almost always
agree with the much deeper reference search. So the next useful experiment is
to repair the real-observation belief update, not to replace root allocation.