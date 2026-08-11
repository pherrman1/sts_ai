# Searcher3 posterior-collapse diagnosis and fresh-belief fallback

Date: 2026-08-10

## Audit finding

The filter's zero-survivor path is not dominated by propagation inability. In
`BattleScumSearcher3::filterRealTransition`, each old particle is copied from
the real pre-action state, installed, and run through the exact `Action::execute`
transition. The extended audit counts predicted visible observations by hash,
records the real hash, action type, reshuffle signal, and concentration.
Propagation failures are counted separately from particles that propagate but do
not predict the real observation.

The collapse category is a diagnostic classification, not a proof of a specific
hidden mechanic: END_TURN rows are labelled stochastic end-turn/particle
deprivation, CARD rows card-effect/automatic-queue/particle-deprivation, and
reshuffle-like rows are marked separately. `HiddenBattleState` still stores RNG
seeds but not counters, so exact post-transition RNG identity remains an open
representation limitation.

## Results

Fresh paired block: seeds 93100–93131, fair Searcher3, A0, 64 particles, 1,000
simulations, deployed native models, alpha 0.3, 24 threads. B used filtering;
C added `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`. The control A used filtering off.

The corrected B diagnostic contained 12,432 real-boundary rows. Mean compatible
fraction was 0.697 (median 1.0), propagation-failure rate was 1.24%, fallback
shuffles were 0%, and collapse rate was 1,894/12,432 = 15.23%. No collapse row
had propagation failures or action-illegal particles. Of collapse rows, 1,325
were END_TURN, 357 CARD, 41 single-card-select, 37 multi-card-select, and 85
POTION; 50 had the conservative reshuffle/draw signal.

Among collapse rows, exact propagation produced a mean 57.23 distinct predicted
observations (median 63), mean entropy 3.978, and mean dominant share only 3.9%.
The capped fresh-prior sensitivity probes found mean compatible counts of 0.64,
1.69, 2.77, and 6.34 at 64/128/256/512 particles respectively; positive-survivor
probes were 32/64, 44/64, 47/64, and 53/64. This supports finite-particle
deprivation as a substantial explanation, while the nonzero misses at 512 keep
model/representation limitations open.

A/B/C gameplay results were respectively 10/32, 11/32, and 11/32 wins; mean
floors 40.938, 40.969, 40.969; mean ending HP 14.688, 15.531, 15.531; CPU
27.031, 27.000, 27.188 seconds/run. A/B and A/C had one paired win flip; B/C
had zero. Fresh reconstruction occurred on every collapse in C (15.23% of
boundaries) and changed no paired gameplay decisions relative to B in this
block. Decision-level action-change logging was not available in the existing
bestbench schema, so no stronger action-count claim is made.

## ELI5

When every one of 64 guesses disagrees with what really happened, we checked
whether the guesses were impossible to simulate or simply missed a rare outcome.
They were usually simulated correctly, but they spread across many possible
outcomes, so 64 guesses often missed the real one. Trying 128–512 guesses made
the real outcome show up more often. When that happened, throwing away the old
guesses and making fresh guesses from the visible state was safe in this small
run, but it did not change the game decisions.

Status: diagnostic result; fresh fallback remains opt-in and unpromoted.