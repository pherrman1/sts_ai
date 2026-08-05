# 2026-08-04 — Dynamic sim-budget wave: convergence stop inert in fair play; C_psi adaptive budget delivered, not promoted

Date: 2026-08-04
Session/task: Implement and benchmark a heuristic that decides the combat
simulation budget dynamically (per decision and per fight), after the fair
3k/4k sim-budget finding (§98/§99). Two designs: re-test the existing
convergence early stop (per decision) and build a C_ψ difficulty-adaptive
per-fight budget.

## Decisions

1. **Convergence early stop is rejected for fair play (§102).** Re-running
   §22's `searchToTotalAdaptive` (`STS_CONVERGE`) at fair 3k with the V4 gate
   stack: (patience,min) ∈ {(200,200),(400,300),(800,400)} all produce
   **bit-identical per-seed results to flat V4@3k** (0 non-`sec` diffs on 64
   seeds) — the stop never fires. Mechanism: each fair `step()` re-determinizes
   hidden draws, so `bestActionValue` keeps improving and the plateau window
   never fills within 3k sims. §22's stop only worked in known-RNG where
   rollouts are near-deterministic. Any future per-decision stopping needs a
   different signal (best-action visit-share stability or windowed root value).
2. **C_ψ adaptive per-fight budget delivered, kept opt-in (§103).**
   `STS_SIM_ADAPT=1` + `STS_CPSI_NN` sets each fight's budget to
   `clamp(base·(0.5+P(death)+(1−E[hp|win])), 0.4, 2.0)·base` from one no-peek
   C_ψ forward pass at fight start (`apps/one_combat.cpp::fightSims`).
   Benchmark (3 × 256 seeds, paired vs flat V4@2k): combined **+1.8pp win
   (CI [−1.7,+5.3]), +1.4 HP, −12% compute (19.50 vs 22.10 cpu-s/run)**;
   blocks went +2.7/+3.9/−1.2pp. vs the V4@3k reference it tied on block 1
   (−39% compute) and lost 2.7pp on block 3. Win edge **not established**;
   compute saving real. Not promoted; flat V4@3k stays the operating point.
3. **Process:** all benchmarks on the GCP server (`sts-test`, 24 threads);
   local runs were stopped at the user's request because the other agent was
   benchmarking locally (`build/mapgate_qwin_cal_m0.10.csv`) — CPU contention
   risk. Server tree synced with `apps/one_combat.cpp` + `apps/ooc_strategic_net.h`
   (the §96 lesson: sync net headers with the driver — the server build failed
   on `mapEnc` until the header followed).

## Rationale

- §21/§22 established "no free lunch" for compute allocation in known-RNG;
  the C_ψ variant is the first dynamic budget with a favorable slope (~12%
  savings at equal win rate) — **Inference:** the no-peek C_ψ difficulty
  signal is better calibrated than room-type tiers, but the win-rate edge is
  within noise and block-dependent (block 3 flipped), so it is not yet a
  promotion candidate.

## Alternatives considered

- Static room-tier budgets (`STS_SIMS_*`) — already falsified (§21);
  C_ψ tiering is the learned replacement.
- Per-decision `bestActionValue` convergence — falsified in fair play (§102);
  a visit-share-based signal is the plausible successor.
- Frac tuning (min 0.3 / max 3.0) to amplify the win edge — deferred; the
  edge itself is not yet established, so tuning would overfit to noise.

## Evidence

- EXPERIMENTS.md §102/§103; per-seed CSVs `build/conv_*_64.csv`,
  `build/simsweep_v4_2k_256{,_b2,_b3}.csv`, `build/simadapt_2200_256{,_b2,_b3}.csv`,
  `build/simsweep_v4_3k_256_b3.csv`; `apps/one_combat.cpp::fightSims` +
  `STS_SIM_ADAPT*` env parse; `include/sim/search/CombatCpsiNet.h::predict`.

## Status and follow-up

- Delivered and recorded; both features opt-in (`STS_CONVERGE` unchanged,
  `STS_SIM_ADAPT=1` new). No default change; V4@3k remains the recommended
  configuration.
- Open: (1) visit-share/windowed-value convergence signal for true
  per-decision stopping in fair play; (2) frac tuning or a fourth block only
  if the win edge becomes a priority; (3) `STS_SIM_ADAPT` for future
  datagen (cheaper labels at same quality is untested).
