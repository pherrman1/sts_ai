# 2026-08-28 — Research-run preflight guardrails

Date: 2026-08-28
Session/task: Convert the highest-leverage workflow-retrospective findings into small durable tools.

## Decision

Decision-bearing multi-arm GCP `bestbench` runs use a strict manifest and a
pre-seed exact-SHA check. Artifact transfer can verify SHA-256 at both ends,
and manifest launches refuse existing results, metadata sidecars, or logs.
Local preset builds use one environment-aware wrapper that selects native
CMake or a single Windows-to-WSL command.

## Rationale

These checks move costly, previously post-run discoveries—missing telemetry,
configuration drift, stale outputs, wrong artifacts, and mismatched remote
build trees—to deterministic validation before gameplay. The wrapper removes
repeated Windows/WSL path and invocation setup without changing the CMake graph.

## Alternatives considered

- A general experiment orchestration framework — rejected as broader than the
  observed failures; the existing designated-host launcher remains the owner.
- Post-run canary validation alone — retained but insufficient for errors that
  can be rejected before spending a seed.
- Separate Windows and Linux build scripts — rejected because one small route
  selector expresses the maintained preset contract directly.

## Evidence

- `tools/agent/gcp_benchmark.py` — `load_run_manifest`, `copy_to`,
  `exact_sha_preflight`, and `manifest_run`.
- `tools/agent/build.py` — native/WSL preset selection.
- `tests/agent/test_gcp_benchmark.py` and `tests/agent/test_build.py` — focused
  fail-closed and routing fixtures.

## Status and follow-up

- Implemented. The manifest guard complements, rather than replaces,
  `tools/agent/check_benchmark_canary.py` after the smallest smoke.
