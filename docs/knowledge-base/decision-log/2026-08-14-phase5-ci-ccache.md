# 2026-08-14 — Phase 5: Measured CI compiler caching with ccache

Date: 2026-08-14
Session/task: Phase 5 experiment — reduce CI compile time via ccache

## Decision

Integrate ccache into the GitHub Actions Linux GCC CI lane as a compiler
launcher, without changing CMake targets, compiler flags, or build parallelism.

## Rationale

The hypothesis was that repeated compilation of the same `src/*.cpp`
collection across CMake targets could be reduced without changing build
semantics. Ccache caches object files keyed by input content, compiler identity
(`compiler_check=content`), and compilation flags. The approach changed
**only** CI and preserved build semantics, test coverage, Debug mode, `jobs=1`,
and all existing verification.

### Final measurements

| Configuration | Run / attempt | Commit | Linux GCC job | Build | ccache result | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| Primary baseline | `31791405209` | `8be451c07150625ddb8933d1bd3fc65231a54181` | ~9m52s | 9m09s | N/A | Existing verification passed |
| Cold/semi-cold ccache | `31792228896` / attempt 1 | `e85b99fc3400e1f7893be1846b3c44428b07dbde` | — | ~4m07s | 144 / 226 hits (63.72%); cache began empty; ~39–40 MB saved | 27/27 passed |
| Warm ccache | `31792228896` / attempt 2 | same source commit | ~51s | ~5.7–6s | 225 / 226 hits (99.56%); exact ccache key restored | 27/27 passed |

The cold/semi-cold Build improved by approximately 55% versus the 9m09s
baseline Build. The warm Build improved by approximately 99%, and the total
warm Linux GCC job improved by approximately 91% versus the ~9m52s baseline.
Ccache statistics are zeroed before Configure, so the single warm miss may be
a configure-time compiler probe rather than a build translation unit.

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
- Primary baseline: main SHA `8be451c07150625ddb8933d1bd3fc65231a54181`,
  run `31791405209`.
- Cold/semi-cold result: PR commit
  `e85b99fc3400e1f7893be1846b3c44428b07dbde`, run `31792228896` attempt 1.
- Warm result: the same run and commit, attempt 2, with the exact ccache key
  restored.

## Status and follow-up

- **Phase 5 successful; KEEP ccache.** The hypothesis is strongly supported:
  ccache produced genuine compiler-cache hits, all 27 CTest checks passed in
  both ccache runs, and both cold/semi-cold and warm results materially beat
  the baseline.
- The measured result exceeds the decision thresholds: cold/semi-cold Build
  time is below 70% of baseline, and warm Build time is below 40% of baseline.
- The next independent optimization experiment should examine the duplicated
  CMake build graph and common simulator object compilation. Do not mix that
  build-graph investigation into this ccache PR.