# 2026-08-16 — Searcher3 cheap behavior-preserving speedups

Date: 2026-08-16
Session/task: Bounded Searcher3 per-simulation CPU pass on a clean main-derived
branch (`perf/s3-cheap-speedups`), isolated from the particle-conditioned
leaf-value Phase-1 branch.

## Decision

Retain two behavior-preserving micro-optimizations in
`src/sim/search/BattleScumSearcher3.cpp` as one combined change:

1. Gate the per-expansion `BattleContext preExecState` copy in `step()` behind
   the default-off `g_s3EndTurnMarginalize` flag (its only consumer is
   `endTurnMarginalEval`).
2. Replace the two-vector sort-and-compare in `sameCardMultiset` with an exact
   allocation-free fixed-size count array over the dense `CardId` range.

Stop after these two; deeper Searcher3 speed work is not started.

## Rationale

Combined median search cost improved +2.21% (28.271 → 27.647 ms/1000 sims,
9 interleaved rounds × 3 arms, paired per-round median +2.43%) — inside the
retention band for extremely small, obviously maintainable diffs. Each change
alone measured under the 2% noise floor (A ≈ +0.7%, B marginal ≈ +1.6%), so
they are retained only as a pair. Search behavior is byte-identical: fairgen
value/policy/OOC CSVs matched baseline exactly for both interventions, and all
27 timing runs produced identical per-search CPU-diag fingerprints and
identical bestbench outcomes. Neither intervention touches RNG consumption,
edge order, enumeration, or any flagged feature path; the marginalization
feature keeps identical behavior when enabled (the copy is taken under the same
condition the consumer checks).

## Alternatives considered

- Retain intervention A alone — rejected: +0.66% median, below the retention
  threshold.
- Revert both — rejected: the combined diff is ~20 lines in one file with exact
  behavioral equality evidence and a measurable (if modest) CPU saving.
- Further cheap candidates (path/actionStack reserve, observation work) — not
  pursued: profiling shows remaining cost is dominated by vnet inference,
  `BattleContext` copies in rollouts, and action execution, which need
  architectural work (out of scope by handoff).

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp` — `step()`, `sameCardMultiset`.
- `docs/experiments/ledger-06.md` — full measurement protocol and raw
  repetitions (2026-08-16 Searcher3 cheap-speedup entry).
- `one_combat fairgen` byte-equality and `STS_REUSE_CPU_DIAG` fingerprints —
  recorded in the ledger entry.

## Status and follow-up

- Implemented on `perf/s3-cheap-speedups` (from main `a7573e1`); ready for
  review/merge. Particle-conditioned Phase-1 branch untouched.
- Follow-up (separate decision): remaining Searcher3 hotspots (vnet leaf
  inference per rollout endpoint, per-rollout `BattleContext` copies) require
  representation/architecture changes, deliberately not started.
