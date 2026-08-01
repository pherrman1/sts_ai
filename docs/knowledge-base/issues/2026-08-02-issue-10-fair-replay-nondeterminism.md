# Issue 10: Fair multi-thread replay is not bit-identical; no test

- **Status:** open
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md), "Known limitations"; [`evaluation/benchmark-protocol.md`](../evaluation/benchmark-protocol.md)

## Symptom

Historical repeated fair multi-thread runs were not bit-identical
(`EXPERIMENTS.md` entries 66e, 66j), and no automated equality test exists.
`ScreenStateInfo` sentinel initialization and `BattleContext::init` resets
reduce stale-copy behavior but do not establish whole-run determinism.

## Evidence

- `determinism-and-rng.md`: "Historical repeated fair multi-thread runs were not
  bit-identical... No automated equality test exists."
- `CMakeLists.txt`: no registered CTest tests; `apps/test.cpp::main` is a manual
  dispatcher.

## Why it matters

Reproducible whole-run evaluation is a stated goal; without a repeatability
test, new parallelization or RNG changes can silently break replay and produce
unreproducible benchmark rows.

## Candidate fix direction

Add a `reprobench`-based repeated-seed CSV equality check
(`apps/one_combat.cpp::reprobench`) as a registered or documented focused test;
isolate OpenMP scheduling effects by probing single-thread replay first.

## Relevant code

- `apps/one_combat.cpp::bestBench`, `reprobench`
- `CMakeLists.txt`
- `EXPERIMENTS.md` §66e, §66j

## Resolution (2026-08-02)

Partially resolved: `check_replay.py` (repo root) probes repeated-seed CSV equality and passes its self-test; fair multi-thread bit-identity remains unguaranteed and its root cause (OpenMP scheduling, shared globals, RNG construction) is still an open question.

## Closed by

*Fixed in the 2026-08-02 working tree. No change; remains open.*
