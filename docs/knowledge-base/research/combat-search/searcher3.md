# Searcher3 ISMCTS

Last verified: 2026-08-11.

## Purpose / research question

Does information-set MCTS with particle determinization (`BattleScumSearcher3`)
improve fair-play combat decisions over the known-RNG Searcher2?

## Current conclusion

**Searcher3 is the standard fair-play combat searcher.** It beats Searcher2
fair-play by ~+39pp in the early gates and has been the foundation for every
subsequent combat experiment.

The recommended operating configuration is **S3−belief−chain** (belief OFF,
chain OFF, i.e. `STS_S3_BELIEF=0 STS_S3_CHAIN=0`) with `STS_S3_PARTICLES=64`
at 1,000–3,000 simulations per decision. This was established by the §115
particle×sims grid and §124 re-measurement on the live-valid binary:

- belief ON costs −11.3 to −12.1pp (significant)
- chain ON costs −4.7pp (from §106 ablation)
- CRN warm-start code was historically uninvoked (dead), so it was absent
  from earlier results. When explicitly activated via `STS_S3_CRN=1` in §106,
  it was significantly harmful (−14.1pp vs control, CI excludes 0), so it
  remains disabled.

The default path since 2026-08-07 includes:

- `STS_LIVE_VALID=1` (fair-tree edge re-selection, +5.5–5.9pp)
- `STS_FORCED_MOVE=1` (decision-neutral, −8.5% cpu)
- Honest-data V_combat leaf default ON at α=0.3 (§126 promoted, §148 tuned)

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-07-25 | [S3 early development](../../../../docs/experiments/ledger-01.md) (search for "BattleScumSearcher3") | ISMCTS with lethal detection initial implementation |
| 2026-07-26 | [Phase 3 compression + tree reuse](../../../../docs/experiments/ledger-01.md) | Sorted compression investigated |
| 2026-08-05 | [§106 S3 feature ablation](../../../../docs/experiments/ledger-04.md) | Belief/chain/CRN net-negative; prune/live inert |
| 2026-08-05 | [§107 particle×sims sweep](../../../../docs/experiments/ledger-04.md) | S3−belief−chain promoted at 60.2% @3k/256p |
| 2026-08-05 | [§113 CARD_SELECT parity fix invalidates §107](../../../../docs/experiments/ledger-04.md) | §107 headline invalidated; honest re-baseline 42.6% @3k |
| 2026-08-06 | [§122-§123 LIVE_VALID gates](../../../../docs/experiments/ledger-05.md) | LIVE_VALID promoted to default ON |
| 2026-08-07 | [§124 re-measurement](../../../../docs/experiments/ledger-05.md) | Confirmed: S3−belief−chain is the particle config |
| 2026-08-10 | [S3 belief-vs-root audit](../../../../docs/experiments/ledger-01.md) | Root allocation only 3.1% disagreement with 4000-sim ref |

## Rejected / falsified approaches

- **S3 deterministic chain compression** — net-negative (§106)
- **S3 particle belief reweighting** — costs −11 to −12pp (§124)
- **CRN warm start** — historically uninvoked (dead) code; when explicitly
  enabled via `STS_S3_CRN=1` it was significantly harmful (−14.1pp vs control
  at §106, CI excludes 0), so it remains disabled
- **Non-fair forced-move contraction** — divergent results (§120/§121), restricted to fair only
- **Obs-keyed descent** — tree grows linearly, floor 11 vs 33 (§114)

## Relationships

- [belief-state.md](belief-state.md) — belief maintenance diagnostics and filtering
- [particle-budget.md](particle-budget.md) — particle-count utilization
- [leaf-evaluation.md](leaf-evaluation.md) — rollout and learned leaf behavior under S3
- [policy-prior.md](../combat-models/policy-prior.md) — GBM prior inside PUCT

## Current implementation

See [`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md) for
the current executable implementation. Key flags: `STS_SEARCHER3=1`, `STS_FAIR=1`,
`STS_S3_BELIEF`, `STS_S3_CHAIN`, `STS_S3_PARTICLES`, `STS_LIVE_VALID`.

## Open questions

- Should 128 particles replace 64 as the gameplay default? (promising but not confirmed, see particle-budget.md)
- Can belief filtering semantics be promoted to default? (confirmation gate pending, see belief-state.md)
- Can the 3k operating point be re-measured with the full current stack? (open follow-up)
