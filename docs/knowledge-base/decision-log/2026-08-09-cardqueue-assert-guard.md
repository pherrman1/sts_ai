# 2026-08-09 — CardQueue overflow assert guard (issue #51); ActionQueue fix already in HEAD

Date: 2026-08-09
Session/task: Fix ActionQueue capacity overflow (issue #50) and CardQueue silent overflow

## Decision

- **ActionQueue (BUG 1): no code change made.** The 50→128 capacity increase
  is already in HEAD (`da8c902`): `include/combat/BattleContext.h:80`
  (`ActionQueue<128> actionQueue;`) and `src/combat/BattleContext.cpp:28`
  (`actionQueue = ActionQueue<128>{};`). The task brief claimed HEAD still had
  capacity 50; repository evidence disproved it, so that part of the plan was
  already satisfied. Issue
  `docs/knowledge-base/issues/2026-08-09-issue-actionqueue-overflow.md` is
  marked closed and its index row (which still said "open") was corrected.
- **CardQueue (BUG 2): guarded every capacity assert** in
  `src/combat/CardQueue.cpp` with `#ifdef sts_asserts` (matching the
  ActionQueue pattern) and added `#include "sts_common.h"` to that TU so the
  macro is visible — without the include, the guards would compile the
  asserts out in every build (verified by preprocessor check: 0
  `__assert_fail` expansions without it, 5 with it).
- Added a POSIX fork/waitpid death test `testCardQueueOverflow`
  (`./build/test cardqueue_overflow`, ctest `cardqueue_overflow`): an 11th
  push into the capacity-10 ring must abort with SIGABRT, locking in the
  "fail loudly, never silently wrap" contract.

## Rationale

- The project's assertion convention is the unconditional
  `#define sts_asserts` in `include/sts_common.h:8`; every other assert site
  (ActionQueue, Player, MonsterGroup, Actions, BattleContext) guards with
  `#ifdef sts_asserts`. The project build never defines NDEBUG
  (`CMakeLists.txt`: `-O3` without `-DNDEBUG`), so the guarded asserts are
  live in every project configuration. Matching that pattern is the minimal,
  convention-consistent fix requested by the plan.

## Alternatives considered

- Runtime discard-oldest-with-warning on overflow (the plan's option 2) —
  rejected: it masks overflow bugs instead of failing loudly and diverges
  from the ActionQueue behavior the bug is aligned with.

## Evidence

- `include/combat/BattleContext.h:80`, `src/combat/BattleContext.cpp:28` — `ActionQueue<128>` present in HEAD
- `src/combat/CardQueue.cpp` — 5 asserts guarded by `#ifdef sts_asserts`; `#include "sts_common.h"` added
- `apps/test.cpp` — `testCardQueueOverflow` (POSIX death test), dispatched from `main`
- `CMakeLists.txt` — `add_test(NAME cardqueue_overflow ...)`

## Status and follow-up

- Implemented. Build clean; all 13 ctest entries pass including the new
  `cardqueue_overflow`; `./build/test cardqueue_overflow` passes.
- **Open question**: under a hypothetical `-DNDEBUG` configuration the
  `<cassert>` macro is still a no-op (identical to ActionQueue and every
  other `sts_asserts` site); the project relies on never defining NDEBUG. If
  NDEBUG builds are ever required, asserts would need a custom macro.
- Pre-existing, out of scope: `CardQueue::containsCardWithId`
  (`src/combat/CardQueue.cpp`) never advances its index, so it only checks
  the front element.
