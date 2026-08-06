# 2026-08-05-issue-49 — TERM_WIN terminal-leaf bonus: intermittent multithread segfault (resolved)

**Tier:** Medium (opt-in feature only; TERM_WIN defaults off)
**Status:** resolved 2026-08-06
**Source pages:** [combat-search](../architecture/combat-search.md),
[decision log `2026-08-05-phase3-terminal-value-stage2.md`](../decision-log/2026-08-05-phase3-terminal-value-stage2.md),
[decision log `2026-08-06-issue-49-term-win-mt-crash-fix.md`](../decision-log/2026-08-06-issue-49-term-win-mt-crash-fix.md)

## Symptom

`STS_TERM_WIN=1` (Searcher3 terminal-leaf run-value bonus) at 12 OpenMP
threads segfaults intermittently: ~2/6 runs on 32 seeds @1k/64p, with
**zero output lines** (crash precedes the first banner flush). The
`STS_TERM_STALL_LOG` config crashed 2/5. Single-thread runs: 0/5. ASAN
build: 0/8. Reproduced identically on the Phase-1 binary (6f0420d) — NOT
introduced by the Phase-2 changes (e4fbb4a).

## Evidence

- `EXPERIMENTS.md` §116; local repro on Phase-2 (be7d477) and Phase-1
  (6f0420d) binaries, 32 seeds @1k/64p, 12 threads, `STS_FAIR=1
  STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
  STS_FORCE_RELIC=HAPPY_FLOWER STS_TERM_WIN=1` (+`STS_TERM_STALL_LOG`).
- Control runs (no TERM_WIN) at 12 threads: clean across many runs.
- 1-thread TERM_WIN: 5/5 clean. ASAN (Debug + `-fsanitize=address`): 8/8
  clean.

## Why it matters

The bonus is opt-in and unpromoted (Stage-2 benchmark null, §116), so no
deployed configuration is affected. But the crash makes the TERM_WIN arm
unusable for any future cross-combat-setup work, and an intermittent
startup-time segfault in a parallel region suggests a latent race that
could resurface elsewhere.

## Root cause (confirmed 2026-08-06)

**Lazy-init data race in `termWinIndices()`** (`apps/one_combat.cpp:3317`):
`static TermWinIndices m; if (!m.ok) {...}` — the magic-static guard covers
only construction, so every worker thread entering on its first battle
raced on every field and on the `potIdx` vector's `push_back`s. The
resulting concurrent reallocation corrupted the heap (ThreadSanitizer
reported the `vector<int>` use-after-free and the SEGV inside
`termLeafBonus`, crash stack `termLeafBonus` → `evaluateTerminal` → `step`
→ `playoutBattleFair`). Torn `ix` values also made `termLeafBonus` patch
wrong row slots — the `[term-win parity] patched=2 full=26`-style garbage
seen in surviving runs (their TERM_WIN data was not trustworthy).

**Fix:** rewrote `termWinIndices()` as a magic-static lambda
(`static const TermWinIndices m = [] {...}();`) so the whole init runs
inside the construction guard. Applied for the GCP cpsi-eval arm by a
parallel session (Addendum 2,
`2026-08-05-terminal-leaf-run-value-bonus.md`) and verified here on the
win-tree arm.

**Verification:** local 12-thread repro (`bestbench 1000 12 0`, issue env)
**2/4 segfaults pre-fix → 0/6 post-fix**; 32-seed config 0/2. TSAN
post-fix: zero `termWinIndices`/`richIdxMap` races (pre-fix: 20+ reports).

## Follow-on fixes in the same arm (2026-08-06)

- `termLeafBonus` victory heals only replicated Burning Blood (+6);
  `exitBattle` also heals Black Blood (+12) and Meat on the Bone (+12
  below half HP) — now mirrored exactly in relic-container order.
- Potion slots were patched presence-hot while `richRow` is multi-count;
  now incremented (duplicate potions).
- Parity diagnostic feature label was off by one (raw layout vs full
  header names); fixed.
Post-fix parity check: **0 diagnostics** across 32-seed @1k runs; win%
unchanged (28.1% before and after).

## Related pre-existing races (not fixed, out of scope)

TSAN also surfaced, in the control arm too and with no observed crash:
`search::g_potionKeepValue` written per battle from every thread
(`apps/one_combat.cpp:2394`, read in
`src/sim/search/BattleScumSearcher2.cpp:725,767` — recommendation: make
`thread_local`), `g_debug_bc` (`src/combat/BattleContext.cpp:745`), and
`BattleContext::sum` (`BattleContext.cpp:539`). `richIdxMap()`
(`apps/one_combat.cpp:1404`) has the same mutate-after-guard pattern but
is de-facto safe (main-thread pre-warm during model load; the
`termWinIndices` fix removed its only concurrent first-use path).

## Status

Resolved. TERM_WIN stays opt-in/off (unpromoted, §116); the fix only
affects the opt-in arm. Details: decision log
`2026-08-06-issue-49-term-win-mt-crash-fix.md`.
