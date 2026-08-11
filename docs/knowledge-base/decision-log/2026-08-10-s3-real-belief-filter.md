# Searcher3 real-observation belief filtering

Date: 2026-08-10

## Decision

Keep `STS_S3_REAL_BELIEF_FILTER` opt-in and recommend a confirmation gate before
considering structured rejuvenation. Do not change gameplay defaults.

## Evidence

The pre-implementation audit found that `Belief::update` in
`CombatObservation.cpp` only checks an old draw-order prefix and cannot model
real card movement, generated cards, reshuffles, automatic action queues, or
RNG advancement. The new boundary filter in
`BattleScumSearcher3::filterRealTransition` propagates each particle from the
real pre-action state through `Action::execute`, compares visible
`CombatObservation`, retains equal-weight compatible particles, and restores a
uniform prior on collapse. Hypothetical MCTS updates remain default-off.

On paired fair Searcher3 A0 seeds 93000–93031, 64 particles and 1,000 sims,
filtering produced 11,521 boundary rows: compatible fraction mean/median
0.720/1.000, collapse 13.97%, propagation failures 3.65%, fallback shuffles
0%, surviving draw-order diversity mean/median 42.96/64, RNG-signature diversity
55.03/64, and 0.185 ms mean boundary CPU. Control/filter were 10/32 vs 11/32
wins, identical mean floor (38.719), and +3.31 mean ending HP for filter, with
one paired win flip. These are diagnostic-sized results, not a promotion gate.

## Status and follow-up

**Inference:** Exact real-boundary filtering is semantically and computationally
promising, but posterior collapse is frequent enough to warrant a confirmation
run and diversity inspection. Do not add generic cloning. If collapse is
confirmed as harmful, investigate structured rejuvenation that preserves all
observed consequences and resamples only unconstrained hidden degrees of
freedom.

Artifacts: `build/belief_filter_control_32.csv`,
`build/belief_filter_filter_32.csv`, `build/belief_filter_diag_32.csv`, and
`tools/analyze_s3_belief_filter.py`.

ELI5: We used to ask whether an old shuffled deck still looked like the new deck
by comparing positions, even after cards had been played and moved. Now we let
each possible deck experience the exact move that really happened and keep only
possibilities that lead to the same things the player could see. Most survive,
but some decisions eliminate every candidate, so the next experiment should
check whether that loss of variety is real before adding a careful resampler.