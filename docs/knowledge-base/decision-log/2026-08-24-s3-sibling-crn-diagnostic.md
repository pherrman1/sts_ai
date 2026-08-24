# 2026-08-24 — Searcher3 sibling matched-particle CRN diagnostic

Date: 2026-08-24
Session/task: Implement the accepted offline diagnostic comparing independent
and sibling-matched Searcher3 hidden-particle sampling.

## Decision

Add a diagnostic-only `s3siblingcrn` mode over existing `frontiergen` parent
snapshots. One attempted evaluation installs one belief particle, validates
and executes a fixed root action, then uses current Searcher3 rollout and leaf
evaluation. The matched arm reuses the exact particle across siblings; the
independent arm derives a distinct particle seed per action. Rollout-policy
seeds are action-specific and identical across arms. A separate 128-sample
independent stream supplies reference estimates. Raw sample rows are analyzed
by `tools/analyze_s3_sibling_crn.py`.

The historical `STS_S3_CRN` warm start remains default-off and unchanged. The
new mode never searches a tree, changes PUCT statistics, or affects gameplay.

## Rationale

This isolates covariance from the fixed-action estimator marginal. Exact
particle reuse is stronger and clearer than the historical partial-CRN
reseed-prefix diagnostics. Logging simulator RNG counters before the action,
after the root action, and after rollout makes natural downstream divergence
inspectable. Invalid actions are reported and incomplete batches are excluded;
no substitute action is chosen.

## Evidence before review

- Focused Release build of `one_combat` and `unit-test`: passed.
- `test s3_sibling_crn`, `cardselect_parity`, and
  `battlecontext_roundtrip`: passed.
- Analyzer self-test: passed after correcting its one-element quantile case.
- Two-state `K={2,4}`, `R=4` smoke: 1,056 attempts per run, zero invalid;
  two raw files compared byte-for-byte equal. This smoke is implementation
  evidence only and has no scientific interpretation.

## Status

Implementation awaiting independent review. The preregistered 32-state formal
experiment has not been run.
