# Issue 25: Native inference probes a hard-coded OpenBLAS path

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`operations/build-and-debugging.md`](../operations/build-and-debugging.md)

## Symptom

Native PV/distribution inference probes a developer-specific SciPy OpenBLAS
path and otherwise falls back to scalar math. Performance and, potentially,
numerics depend on an environment-specific shared object.

## Evidence

- `src/sim/search/CombatPVNet.cpp` and `CombatDistValueNet.cpp` BLAS
  initialization blocks.
- `build-and-debugging.md`: "Native PV/distribution code attempts a
  developer-specific SciPy OpenBLAS path before scalar fallback."

## Why it matters

Benchmarks run on machines without that path silently use scalar math with very
different speed, changing simulation throughput (and therefore results) across
environments without any provenance marker.

## Candidate fix direction

Detect BLAS via a build-time option or `find_package`, or record which backend
was used in startup output so load messages identify the regime.

## Relevant code

- `src/sim/search/CombatPVNet.cpp`
- `src/sim/search/CombatDistValueNet.cpp`

## Resolution (2026-08-02)

Fixed: `init_blas()` in `CombatPVNet.cpp` and `CombatDistValueNet.cpp` prints the active backend once at load time (`BLAS: OpenBLAS <path>` or `BLAS: scalar fallback`); math semantics unchanged.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
