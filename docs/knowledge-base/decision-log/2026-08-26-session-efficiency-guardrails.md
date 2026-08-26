# 2026-08-26 — reduce repeated agent-session waits and cold builds

## Decision

Use nonblocking CI status queries, opt-in shared local ccache presets, and a
one-seed bestbench treatment/provenance canary before larger experimental
cohorts. Strengthen the Silver GAMBLE fixture to prove an actual intermediate
selection and exact reroot with inherited visits.

## Rationale

Recent sessions contained a 5.4-hour foreground CI watch, a 94-minute combined
parity compile/run, repeated 20–40-minute cold worktree builds, an experimental
arm that bypassed its requested Silver backend, and a GAMBLE parity fixture
that initially passed by confirming an empty subset without exercising the
multi-step mechanism. These changes target those observed failures without a
new orchestration system or shared mutable build directory.

## Evidence

- `CMakePresets.json`: opt-in `*-ccache` configure/build/test presets
- `tools/agent/check_benchmark_canary.py --self-test`
- `apps/silver_bridge_test.cpp`: nonempty GAMBLE selection, exact reroot, and
  inherited-visit assertions
- `operations/agent-context-and-workflow.md`, `build-and-debugging.md`, and
  `evaluation/benchmark-protocol.md`

## Status and follow-up

Implemented. A content-identical forced recompile produced a direct ccache hit;
cross-worktree time savings remain to be measured on ordinary future tasks.
