# 2026-08-23 — Searcher3 Always-Q Experiment 1b implementation

## Decision

Implement the targeted late/no-win hard-state diagnostic as an opt-in
instrumentation path on the reviewed stacked base
`65c756340e67ba1a597ddc2d442ab889702a252f8`. Do not run the scientific
collection or apply its decision rule until independent implementation review
freezes a reviewed SHA.

## Implementation contract

`BattleScumSearcher3::firstQExploitSimulation` is per instance, starts at `-1`,
and records the first one-based simulation ordinal in that search call whose
backpropagation changes the existing `bestActionSequence` from empty to
non-empty. This is the actual
baseline Q-gate activation condition; it does not require a terminal win. It
does not alter selection, rollout, or RNG. `alwaysQOverride` is an unset
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
The expensive paired-reference diagnostic is not part of this correction and
must remain disabled. First measure this gate-timing telemetry on the current
qualified fair Searcher3 stack; only a materially late population justifies
revisiting the paired hard-state experiment.

Scientific outcomes belong in the experiment ledger only after the corrected
implementation SHA is frozen.

## Verification status

The WSL GCC 13.3 build of `unit-test` and `one_combat` passed, and
`unit-test issue_fixes` passed. Both analyzer syntax checks and synthetic
self-tests passed. The corrected two-seed timing smoke captured 803 real
Searcher3 combat-search rows, with 799/803 (99.50%) opening by simulation 10;
the paired hard-state/common-reference diagnostic was explicitly off. The
smoke is implementation evidence only; it is not a gameplay or Always-Q
effect result.

The Windows environment lacks `python3` and CMake on PATH, so equivalent
`python` checks and WSL CMake/GCC were used. WSL's linked-worktree Git path
cannot answer the executable's optional provenance `git rev-parse` call; that
printed a fatal diagnostic during the earlier hard-state smoke while the run
and CSV completed. The corrected timing run does not invoke the hard-state
probe or claim a hard-state provenance field; its exact command, stack, seed
range, and raw CSV are recorded in the correction result below.

## Correction result

The required cheap diagnostic was run before any paired hard-state/reference
probe. On the corrected implementation, the 8-seed guarded collection covered
3,449 real Searcher3 combat searches (seeds 92000–92007, Act-3 stop, ascension
0, 1,000 simulations/decision, 64 particles, fair S3, current V_combat and
policy artifacts, and the documented V4 strategic OOC stack). The baseline Q
gate opened by simulation 10 in 3,446/3,449 searches (99.91%):

| Stratum | n | sim 1 | sims 2–10 | sims 11–100 | sims 101+ | never |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 3,449 | 3,380 (98.00%) | 66 (1.91%) | 1 (0.03%) | 1 (0.03%) | 1 (0.03%) |
| Act 1 | 1,011 | 1,004 (99.31%) | 7 (0.69%) | 0 | 0 | 0 |
| Act 2 | 1,152 | 1,122 (97.40%) | 29 (2.52%) | 1 (0.09%) | 0 | 0 |
| Act 3 | 1,286 | 1,254 (97.51%) | 30 (2.33%) | 0 | 1 (0.08%) | 1 (0.08%) |
| ordinary | 1,539 | 1,532 (99.55%) | 7 (0.45%) | 0 | 0 | 0 |
| elite | 943 | 924 (97.99%) | 17 (1.80%) | 0 | 1 (0.11%) | 1 (0.11%) |
| boss | 967 | 924 (95.55%) | 42 (4.34%) | 1 (0.10%) | 0 | 0 |

The preregistered decision rule therefore applies: **STOP_ALWAYS_Q_LINE**.
The baseline already opens its normal Q gate almost immediately, including in
boss searches. This is timing evidence only; it is not a gameplay win-rate
gate and does not justify running the expensive same-state/common-reference
experiment. The two exceptional late/never rows were both Act-3 elite
searches in seed 92004: one opened at simulation 114 and one did not open in
the recorded 1,000-simulation call.

Raw artifacts are the ignored local files
`build/qgate_timing_8seeds.csv`, `build/qgate_8seed_results.csv`,
`build/qgate_timing_smoke_v2.csv`, and `build/qgate_smoke_results_v2.csv`.
The deterministic analyzer is `tools/analyze_s3_q_gate_timing.py`.
