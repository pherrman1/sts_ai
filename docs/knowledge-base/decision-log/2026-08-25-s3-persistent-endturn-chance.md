# 2026-08-25 — Searcher3 persistent END_TURN chance continuations

Date: 2026-08-25
Task: Experiment 4 persistent END_TURN chance/outcome nodes for Searcher3.

## Decision

Implement the treatment behind default-off
`STS_S3_PERSISTENT_ENDTURN_CHANCE`. Keep `Edge::child` as the one aggregate
action-statistics container and store exact full-`CombatObservation` outcome
children alongside it. A normal particle executes END_TURN once, and its actual
post-action observation selects or creates the only continuation visited by
that simulation. The PR #48 strategy-fusion diagnostic remains unchanged for
control use and is mutually exclusive with the treatment. Eager END_TURN
marginalization is also mutually exclusive, and chance eligibility has an
independent `STS_S3_PERSISTENT_ENDTURN_MAX_PILE` bound (default 8).

## Rationale and alternatives

PR #48 found 0.7063 probability-weighted shared/conditioned disagreement and a
positive matched-conditioned reference margin (+2.4507 pooled; source-seed
bootstrap 95% CI [+0.6162,+3.5639]). Persistent conditioning directly tests
whether amortized visible-state splitting recovers that lost policy
conditioning. Eager alternative generation was rejected because the prior
prototype cost about 56% CPU without improving quality. Generic chance nodes,
progressive widening, hidden-state keys, and non-END_TURN changes remain out of
scope.

## Evidence

- `BattleScumSearcher3::dispatchPersistentEndTurnOutcome` uses exact
  `CombatObservation::operator==`; hidden order, RNG, particle index, and seed
  are absent.
- CTest `s3_persistent_endturn_chance` proves split, reuse, hidden-RNG
  non-keying, observation-only dispatch, and aggregate backup.
- Focused nearby regressions pass: `s3_strategy_fusion_diag`,
  `semantic_card_edges`, `s3_drawpile_reuse_boundary`, and
  `rng_state_propagation`.
- Guarded Release smoke, seeds 92000–92007 at fair S3 1,000 simulations/64
  particles: control 7/8, treatment 7/8, two opposite paired flips; summed
  per-run seconds 605.2119 vs 600.7984 (-0.73%). Treatment observed 2,104,508
  eligible visits, 411,206 containers, 780,308 new outcomes, and 1,324,200
  reuse hits (62.92%).

## Status and follow-up

Implementation PASS. The small gameplay smoke is not statistically decisive.
The lack of measurable overhead and nontrivial reuse support independent review
for a separately designed larger gate after the implementation SHA is frozen.

**Open question:** one container reached 685 distinct visible outcomes. This is
not explained solely by legacy visible pre-state mixing in the cheap follow-up.
A guarded one-seed/64-simulation treatment smoke found 241 containers with at
least one pre-observation hash mismatch, but its largest container had 59
outcomes over 205 visits and zero mismatches; containers known to mix visible
pre-state hashes reached at most 15 outcomes. This is evidence against the
simple explanation, not a retrospective classification of the earlier 685
container. Its distribution and memory impact remain open before a larger gate.
