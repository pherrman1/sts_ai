# Searcher3 belief state

Last verified: 2026-08-15.

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

**Persistent posterior transfer across fresh trees is rejected for the current
particle representation.** A 2026-08-15 diagnostic found that 99.4% of
non-trivial exact filters were followed by a fresh initial belief, so the
lifetime coupling is material. But an 8-seed fresh-tree treatment that
transferred the posterior caused 79.1% collapse, mostly propagation failures:
`HiddenBattleState` stores RNG seeds but not counters, while particle application
resets counters to zero. It cannot represent a posterior safely across multiple
real transitions. No transfer feature remains in the executable.

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
| 2026-08-15 | [Persistent-posterior lifecycle decision](../../decision-log/2026-08-15-s3-persistent-posterior-lifecycle.md) | Useful posteriors are usually discarded, but transfer is invalid with seed-only hidden RNG state; diagnostic retained, treatment removed |

## Rejected / falsified approaches

- **Hypothetical MCTS belief updates** — default-off since issue #58
- **Internal belief reweighting during search** — not in the recommended regime
- **Obs-keyed descent** — falsified at §114
- **Persistent posterior transfer with seed-only hidden state** — rejected:
  propagated particles lack RNG counters and collapse on later real boundaries

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

When `STS_S3_BELIEF_AUDIT=1` and `STS_S3_BELIEF_AUDIT_FILE` are set, the fair
S3 loop also writes `<audit-file>.next_search.csv`. It records the actual belief
source for each filtered boundary's next search (`fresh_initial`,
`existing_filtered_posterior`, `collapse_fresh`, or `no_next_search`), including
reconstruction caused by `STS_REUSE_MAX_SEARCHES`. Analyze it with
`tools/analyze_s3_belief_filter.py --next-search` rather than using
`belief_carried` as a proxy.

See [`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md)
for the full implementation context.

## Open questions

- Can a future hidden-state representation carry exact RNG-counter state across
  real boundaries without violating simulator invariants? **Open question**;
  no such mechanism is implemented.
- Can the filtering semantics be promoted to a gameplay default?
