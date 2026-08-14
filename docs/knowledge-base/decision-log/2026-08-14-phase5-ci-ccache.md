# 2026-08-14 — Phase 5: Measured CI compiler caching with ccache

Date: 2026-08-14
Session/task: Phase 5 experiment — reduce CI compile time via ccache

## Decision

Integrate ccache into the GitHub Actions Linux GCC CI lane as a compiler
launcher, without changing CMake targets, compiler flags, or build parallelism.

## Rationale

The baseline pre-ccache CI (08:46:58Z–08:56:46Z, run 31785326007, SHA 5124f06d)
showed ~9m48s total job time with ~8m47s Build duration and ~4s Test duration.
Multiple targets (`main`, `one_combat`, `unit-test`, `small-test`, `parity_test`)
compile the same `src/*.cpp` collection separately, yielding repeated
compilation of identical translation units. Ccache can cache object files
keyed by input content, compiler identity (`compiler_check=content`), and
compilation flags, thereby eliminating redundant compilations both
within a single build and across runs via cached `.ccache`. The approach is
conservative: it changes **only** CI and **preserves** build semantics, test
coverage, Debug mode, `jobs=1`, and all existing verification.

## Alternatives considered

- Third-party ccache GitHub Action — rejected to minimize external actions and
  keep the mechanism transparent in our workflow.
- Increasing jobs beyond 1 — **excluded per Phase 5 constraints**; parallelism
  change would confound the ccache effect.
- CMake target restructuring / unity builds / PCH — **excluded per Phase 5
  constraints**; changes must isolate compiler caching.

## Evidence

- `.github/workflows/ci.yml` — added `env` with `CCACHE_DIR`, `CCACHE_COMPILERCHECK`,
  `CCACHE_MAXSIZE`, `CMAKE_CXX_COMPILER_LAUNCHER`; added `actions/cache@v4` step;
  added `ccache --version`, `--show-config`, `--zero-stats`, `--show-stats`
  diagnostics around Build.
- `build-and-debugging.md` Section 59-87 — documented ccache CI mechanism.
- Baseline: run 31785326007.

## Status and follow-up

- **Implementing**; changes staged on `infra/ci-ccache-phase5` branch.
- Next: push, create PR, await first CI run (cold/semi-cold), then
  `gh run rerun` same SHA for warm cache comparison.
- Decision rule: keep if CI stays green and Build time materially improves:
  cold/semi-cold ≤ 70% or warm ≤ 40% of baseline ~8m47s (clear success if
  cold ≤ ~6m13s or warm ≤ ~3m30s); abandon if improvement < 20% and do not
  tune risky ccache settings.