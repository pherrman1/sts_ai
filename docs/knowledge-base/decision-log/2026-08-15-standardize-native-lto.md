# 2026-08-15 — Standardize native LTO

Date: 2026-08-15
Session/task: Benchmark compiler optimization flags and adopt the measured native build improvement

## Decision

Add `-flto` to the global native C++ flags in `CMakeLists.txt`, making link-time
optimization part of the standard Release and native executable builds.

Do not add `-march=native` to the standard flags.

## Rationale

In the matched 8-seed Jaw Worm combat benchmark, `-O3 -march=native -flto`
reduced process user CPU time from 0.88 s to 0.76 s versus the current `-O3`
build, while `-march=native` alone reduced it only from 0.88 s to 0.87 s.
The benchmark is small, so the result is evidence for adopting LTO rather than
a universal performance guarantee. `-march=native` is also host-specific and
would make binaries less portable.

## Alternatives considered

- Keep current `-O3` — rejected because the measured LTO build was faster with
  identical benchmark outcomes.
- Standardize `-march=native` as well — rejected because its isolated benefit was
  negligible and it specializes binaries to the build host.
- Add LTO only to Release presets — rejected because the current project applies
  native optimization flags globally and the native target graph shares the
  resulting object files.

## Evidence

- `CMakeLists.txt` — global `CMAKE_CXX_FLAGS`.
- `apps/one_combat.cpp::benchmark` — Jaw Worm combat benchmark and MCTS timing.
- `tools/seed_guard.sh` — guarded 8-seed execution.
- `docs/experiments/ledger-06.md` — dated raw benchmark configuration and results.

## Status and follow-up

- Implemented and verified with a Release configure/build.
- The benchmark used one CPU thread and 8 seeds; a larger cross-workload
  measurement would be needed to characterize build-time cost, other CPUs, and
  full-run performance.