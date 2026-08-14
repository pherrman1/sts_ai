# 2026-08-14 — Phase 6: Deduplicate native C++ core compilation

Date: 2026-08-14
Session/task: Phase 6 CMake native core object reuse

## Decision

Introduce the `sts_core_objects` OBJECT library and reuse its common
`src/*.cpp` objects from `main`, `one_combat`, `parity_test`, `unit-test`, and
`small-test`. Keep `slaythespire` independent and compiling the existing source
glob arrangement.

## Rationale

The native executables previously compiled every common source independently.
The object target gives those executables one compilation owner while keeping
application sources and `bindings/bindings-util.cpp` target-specific. Common
include requirements are attached to the object target; target-specific
requirements remain on the executable targets.

The Python module is deliberately excluded because Python/PIC/visibility
requirements are outside this phase and its source arrangement remains
semantically unchanged.

## Alternatives considered

- Static or shared library — rejected because Phase 6 specifically calls for
  an OBJECT library and does not introduce a new linkable library.
- Reusing `sts_core_objects` from `slaythespire` — rejected to preserve the
  separate Python/PIC/visibility compilation semantics.
- Unity builds, precompiled headers, ccache, or parallel-build changes —
  rejected as outside the single build-ownership variable for this phase.

## Evidence

- `CMakeLists.txt` + `sts_core_objects`: common sources are owned by one
  OBJECT target and consumed by the five native executables.
- Baseline command:
  `CCACHE_DISABLE=1 /usr/bin/time -p cmake --build build-phase6-before-2 -j1
  --target main one_combat parity_test unit-test small-test`
- Baseline result: success; `real 286.27`, `user 258.09`, `sys 23.39`.
- Baseline build log: `CMakeFiles/main.dir/src/...`,
  `CMakeFiles/one_combat.dir/src/...`, `CMakeFiles/parity_test.dir/src/...`,
  `CMakeFiles/unit-test.dir/src/...`, and `CMakeFiles/small-test.dir/src/...`
  independently compiled common translation units.
- Treatment command:
  `CCACHE_DISABLE=1 /usr/bin/time -p cmake --build build-phase6-after-1 -j1
  --target main one_combat parity_test unit-test small-test`
- Treatment result: success; `real 78.21`, `user 72.07`, `sys 5.86`.
- Treatment build log: 36 common translation units compiled once under
  `CMakeFiles/sts_core_objects.dir/src/...`; no native executable `src/*.cpp`
  compile lines appeared. All five expected executable paths existed.
- CTest command: `ctest --test-dir build-phase6-after-1 --output-on-failure`;
  27/27 tests passed.

## Status and follow-up

- **Implemented.** Native core compilation is deduplicated without changing
  executable names, CTest registrations, or the Python module's separate source
  arrangement. Temporary measurement directories remain for manual cleanup.