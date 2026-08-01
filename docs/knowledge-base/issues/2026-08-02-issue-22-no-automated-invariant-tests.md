# Issue 22: No automated invariant/test suite exists

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`behavior/invariants.md`](../behavior/invariants.md), "Known limitations"; [`architecture/overview.md`](../architecture/overview.md)

## Symptom

No test automatically asserts combat terminal-field usage, observation
identity, schema order, native/server parity, or self-play arm ownership. CMake
registers no CTest tests; `apps/test.cpp::main` is a manual dispatcher whose
no-argument invocation only smoke-checks argument parsing.

## Evidence

- `behavior/invariants.md` "Known limitations": the explicit list of
  unasserted invariants.
- `CMakeLists.txt`: no `enable_testing`/`add_test`; `apps/test.cpp::main`.

## Why it matters

Most repository invariants are enforced only by review discipline. Issues 03,
04, 05, 07, 09, and 10 are precisely the class of regression that automated
tests would catch.

## Candidate fix direction

Prioritize the invariants by risk (observation identity, schema order, combat
terminal field, arm ownership) and add the cheapest checks first, e.g.,
producer/consumer schema tests and a `test` dispatcher subcommand.

## Relevant code

- `CMakeLists.txt`, `apps/test.cpp::main`
- `behavior/invariants.md` "Known limitations"

## Resolution (2026-08-02)

Fixed: `enable_testing()` plus CTest entries (selfplay `bash -n`, `py_compile`, `check_replay --self-test`; 5/5 pass); the `test` dispatcher gained targeted Searcher3 checks and `small-test isbattleover` covers the terminal-field derivation. Deeper invariants remain review-enforced.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
