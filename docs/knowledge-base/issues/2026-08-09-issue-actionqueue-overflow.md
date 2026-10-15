# Issue: ActionQueue capacity-50 overflow crashes combatgen

**ID:** (assign next)  
**Date:** 2026-08-09  
**Tier:** High  
**Status:** closed (2026-08-09 — capacity increased 50→128)  
**Source:** `include/combat/ActionQueue.h:88`, `include/sts_common.h:8`

## Symptom

`combatgen` (and likely any mode exercising many fights under the vnet-default
fair-S3 path) crashes with:

```
one_combat: include/combat/ActionQueue.h:88:
void sts::ActionQueue<capacity>::pushBack(sts::Action) [with int capacity = 50]:
Assertion `false' failed.
```

Hit at run 14,800/100,000 during the 2026-08-09 combatgen datagen run (seeds
3000–102999, 1,000 sims, fair S3−belief−chain/64p, vnet default ON).

## Evidence

- `ActionQueue` has a fixed capacity of 50 actions (`include/combat/ActionQueue.h`).
- `#define sts_asserts` is unconditional in `include/sts_common.h:8`.
- Certain card/relic combinations (e.g., Dead Branch + Corruption + high card
  generation) can queue more than 50 actions between `executeActions` flushes.
- The crash occurred once in 14,800 seeds — rare but reproducible under the
  current fair-S3+vnet config, which produces longer/deeper fights.

## Why it matters

- **Datagen:** long-running datagen jobs crash mid-run, losing hours of work.
- **Benchmarks:** a rare combat state that overflows the queue may crash
  bestbench/benchmark runs on specific seeds.
- **Self-play:** if the self-play loop hits this seed, the loop aborts.

## Candidate fix directions

1. **Increase capacity** (e.g., 50 → 128). Simple, but doesn't guarantee
   the bound is sufficient.
2. **Remove the assert and silently drop** — the code already wraps `back`
   without the assert, but dropping actions causes silent data corruption.
3. **Dynamic queue** — replace the fixed array with `std::vector`. Requires
   performance measurement (action queue is in the hot path).

## Relevant code

- `include/combat/ActionQueue.h:72–95` — `pushBack` with `sts_asserts` guard
- `include/sts_common.h:8` — unconditional `#define sts_asserts`
