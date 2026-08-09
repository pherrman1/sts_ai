# 2026-08-09 — Strategic seed split, contract checks, and gate tracing

Date: 2026-08-09
Session/task: Implement the first correctness and observability items from the
honest-V4 investigation handoff.

## Decision

Use a deterministic whole-seed 80/20 split in both strategic trainers. Keep
`(seed, decIdx)` as the decision-group batching unit, but do not allow a seed
to occur in both train and validation. Share the split implementation in
`strategic_split.py` and include its version in the state-cache fingerprint.

Make the honest V4 Python global construction named-column based through
`strategic_tok_contract.py`. Keep the native parity hook as a failing check:
when `STS_OOC_STRATEGIC_TOK_CHECK=1`, the first gated decision compares all
raw globals and canonical deck/relic/potion tokens against `richRow()` and
aborts on mismatch.

Add `STS_OOC_STRATEGIC_TRACE=<csv>` as an opt-in deployment trace at the
shared `regretGateTail`, including candidate action bits, Q values,
margin/threshold, fallback match, selected action, gate rule, explicit key/
stop objective flags, and final run outcome.

## Rationale

**Inference:** decision-level validation was leakage-prone because one run
contains correlated decisions. A seed-level holdout is the smallest change
that establishes run-disjoint validation while preserving existing group
batching and loss calculations.

**Inference:** the previous diagnostic parity hook could report global
mismatches but could not fail a run or check token arrays. A failing check is
appropriate for an explicitly enabled correctness mode; it does not affect
unset benchmark behavior.

## Alternatives considered

- Keep decision-group splitting: rejected because it permits train/validation
  decisions from the same run.
- Rewrite the trainer around a new dataset schema: rejected; the existing
  `richHeader()` contract is sufficient and the change should not mix schema
  redesign with split validation.
- Trace only stderr: rejected; a CSV with the final run outcome supports
  per-screen override analysis and paired benchmark replay.

## Evidence

- `train_strategic.py` and `train_strategic_tok.py` now call
  `strategic_split.py::seed_disjoint_split` and print seed sets plus their
  intersection.
- `strategic_tok_contract.py` and
  `tools/ooc_strategic_contract_selftest.py` cover the 42-global named-column
  layout and derived thresholds.
- `apps/one_combat.cpp::tokCheckGlobParity` compares native `buildTokState`
  against `richRow()`; `regretGateTail` writes the optional trace.
- `STS_FAIR=1 STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_TOK_CHECK=1 ./build/one_combat bestbench 20 1 0 0`
  completed successfully. A 2-seed 50-sim run produced a trace with 52 gate
  records and final outcomes.
- `cmake --build build --target one_combat -j2` passed.

## Status

Implemented. The feature self-tests pass. A full retrain and the 64-seed
current-stack ON/OFF gate remain separate experiments and must specify
`STS_COLLECT_KEYS` explicitly.
