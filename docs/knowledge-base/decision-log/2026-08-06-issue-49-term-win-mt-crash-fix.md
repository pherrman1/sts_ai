# 2026-08-06 — Issue 49 fixed: TERM_WIN lazy-init race + transfer-parity fixes

Date: 2026-08-06
Session/task: Close issue 49 (intermittent multithread segfault in the
`STS_TERM_WIN=1` arm). Root cause was identified independently here with
ThreadSanitizer on the local (8-core WSL) binary and fixed in the same
session; this entry records that evidence, the two additional
transfer-parity fixes found by the now-working parity diagnostic, and the
remaining pre-existing races that TSAN surfaced.

## Decisions

1. **Issue 49 root cause confirmed: lazy-init data race in
   `termWinIndices()`** (`apps/one_combat.cpp:3317`). The
   `static TermWinIndices m; if (!m.ok) {...}` pattern lets the C++11
   magic-static guard cover only construction; every worker thread entering
   on its first battle then raced on every field and on the `potIdx`
   `push_back`s. TSAN caught the resulting `vector<int>` reallocation
   use-after-free and a heap corruption SEGV inside `termLeafBonus`
   (crash stack `termLeafBonus` → `evaluateTerminal` → `step` →
   `playoutBattleFair`). The fix is the magic-static lambda
   (`static const TermWinIndices m = [] {...}();`), which keeps the whole
   init inside the construction guard; applied by a parallel session for
   the cpsi-eval GCP arm (see Addendum 2 in
   `2026-08-05-terminal-leaf-run-value-bonus.md`) and present in the
   working tree here.
2. **Verification on the exact issue-49 repro passes.** Local 12-thread
   win-tree arm (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
   STS_S3_PARTICLES=64 STS_FORCE_RELIC=HAPPY_FLOWER STS_TERM_WIN=1`,
   `bestbench 1000 12 0`): **2/4 segfaults pre-fix → 0/6 post-fix** (and
   0/2 at the issue's 32-seed config). TSAN post-fix reports **zero**
   `termWinIndices`/`richIdxMap` races (pre-fix: 20+ reports at
   `one_combat.cpp:3322-3343` plus the realloc UAF).
3. **Two transfer-parity bugs fixed in `termLeafBonus`** (found because the
   parity diagnostic became deterministic and trustworthy post-fix):
   - Victory heals only replicated Burning Blood (+6); `exitBattle` also
     heals Black Blood (+12) and Meat on the Bone (+12 below half HP).
     `termLeafBonus` now mirrors `updateRelicsOnExit` exactly (relic
     container order).
   - Potion slots were patched presence-hot (1.0) while `richRow` is
     multi-count — duplicate potions mismatched. Patched to increment.
   - The parity diagnostic's feature label was off by one (it indexed the
     raw layout with the full `richHeader` name list, so it printed "floor"
     for `curHp`); fixed the lookup.
   Post-fix: **0 parity diagnostics** across 32-seed @1k runs (pre-fix:
   deterministic curHp +12 and potion-count mismatches), win% unchanged
   (28.1% both before and after the transfer fixes — they only correct the
   leaf row, which does not change the falsified arm's policy verdict).
4. **Pre-existing races found by TSAN, NOT fixed (out of scope, present in
   the control arm too, no observed crash):**
   - `search::g_potionKeepValue` written per battle from every worker
     thread (`runFullRunOOC`, `apps/one_combat.cpp:2394`) while searchers
     read it (`src/sim/search/BattleScumSearcher2.cpp:725,767`) — a real
     write-vs-write/read race that can leak one run's keep value into
     another thread's search. Benign in practice (aligned double), but
     multi-threaded search results are formally racy. Recommendation: make
     it `thread_local` in a separate change.
   - `g_debug_bc = this` (`src/combat/BattleContext.cpp:745`) and the
     `BattleContext::sum` accumulator (`BattleContext.cpp:539`) — debug
     globals, benign, pre-existing.
   - `richIdxMap()` (`apps/one_combat.cpp:1404`) has the same
     mutate-after-guard pattern as the fixed `termWinIndices`; it is
     de-facto safe because every entry path warms it on the main thread
     during model load, and the `termWinIndices` fix removed its only
     concurrent first-use path. Left as-is (matching the minimal fix);
     flag for a same-style hardening if a new worker-thread first-use
     path appears.

## Rationale

- The crash and its heap corruption were reproduced 2/4 locally pre-fix and
  eliminated 0/6 post-fix; TSAN evidence (use-after-free in `potIdx`
  reallocation + SEGV in `termLeafBonus`) is the strongest available proof
  of the mechanism.
- The transfer-parity fixes restore the arm's documented invariant ("the
  patched vector must equal the full vFeatCsv path on a real post-combat
  copy") — the parity check that enforces it now passes. They do not change
  benchmark numbers and do not affect the recommended stack (TERM_WIN
  stays opt-in/off, §116 null stands).

## Alternatives considered

- Adding a `std::call_once` guard instead of the lambda — equivalent, more
  code; the lambda keeps the existing "return a const reference" shape.
- Fixing `g_potionKeepValue`/`richIdxMap` in this change — rejected to keep
  the fix minimal and reviewable; both are documented above instead.

## Evidence

- TSAN runs (GCC 13, `build-tsan`): pre-fix reports at
  `one_combat.cpp:3322-3343` (termWinIndices field writes, `potIdx`
  `push_back`/`_M_realloc_insert` UAF) + SEGV in `termLeafBonus`; post-fix
  only the §4 pre-existing races remain.
- Crash screen: `termwin_screen` 12 seeds @1k/64p, 12 threads: 2/4 SEGV
  (pre-fix) → 0/6 (post-fix); 32 seeds @1k: 0/2.
- Parity diagnostics: deterministic `curHp` +12 mismatches (Black Blood
  heal) and `pot21` 1-vs-2 mismatches pre-fix; 0 post-fix.
- Concurrent session's evidence: Addendum 2 in
  `2026-08-05-terminal-leaf-run-value-bonus.md` (GCP 24-thread cpsi-eval
  arm, `malloc(): unaligned tcache chunk detected`, 256-seed sweep
  restarted with the fixed binary).

## Status

- Issue 49 **resolved** (issue note
  `docs/knowledge-base/issues/2026-08-05-issue-49-term-win-mt-crash.md`
  closed). TERM_WIN remains opt-in/off (unpromoted, §116). `ctest` local
  failure `selfplay_syntax` is a pre-existing Windows-checkout CRLF
  artifact (`bash -n` vs CRLF `selfplay/loop.sh`), unrelated to this fix.
