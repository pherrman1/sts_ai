# Current research status

Last verified: 2026-08-14 against the current working tree.

## Purpose

This page is the single routing source for active, parked, and closed research
lines. It does not replace the current benchmark configuration in
[current-baselines.md](current-baselines.md), chronological evidence in
`EXPERIMENTS.md`, or implementation contracts in the architecture pages.

## Active line

### Encounter-marginalized strategic labels

The 2,000-source-seed matched M0 (fixed-world) vs M1 (encounter-marginalized)
experiment completed (2026-08-15). On the preregistered 64-seed paired gameplay
gate (seeds 900000–900063, frozen S3 + 7k-VNet Act-3 stack, all strategic
screens ON, margin 1.0), M1 did not separate from M0:

- M0 17/64 = 26.6%; M1 16/64 = 25.0%; paired Δ (M1−M0) = **−1.6pp**, 95% CI [−14.1, +10.9]pp.
- Offline best-CE: M0 `val_pol_ce` 0.50897 vs M1 0.51181 (both trained 40 epochs).

Per the preregistered decision rule this is a **null / approximately-equal**
result: encounter marginalization does not separate from the fixed-world control
at 2,000 source seeds. It does not support promotion or immediate scaling to
5,000 seeds. Both arms remain far below deployed V4, so a separate bottleneck
(H4) remains plausible; do not infer that fixed-world leakage is beneficial.
See [ledger-06 §168](../../../docs/experiments/ledger-06.md) and the
[Phase 12 decision log](../decision-log/2026-08-14-phase12-encounter-marginalization-next-step.md).

Evidence:

- [Encounter-marginalization final report](../encounter-marg-final-summary-2026-08-10.md) (500-seed pilot, +3.1pp M1)
- `docs/experiments/ledger-06.md` §168 (2,000-seed null result)
- `apps/one_combat.cpp::strategicMargGen`
- `tools/convert_marg_to_trainer.py`, `tools/reconstruct_marg_csv.py`

## Current baseline

Use [current-baselines.md](current-baselines.md) for the recommended executable
configuration and qualified benchmark numbers. Do not infer the current
baseline from a dated plan, session report, model filename, or ignored build
artifact.

## Parked lines

- Infinite-combo-aware search steering: investigation completed, but no active
  implementation or gate is scheduled.
- Self-play strategic relabeling: the 2026-08-07 handoff predates later
  controller, model, and encounter-marginalization work. It requires a new
  pre-registered contract before execution.
- Rollout leaf variants: prior K-rollout, one-turn bootstrap, policy-filtered,
  and related variants were null or negative. Reopen only with a new premise.
- Policy-head search distillation: the old Phase F handoff is not current
  execution guidance and must be revalidated against current labels and code.
- Searcher3 real-observation belief filtering
  ([decision log](../decision-log/2026-08-10-s3-real-belief-filter.md),
  [ledger-01.md](../../../docs/experiments/ledger-01.md)): the
  exact-transition posterior filter (`STS_S3_REAL_BELIEF_FILTER`) is
  implemented opt-in. The 32-seed diagnostic shows compatible fraction 72%
  (was ~10%), affordable CPU, and semantic correctness, but collapse is
  ~14%. A confirmation gate is the next justified step; rejuvenation is
  parked behind it. No gameplay default changed.
  A 2026-08-15 lifecycle diagnostic found that useful filters are usually
  discarded before the next search. A paired collapse-fallback correction showed
  the prior 79.1% temporary-transfer collapse was primarily stale pre-transition
  particle restoration: post-state fresh recovery reduced collapse to 19.7%.
  Transfer remains experimental and absent from the executable; only telemetry
  remains pending a separate action/quality experiment.
- Searcher3 particle-count default
  ([decision log](../decision-log/2026-08-10-s3-particle-count-sweep.md),
  [ledger-01.md](../../../docs/experiments/ledger-01.md)): 128 particles
  is directionally promising (monotonic collapse reduction, positive win
  direction) but not confirmed for promotion. 64 particles remains the
  gameplay default; a confirmation gate on a full seed block is the next
  justified step.

## Closed lines

- Raw deep-search utility as the combat leaf target, repeated DAgger, residual
  correction, and the sampled terminal-endHP relabeling did not improve the
  recorded online gate (`EXPERIMENTS.md` §166).
- The initial DeepSets combat VNet failed under MCTS distribution shift
  (`EXPERIMENTS.md` §157-§158).
- Completed and superseded plans, handoffs, and intermediate reports are under
  `docs/archive/research/`. They are historical evidence, never current
  instructions.

## Invariants and assumptions

- Code and executable behavior remain authoritative.
- Policy-quality claims require paired common seeds and an explicitly labelled
  fair or known-RNG regime.
- Agent-run seed counts remain subject to `tools/seed_guard.sh`.
- An artifact path in a historical report does not prove that artifact still
  exists or loaded successfully.

## Relevant code

- `apps/one_combat.cpp::strategicMargGen`
- `apps/one_combat.cpp::stepFrozenV4Ooc`
- `tools/convert_marg_to_trainer.py`
- `train_strategic_tok.py`
- `export_strategic_tok.py`

## Known limitations

- The active M0/M1 direction is supported by a small, underpowered matched
  gate; it is not a promotion claim.
- Historical reports sometimes omit hashes, exact seed ranges, or complete
  environment provenance. Those omissions must not be filled by inference.

## Open questions

- Does scaled encounter-marginalized supervision improve M1 relative to a
  matched M0 control?
- If so, does the matched winner become competitive with deployed V4?
