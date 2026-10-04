# Gate 2 follow-up canary plan

## Purpose

Exercise the active-Lizard correction in whole-run integration after the
original Gate 2 cohort was invalid because the forced Tail was inserted spent.
This is an eight-pair mechanism/support canary, not a win-rate qualification.
The original `991000..991007` cohort and its raw evidence remain immutable and
are not reused.

## Frozen cohort and arms

- Ascension 0, Act 3 horizon, `STS_FORCE_RELIC=LIZARD_TAIL` in both arms.
- Exactly eight new paired seeds: `991008..991015`; no replacements or
  extensions.
- Each run uses 10,000 project-fair native Silver real-combat simulations and
  2,048 OOC MCTS simulations, with the same frozen PR #351 confirmation
  settings as the original canary.
- Control: the tracked DeepSets integration candidate and standard Attention
  Brew fallback with `STS_OOC_MCTS_ACTIVE_LIZARD=0`.
- Treatment: byte-identical models, fallback, and settings with
  `STS_OOC_MCTS_ACTIVE_LIZARD=1`.
- Run control then treatment for each seed, in ascending seed order.
- Every gameplay invocation runs through `bash tools/seed_guard.sh` and writes
  unique result, sidecar, MCTS trace, and process-log paths.

## Frozen artifacts and setup

- Integration candidate:
  `docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/integration_candidate.native`,
  SHA-256 `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`.
- DeepSets tensor payload SHA-256:
  `429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`.
- Standard Attention Brew fallback SHA-256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Strategic token model SHA-256:
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
- The manifest also pins the clean source commit, executable SHA-256,
  `tools/seed_guard.sh` hash, `/usr/bin/env` hash, exact argv, full clean
  environment, model paths/hashes, and fresh per-run output paths.
- Use `env -i` with the same explicit environment values as the original
  `gate2_canary_plan.md`, updated only for the tracked candidate path,
  `STS_EXECUTABLE_GIT_SHA`, the new seeds/output paths, and the two arm values.
  Keep `STS_SILVER_TELEMETRY=0`; leave the removed
  `STS_SILVER_REUSE_CAP` override unset.
- Run all 16 `seed_guard.sh guard-only` checks and verify every frozen input
  hash before starting the first gameplay seed. These checks do not start a
  gameplay process.

## Decision rules

All 16 gameplay processes must exit 0 and produce one complete result row and
sidecar for the requested seed. Logs must show the expected active-Lizard arm,
candidate/fallback hashes, fair Silver budget, OOC budget, and runtime source
SHA. Aggregate treatment counters must report nonzero Lizard preparations and
nonzero Lizard samples. There must be zero unexpected
`unsupportedCombats`, `mctsSupportAborts`, hybrid fast/fallback support
failures, and Lizard support failures. Every eligible selected active-Tail
state must be supported; impossible Tail state, invalid HP, NaN, RNG/state
contract failure, or a new non-Lizard support regression rejects the canary.
The predeclared Lizard+Brew, Fairy, and Mark-of-the-Bloom boundaries remain
visible as separate expected exclusions.

Report outcomes, floors, HP, runtime, and counters descriptively. Win-count
differences do not qualify treatment quality and do not authorize an extension.
Any incomplete run or failed engagement check ends this cohort; no replacement
seed is permitted. Gate 3 may proceed only if all correctness, completion, and
active-Tail exercise conditions pass.
