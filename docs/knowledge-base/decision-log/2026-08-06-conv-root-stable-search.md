# 2026-08-06 — STS_CONV_ROOT: root-stability adaptive search (Phase 1 of the adaptive-budget program); provisional 64-seed signal, gate pending

Date: 2026-08-06
Session/task: Implement the §102-recommended convergence signal — root-decision
stability (best action + visit share + windowed value) — as a per-decision
adaptive budget with budget-neutral reinvestment into ambiguous decisions;
plus the forced-move shortcut and the Phase 0 rollout-cause split that
diagnosed fair-mode rollout composition.

## Decisions

1. **Stability signal: most-visited root action + visit share + windowed
   mean value, checked every 100 sims.** Chosen over the §22/§102
   `bestActionValue` plateau (inert under fair determinization). Thresholds:
   share drift > 0.05, windowed value drift > 1.0 HP → drift. Snapshot
   resets on drift; stop after `patience` stable sims past `minSims`.

2. **Chunked escalation + budget-neutral pool (the reinvestment arm).**
   Each decision credits its flat budget to a per-fight `fightPool`; the
   search escalates 250 → 500 → 1000 → … up to `min(pool, MAX_FRAC x flat)`
   (default MAX_FRAC = 3.0) and deducts used sims. **Lesson:** a first
   implementation that escalated straight to frac x target with no pool
   cost 1.9x cpu (measured 64 seeds) — overdraw; the pool restores
   budget neutrality by construction.

3. **Forced-move shortcut:** `onlyLegalAction` (canonical enumeration) —
   exactly one legal action commits directly, no search, no searcher
   construction cost beyond the enumeration. Both fair and non-fair paths,
   gated by the same `STS_CONV_ROOT` flag.

4. **Env gate stays opt-in** (`STS_CONV_ROOT=1` + knobs); built-in defaults
   keep the conservative start (250) until the paired gate confirms;
   candidate operating point from 64 seeds: MIN=500 PATIENCE=500
   (see Evidence). Changing built-in defaults requires the T3 gate and a
   decision-log supersession.

5. **Phase 0 finding — fair illegal-stored-edge share:** rollout calls at
   fair @3k split ~50/50 between newly expanded leaves and stored edges
   illegal in the current determinization (3417 vs 3577 per decision; share
   grows 28%@100 → 68%@30k act 1). Consequence: the fair-vs-known-RNG tree
   coverage gap (54% vs 76%) is a real tree/determinization mismatch, not
   noise; Phase 4 structural options are constrained by the §114 obs-keyed
   falsification (do not retry obs-keyed descent).

## Alternatives considered

- Escalate straight to frac x target without a pool — rejected after the
  1.9x cpu measurement (Evidence below).
- Reuse `g_convPatience`/`g_convMinSims` (2000/1000 defaults) for the
  root-stability stop — rejected: at the 1k operating point that scale can
  never fire (patience > target); dedicated `g_convRootMinSims` (250) and
  `g_convRootPatience` (250) defaults.
- Per-fight pool only in the fair path — rejected: non-fair tree reuse
  accounting (shortfall deltas) also works; both wired.

## Evidence

- 64 seeds @1k fair, local WSL, 8 threads, asc 0, S2 fair, commit
  `4325c03` + this diff, per-seed CSVs `build/conv_*_64.csv` (machine-local):
  flat 23.4% / 23.3 cpu; MIN250-PAT250 17.2% / 19.0; **MIN500-PAT500
  26.6% / 21.2**; MIN750-PAT500 23.4% / 21.2; stop-only (MAX_FRAC=1,
  MIN500-PAT500) 20.3% / 17.4. Decomposition: stopping alone −3pp;
  pool escalation +6pp → candidate point +3.1pp at −9% cpu (all within
  64-seed noise, SE ≈ 7pp; 500/500 flips: 6 up / 4 down / 54 same).
- First implementation (no pool) measured 20.3% / 44.1 cpu (1.9x).
- Invariants: searchdiag rows reconcile (`sims == term+roll+leaf`;
  `rollout == leaf+illegal`) on 3844 fair rows; timing column sane
  (~165k sims/s).

## Status

Implemented, built, locally measured. **Superseded 2026-08-06 by the paired
gate (EXPERIMENTS.md §118): the candidate point MIN=500/PATIENCE=500 was
FALSIFIED.** 128-seed local: flat 21.9% vs candidate 21.1% (−0.8pp, flips
8 up / 9 down). 256-seed GCP gate: flat 22.3% (57 wins) vs candidate 19.9%
(51 wins) — paired delta −2.3pp (SE 2.07pp, 95% CI −2.3 ± 4.1pp), flips
13 up / 19 down; cpu −11% (real, directionally consistent across 64/128/256
seeds at −9/−8/−11%). The win signal from the 64-seed run (+3.1pp) did not
survive; per the plan's T3 rule (promote only if win ≥ flat with CI
excluding a meaningful loss AND cpu ≤ flat) the adaptive line is **stopped**,
built-in defaults stay env-gated opt-in (START 250 / PATIENCE 250), no
baseline-table update, Phase 2 remains parked. Follow-up per plan T2–T5:
completed in this entry and §118.
