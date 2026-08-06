# 2026-08-05-issue-49 — TERM_WIN terminal-leaf bonus: intermittent multithread segfault (open)

**Tier:** Medium (opt-in feature only; TERM_WIN defaults off)
**Status:** open
**Source pages:** [combat-search](../architecture/combat-search.md),
[decision log `2026-08-05-phase3-terminal-value-stage2.md`](../decision-log/2026-08-05-phase3-terminal-value-stage2.md)

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

## Candidate fixes

- Debugger session (gdb/lldb batch) on the crashing seed block; the
  zero-output timing points at the parallel-region setup / first
  `termWinArmForBattle` / shared model access rather than the leaf path.
- Audit shared state in the TERM_WIN arm: `g_winNet` load timing,
  `termWinIndices()`/`richIdxMap()` static maps (magic-static init should
  be safe), `t_curPath`/`t_term*` thread_locals, and the stall-log file
  creation.
- If the race is in the win-tree load or the parallel-region handoff,
  guard with a one-time init before the parallel for.

## Status

Open. Reproduces ~2/6 at 12 threads on both Phase-1 and Phase-2 binaries;
1-thread and ASAN clean. TERM_WIN stays opt-in/off; no action on the
recommended stack. Needs a debugger session to pinpoint.
