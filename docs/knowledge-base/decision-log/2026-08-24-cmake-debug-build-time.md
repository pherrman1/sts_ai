# 2026-08-24 — Configuration-aware CMake build optimization

## Decision

Keep the full CI all-target build, but make the Debug build automatically
parallel, remove forced `-O3` and LTO from Debug, and keep native Release
objects non-PIC. Release retains `-O3`, LTO, and OpenMP. A separate hidden/PIC
core object collection is used only by `slaythespire`.

## Rationale

The CI CTest graph directly executes `one_combat` and `unit-test`, but the other
executables and Python module are maintained build products. Preserving the
full build avoids silently reducing coverage. The expensive work was instead
removed at its source for native CI products: Debug no longer performs Release
optimization/LTO, and the five native executables share one non-PIC core
compilation. A module-side duplicate is intentional because native Release PIC
incurred a measured throughput loss.

## Alternatives considered

- Building only CTest's direct binary dependencies was rejected because it
  would stop validating maintained products.
- Unity builds, precompiled headers, compiler changes, and cache redesign were
  outside this focused task.
- Reusing PIC core objects for native Release was rejected after the matched
  throughput check measured an 8.8% CPU slowdown; the module-side duplicate is
  the smallest design that preserves native performance.
- Removing Release LTO was rejected because it is an established runtime
  performance choice.

## Evidence

- `CMakePresets.json`: `linux-gcc-debug-build` uses `jobs: 0`.
- `CMakeLists.txt`: configuration-aware compile/link options, shared native
  non-PIC objects, and a hidden/PIC module-only object collection.
- Generated Debug flags contain `-g`, `-fPIC` where needed, and `-fopenmp`, but
  no `-O3`, `-flto`, or `-DNDEBUG`; Release flags retain `-O3 -DNDEBUG
  -fopenmp -flto`.
- A clean local WSL Debug build with the initial shared-PIC design compiled
  `src/sim/search/BattleScumSearcher3.cpp` once, built all targets in 130.35 s,
  and emitted no LTO-wrapper message. The corrected module-only PIC design
  retains the same Debug flag behavior and imports successfully.
- `ctest --preset linux-gcc-test` passed 41/41 after syncing the locked
  analysis environment. The focused Release `one_combat` build passed.

## Status and follow-up

Adopted with the module-only PIC correction. The first authoritative GitHub
Actions run passed 41/41 tests and reduced the C++ build from approximately
3m47s to 71 s (68.7%); the full Linux GCC job fell from approximately 5m30s to
2m58s (46.1%). The restored baseline cache produced only 1/48 ccache hits
because the intentional PIC and flag changes altered compile commands; the
following warm run reached 47/48 hits and a 3 s C++ build. The matched Release
throughput check found the initial shared-PIC native design 8.8% slower in CPU
user time (two clean CPU-pinned pairs), so the final design keeps native
objects non-PIC and duplicates core compilation only for the Python module.
