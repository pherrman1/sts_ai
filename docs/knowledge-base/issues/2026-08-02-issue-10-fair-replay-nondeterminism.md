# Issue 10: Fair multi-thread replay is not bit-identical; no test

- **Status:** closed
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

Verified on commit `63d8b89`: fair Searcher2 (1/8/12 threads, up to 128
seeds), fair Searcher3 (16 seeds), and known-RNG (32 seeds) runs replay
bit-identically across separate process invocations; only the `sec` timing
column differs. The recorded issue-02 artifact (128 seeds) reproduces exactly
(`EXPERIMENTS.md` §69; paired artifact `build/det_fair128_b.csv`). The
historical §66e/66j divergence does not reproduce; **Inference:** its cause
was stale `BattleContext` state under `schedule(dynamic)` outer parallelism,
fixed by the `BattleContext::init` full reset in `da8c902` (2026-07-26, three
days after the divergence was recorded). No `random_device`/time-based
seeding exists, observation hashing is integer-only, and OpenMP appears only
in the outer per-seed loops. `check_replay.py` (with `STS_FAIR=1` via env
inheritance) serves as the probe; caveat: verified for gcc 13 / `-O3` /
Linux/WSL only.

## Closed by

*Fixed by the 2026-08-02 determinism verification (`EXPERIMENTS.md` §69) plus
the `check_replay.py` probe from commit `63d8b89`.*
