# Silver cap correction: 32k default, 128k experimental

PR #185 retains dynamic dedup and cap-triggered collection. Production/default
cap is restored to 32,768. `STS_SILVER_REUSE_CAP=131072` is explicit experimental
opt-in; only 32768/131072 are accepted. No search policy is changed below the cap.
Effective runtime cap propagates into search configuration and diagnostics.
Frozen wholecombatgen/combatevalgen teachers and live OOC MCTS reject 128k.
OOC startup reads the cap before installing the backend; the real-run guard also
checks effective cap 32768 together with its existing exact-10k contract.

Original PR baseline: `876e9305a258df3d5a5eafd50e30375b933f8884`.
Correction baseline: `7c66c97234ef4cda24eb9221a2a2202978210c5e`.
Executable implementation: `1335f08e1ad85dc8824409064ba00d4524fc7a97`. Binaries were built from this source
before the commit and embed the preceding commit SHA; binary hashes and source
hashes are recorded in provenance. Subsequent test-registration/evidence edits
do not change executable source.

## Checks and resource observation

Full debug preset build passed. Final CTest: 94/94 passed, 34.95 seconds (`ctest-debug.log`).
Agent-tool unittest discovery: 145/145 passed, 35.797 seconds.
Seed-free startup script: 13 cases passed, including experimental cap,
zero cap and malformed cap rejection. Registered teacher compatibility tests
verify default 32k acceptance and 128k rejection by both producers before output.
Experimental-cap live integration completed; all 12 decision CSV rows report
configured_cap=131072. Existing resize and pointer/retained-statistics tests pass.

Default32 real 10k stress canary: three exact reroots plus another 10k search;
35,968 precollection nodes → 80 retained; 35,888 nodes reclaimed;
48,158 cumulative nodes; final search has 12,270 live nodes. Maximum candidate
reachable graph is 80. No ALLOCATED_CAP fallback from historical dead state.
Dedup capacity 65,536, zero resizes in this shorter default-cap fixture;
peak sampled load 45.5231%, final 10,062 entries. Focused growth tests still
force production-table growth to 131,072 and 262,144.
External `/usr/bin/time -v`: 207,108 KiB maximum RSS (202.25 MiB), no swaps.
Debug isolated fixture includes validation snapshots; this is not a universal
RAM bound or a matched resource comparison to the earlier release 128k canary.
The earlier [128k stress packet](../silver_dedup_128k_2026-09-15/README.md)
remains historical engineering evidence, not evidence supporting promotion.

Recorded flat1k parity packet was reverified without running seeds: 16 rows,
7,008 diagnostic records and 380 telemetry records identical at its recorded
implementation SHA. This is not a new gameplay run at the correction SHA.
No new paired quality benchmark was run. Separate handoff: compare ordinary
exact10k + 32k lazy GC against exact10k + experimental128k lazy GC with matched
seeds/settings, cap/provenance diagnostics, memory and decision-quality evidence;
do not promote 128k or relabel/requalify frozen models without that evidence.

Knowledge impact: maintained production/experimental cap and frozen-teacher
startup contracts. Prior ledger §256 promotion is superseded by §257.
