# 2026-08-02 — Fair replay determinism verification

Date: 2026-08-02
Session/task: Root-cause issue 10 (fair multi-thread replay divergence).

## Decision

Investigated whether fair multi-thread whole-run replay is bit-identical on
current code, and why the historical §66e/66j divergence (2026-07-23) is gone.
Findings recorded in `EXPERIMENTS.md` §69 and `determinism-and-rng.md`; issue
10 closed.

## Result

- Bit-identical across separate process invocations for: fair Searcher2 at
  12/8/1 threads (32/32/16 seeds), fair Searcher2 at 128 seeds (reproduces the
  recorded `build/bench_2026-08-02_default_fair.csv` exactly), fair Searcher3
  (16 seeds), known-RNG Searcher2 (32 seeds). Only the `sec` timing column
  differs.
- Historical cause (**Inference**): stale `BattleContext` nested state under
  `schedule(dynamic)` outer parallelism, fixed by the full reset in
  `BattleContext::init` (commit `da8c902`, 2026-07-26 — three days after the
  divergence was recorded; its comment states the stale-state dependency
  explicitly).
- Supporting facts: no `random_device` or time-based seeding; observation
  hashing is integer-only (`hashMix`); OpenMP appears only in the outer
  per-seed loops of `apps/one_combat.cpp`; agents are seeded from run seeds.

## Alternatives considered

- Diagnosing via single-thread replay first — done; single-thread was already
  identical, which pointed to either scheduling-visible shared state or
  in-run nondeterminism; the global audit (no random_device/time seeds) plus
  the 07-26 reset fix comment settled on stale state.
- Blaming OpenMP scheduling itself — rejected: `schedule(dynamic)` order
  cannot change results when each run is self-contained, which the bit-identity
  across thread counts confirms.

## Evidence

- `EXPERIMENTS.md` §69 (configs, seed blocks, results).
- Paired artifact `build/det_fair128_b.csv` (ignored build dir).
- `check_replay.py` end-to-end fair probe: `STS_FAIR=1 python3
  check_replay.py 1000 16 0 126700` → PASS.
- `da8c902` `src/combat/BattleContext.cpp::init` reset block comment.
- Updated `determinism-and-rng.md`, `benchmark-protocol.md`,
  `investigations/README.md`, issue entry 10.

## Status and follow-up

- Issue 10 closed. Caveat recorded: verified for gcc 13 / `-O3` / Linux/WSL
  only; MSVC/sanitizer/other-machine bit-identity remains an open question.
- Changes are uncommitted in the working tree.
