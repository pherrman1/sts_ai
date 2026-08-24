# 2026-08-24 — Configuration-aware CMake build optimization

## Decision

Keep the full CI all-target build, but make the Debug build automatically
parallel, remove forced `-O3` and LTO from Debug, and reuse the PIC
`sts_core_objects` objects in `slaythespire`. Release retains `-O3`, LTO, and
OpenMP.

## Rationale

The CI CTest graph directly executes `one_combat` and `unit-test`, but the other
executables and Python module are maintained build products. Preserving the
full build avoids silently reducing coverage. The expensive work was instead
removed at its source: Debug no longer performs Release optimization/LTO, and
the Python module no longer recompiles every core translation unit.

## Alternatives considered

- Building only CTest's direct binary dependencies was rejected because it
  would stop validating maintained products.
- Unity builds, precompiled headers, compiler changes, and cache redesign were
  outside this focused task.
- Removing Release LTO was rejected because it is an established runtime
  performance choice.

## Evidence

- `CMakePresets.json`: `linux-gcc-debug-build` uses `jobs: 0`.
- `CMakeLists.txt`: configuration-aware compile/link options and PIC object
  reuse by `slaythespire`.
- Generated Debug flags contain `-g`, `-fPIC` where needed, and `-fopenmp`, but
  no `-O3`, `-flto`, or `-DNDEBUG`; Release flags retain `-O3 -DNDEBUG
  -fopenmp -flto`.
- A clean local WSL Debug build compiled
  `src/sim/search/BattleScumSearcher3.cpp` once, built all targets in 130.35 s,
  and emitted no LTO-wrapper message. The module imported successfully.
- `ctest --preset linux-gcc-test` passed 41/41 after syncing the locked
  analysis environment. The focused Release `one_combat` build passed.

## Status and follow-up

Adopted pending authoritative GitHub Actions timing. Compare its C++ build and
total-job duration with the approximately 3m47s / 5m30s baseline and record the
ccache statistics in the pull request.
