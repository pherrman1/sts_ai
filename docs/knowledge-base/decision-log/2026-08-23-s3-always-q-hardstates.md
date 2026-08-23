# 2026-08-23 — Searcher3 Always-Q Experiment 1b implementation

## Decision

Implement the targeted late/no-win hard-state diagnostic as an opt-in
instrumentation path on the reviewed stacked base
`65c756340e67ba1a597ddc2d442ab889702a252f8`. Do not run the scientific
collection or apply its decision rule until independent implementation review
freezes a reviewed SHA.

## Implementation contract

`BattleScumSearcher3::firstWinningSimulation` is per instance, starts at `-1`,
and records the first cumulative simulation whose backpropagated value causes
the existing `bestActionSequence` winning-line criterion to become non-empty.
It does not alter selection, rollout, or RNG. `alwaysQOverride` is an unset
`std::optional<bool>` by default; unset uses `g_s3AlwaysQ`, while `false` and
`true` force the legacy and immediate-Q predicates respectively. Both ordinary
and `LIVE_VALID` selection call the same instance predicate.

The hard-state hook is enabled with `STS_S3_HARDSTATE_DIAG=1` and writes one
row per source legal root action. It receives the live candidate root directly,
constructs control and treatment probes from that same in-memory
`BattleContext`, uses the same paired seed salt for their belief/RNG streams,
and uses a separate salt for the independent 8000-simulation baseline
reference. The reference is a comparison baseline, not ground truth.

The companion analyzer is
`tools/analyze_s3_always_q_hardstates.py`; it validates repeated exact-state
identity fields, derives E0/E1/E2/H1/H2 from control timing, computes per-budget
regret and paired Δregret, and uses deterministic seed bootstrap intervals.
Scientific outcomes belong in the experiment ledger only after the reviewed
implementation SHA is frozen.

## Verification status

The WSL GCC 13.3 build of `unit-test` and `one_combat` passed, and
`unit-test issue_fixes` passed. The analyzer syntax check and synthetic
self-test passed. A two-seed implementation smoke captured two exact-state
groups (one per seed), including one H2 no-win-by-3000 group, with equal source,
control, treatment, and reference visible-state hashes and a shared reference
action/Q table. The smoke is implementation evidence only; it is not a
scientific result.

The Windows environment lacks `python3` and CMake on PATH, so equivalent
`python` checks and WSL CMake/GCC were used. WSL's linked-worktree Git path
cannot answer the executable's optional provenance `git rev-parse` call; that
printed a fatal diagnostic during smoke while the run and CSV completed. The
scientific collection must use a normal repository path or otherwise verify
provenance before accepting rows.
