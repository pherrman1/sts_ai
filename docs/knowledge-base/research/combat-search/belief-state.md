# Searcher3 belief state

Last verified: 2026-08-11.

## Purpose / research question

How should Searcher3 maintain its belief about hidden game state (draw order,
RNG seeds) across real combat decisions? Can belief filtering improve the
carried state vs. naive carry-over?

## Current conclusion

**Belief filtering semantics are promising but not promoted to default.**
The existing carry-over mechanism produces ~90% stale particles under the
current consistency predicate. A new exact-transition posterior filter
sharply reduces staleness (compatible fraction 72%, was 10%) and is
computationally affordable (~0.2 ms/boundary). However, posterior collapse
(~14-15%) is non-trivial, and fresh reconstruction on collapse did not change
gameplay decisions in the diagnostic run.

The current default remains: fair S3 carries obs-stable trees between decisions
but does NOT apply real-boundary belief updates. `STS_S3_BELIEF=0` is the
recommended particle config.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-05 | [§114 Phase 2 observation identity](../../../../docs/experiments/ledger-04.md) | Observation expansion neutral; obs-keyed descent falsified |
| 2026-08-07 | [§124 feature-ablation re-derivation](../../../../docs/experiments/ledger-05.md) | Belief ON costs −11.3pp; confirmed as current config (S3−belief) |
| 2026-08-10 | [S3 belief-vs-root audit](../../../../docs/experiments/ledger-01.md) (search for "§2026-08-10 Searcher3") | ~90% stale carried particles; root allocation only 3.1% disagreement → recommends belief-filter experiment next |
| 2026-08-10 | [Real-observation belief filtering](../../../../docs/experiments/ledger-01.md) (search for "real-observation belief filtering") | Compatible fraction 72%, collapse 14%, 1/32 win flips — diagnostic, not promoted |
| 2026-08-10 | [Posterior-collapse diagnosis](../../../../docs/experiments/ledger-01.md) (search for "posterior-collapse") | Collapse largely from finite-particle deprivation; fresh reconstruction safe in 32-seed diagnostic |
| 2026-08-10 | [Decision: belief-filter audit](../../decision-log/2026-08-10-s3-real-belief-filter-audit.md) | Old drawOrderConsistent is not a posterior test; exact per-particle propagation is the oracle |
| 2026-08-10 | [Decision: filter implementation](../../decision-log/2026-08-10-s3-real-belief-filter.md) | Keep opt-in, recommend confirmation gate before rejuvenation |
| 2026-08-10 | [Decision: collapse diagnosis](../../decision-log/2026-08-10-s3-collapse-diagnosis.md) | Collapse classifications + fresh-belief fallback diagnostic |

## Rejected / falsified approaches

- **Hypothetical MCTS belief updates** — default-off since issue #58
- **Internal belief reweighting during search** — not in the recommended regime
- **Obs-keyed descent** — falsified at §114

## Relationships

- [particle-budget.md](particle-budget.md) — particle count directly affects collapse rate
- [searcher3.md](searcher3.md) — belief ON/OFF is the S3−belief vs S3−belief−chain config distinction
- [leaf-evaluation.md](leaf-evaluation.md) — leaf evaluators see the determinized world from belief sampling

## Current implementation

The filter lives behind `STS_S3_REAL_BELIEF_FILTER=1` (opt-in, default off).
Collapse-fresh fallback behind `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`.
See `src/sim/search/BattleScumSearcher3.cpp::filterRealTransition`.

`STS_S3_INTERNAL_BELIEF_UPDATE=0` (default off) guards hypothetical updates
during MCTS descent.

See [`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md)
for the full implementation context.

## Open questions

- Does posterior collapse harm useful diversity? (confirmation gate needed)
- If so, can structured rejuvenation (resampling only unconstrained hidden degrees of freedom) help?
- Can the filtering semantics be promoted to a gameplay default?
