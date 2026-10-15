# Issue: CardQueue capacity-10 overflow silently corrupts under NDEBUG

**ID:** 51
**Date:** 2026-08-09
**Tier:** High
**Status:** closed (2026-08-09 — capacity asserts guarded by `sts_asserts`, matching ActionQueue)
**Source:** `src/combat/CardQueue.cpp` (`pushFront`/`pushBack`/`popFront`/`popBack`/`front`), `include/combat/CardQueue.h`

## Symptom

`CardQueue` is a capacity-10 ring buffer whose overflow asserts use the raw
`<cassert>` `assert()` without the project-wide `sts_asserts` guard. In a
build that defines NDEBUG the assert compiles out and an 11th `pushBack`
silently wraps: `arr.at(backIdx)` overwrites the oldest queued card while
`size` grows past `capacity`, corrupting the ring buffer.

## Evidence

- `include/combat/CardQueue.h:9` — `#include <cassert>`; `capacity = 10`.
- `src/combat/CardQueue.cpp` — `assert(size != capacity)` in `pushBack`
  (and `pushFront`, `popFront`, `popBack`, `front`) with no `sts_asserts`
  guard before the fix.
- `include/sts_common.h:8` — unconditional `#define sts_asserts`; every other
  assert site (ActionQueue, Player, MonsterGroup, Actions, BattleContext)
  wraps its asserts in `#ifdef sts_asserts`.
- The project build (`CMakeLists.txt`: `-O3` without `-DNDEBUG`) keeps
  `assert()` live; NDEBUG is never defined by the project configuration.

## Why it matters

- Silent ring corruption under NDEBUG produces wrong combat state instead of
  a loud failure, invalidating results.
- Inconsistent with the `ActionQueue` convention, where the same class of
  overflow fails loudly via the `sts_asserts`-guarded assert.

## Candidate fix directions

1. **Guard the asserts with `#ifdef sts_asserts`** (chosen) — matches the
   ActionQueue pattern; asserts stay live in every project build.
2. **Runtime discard-oldest with warning** — preserves progress on overflow
   but masks the bug instead of failing loudly.

## Relevant code

- `src/combat/CardQueue.cpp` — `pushFront`, `pushBack` (overflow asserts)
- `include/sts_common.h:8` — unconditional `#define sts_asserts`
- `include/combat/ActionQueue.h:72–95` — the pattern this fix mirrors
- `apps/test.cpp` — `testCardQueueOverflow` regression death test (ctest `cardqueue_overflow`)
