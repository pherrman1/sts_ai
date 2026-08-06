# 2026-08-05 — Phase 3 Stage 2 (post-combat run utility): TERM_WIN paired benchmark null; intermittent crash in the opt-in path

Date: 2026-08-05
Session/task: Execute the plan's Phase 3 Stage 2: controlled paired
benchmark of the Searcher3 terminal-leaf run-value bonus (`STS_TERM_WIN=1`,
win-tree evaluator) with forced Happy Flower in both arms + stall
telemetry, on the current honest stack.

## Decisions

1. **Stage 2 falsified — the terminal-leaf bonus is not promoted.** 256
   seeds @1k/64p (fair, A0, S3-belief-chain off, V4 gate stack, forced
   HAPPY_FLOWER): control 37.5% vs TERM_WIN 37.9% (+0.4pp, 39v38 flips) —
   null. Stall telemetry (733/731 battles): charged-counter rate +1.5pp,
   turns +0.11/battle, per-seed counter diff +0.05±0.20 — negligible. Cost:
   3.1x cpu (32.4 vs 10.5 cpu-sec/run) at 1k sims.
2. **Stage 3 stays deferred.** The bonus's design target (cross-combat
   counter alignment) is invisible to the deployed win tree (§110: 0/1060
   trees split on any counter relic), so the null is expected; a
   counter-aware terminal model would be required before re-testing. With
   no measured benefit and the crash below, no further Stage-3 investment
   now.
3. **New issue 49 — intermittent multithread crash in the TERM_WIN path
   (pre-existing).** `STS_TERM_WIN=1` at 12 threads segfaults ~2/6 runs
   (0 output lines; stall-log config 2/5); 0/5 single-thread; 0/8 ASAN.
   Reproduced identically on the Phase-1 binary (6f0420d), so the Phase-2
   changes did not introduce it. Crash precedes the first banner flush —
   startup/parallel-region race in the opt-in arm. Recorded as
   `2026-08-05-issue-49-term-win-mt-crash.md`; needs a debugger session.

## Rationale

- The paired benchmark is the plan's Stage-2 protocol; the null + cost
  verdict closes the line as instructed by the §109/§110 evidence (win tree
  counter-insensitive).
- TERM_WIN defaults off, so the crash does not affect the recommended
  stack or any deployed configuration; it is an opt-in-feature defect.

## Alternatives considered

- Run the `STS_TERM_WIN_W` sweep — not run: no win-rate signal exists at
  the default W to sweep; the cost floor (3.1x) already argues against.
- C_psi evaluator (`STS_TERM_WIN_EVAL=cpsi`) arm — deferred with Stage 3:
  the §110 probe shows correct counter pricing, but the §109 smoke found
  no transfer; without a counter-aware leaf model the bonus cannot win.

## Evidence

- EXPERIMENTS.md §116; CSVs `build/p3_ctl_hf_1k_256.csv`,
  `build/p3_term_hf_1k_256.csv` (GCP + local), stall logs
  `build/p3_stall_{ctl,term}.csv`.
- Crash repro: Phase-2 and Phase-1 (6f0420d) binaries, 32 seeds @1k/64p,
  12 threads, TERM_WIN=1 ± stall log; 1-thread and ASAN control runs clean.

## Status

- Phase 3 Stage 2 closed as falsified; Stage 3 deferred (counter-aware
  terminal model required first). GCP shut down after this batch (per
  instruction). Committed with EXPERIMENTS.md §116.
