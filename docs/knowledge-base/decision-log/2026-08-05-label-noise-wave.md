# 2026-08-05 — Label-noise wave (post-Phase F): noise readings all falsified; the one-ply label ranking is the ceiling

**Date:** 2026-08-05. **Task:** after §104 falsified the distillation
objective, test whether label noise explains the missing transfer — value
quantization, single-path variance, and trainer-side target engineering.

## Decisions

1. **The label-noise reading of §104 is falsified** (EXPERIMENTS.md §105):
   futures=2 variance reduction (matched 500-seed control, same seeds, same
   recipe) collapses the value grid from 55 to 126k distinct values with zero
   gain on dist_top1/q_top1 (+0.001 q_top1); trainer-side denoising
   (STRAT_DIST_MARGIN_EPS/SPREAD_W/TERM_W) all fail the pre-registered
   offline gate and degrade q_top1. The one-ply label **ranking** — not its
   noise — is the ceiling.
2. **No gate A/B for any arm** (pre-registered: offline gate first; no arm
   qualified).
3. **L1b (K=6 deep targets, 5.7.1b) is not run** — L0 showed truncation is
   the weak lever (terminal-vs-censored agreement gap only ~6pp) and L1a
   showed label precision does not transfer. Recorded as deferred/closed
   with this reasoning; the action-plan 5.7.1b item stays unchecked with the
   reason.
4. **The learned one-ply label line is closed**: Q-gate (§96), map encoder
   (§100), policy objective (§104), label noise (§105) are all falsified on
   the current Tier-B labels. The remaining options are 5.7.3 (the iterative
   play→search→train loop) or abandoning one-ply counterfactual labels as
   the OOC learning signal. (Status: not decided — **Open question**.)

## Rationale

- Matched control design (f1 vs f2, same 500 seeds 200000–200499, λ=0.5,
  τ=1.0, 60 epochs) isolates the futures knob — dataset-size effects cancel
  (verified: q_top1 ~0.30 on both 500-seed sets vs 0.36 on the 1,295-seed
  set, i.e., volume dominates precision).
- L0 terminal-only groups (exact 0/1 outcomes, no bootstrap) still disagree
  with behavior 43.3% of the time — even zero-noise labels don't align with
  behavior, and §104 showed following the label argmax loses in the gate
  (**Inference**: the counterfactual ranking is not the causal best route,
  §62 lesson, replicated at every noise level).
- 5.7.3 remains the only untested reframe because it changes the *labels'
  semantics* (self-play search policies) rather than their precision
  (**Inference**).

## Alternatives considered

- **A/B the futures=2 model anyway** despite the offline miss — rejected:
  pre-registered protocol; the offline metrics are consistent across three
  independent angles (L0/L1a/L2).
- **Run K=6 (5.7.1b) regardless** — rejected on L0 evidence (truncation is
  the weak component); noted as a possible cheap completeness run if the
  line is ever reopened.
- **Bigger futures=2 datagen (1,295 seeds)** — rejected: the matched
  comparison shows no effect at 500 seeds; scale would not create one.

## Evidence

- `EXPERIMENTS.md` §105 (L0 probe numbers, matched f1/f2 table, L2 table).
- `train_strategic.py`: STRAT_DIST_MARGIN_EPS / SPREAD_W / TERM_W (defaults
  byte-parity with §104; verified by construction and the smoke runs).
- `build/strategic_qwin_f{1,2}.csv` (+logs); models
  `selfplay/models/ooc_strategic_qwin_f{1,2}_*.pt`,
  `ooc_strategic_qwin_cal_dist_{eps,spread,term}.pt` (md5s in §105).

## Status and follow-up

- **Closed as falsified.** Follow-up (Open question): 5.7.3 iterative loop
  vs. abandoning one-ply labels; either way a new decision record is needed
  before further OOC learning work.
