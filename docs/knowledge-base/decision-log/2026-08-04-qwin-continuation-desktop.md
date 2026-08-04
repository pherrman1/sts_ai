# 2026-08-04 — Wave A1/B desktop execution: corrected-label retrain, V5 export, margin + regret-gate sweeps (both negative)

Date: 2026-08-04
Session/task: Execute ooc-qwin-continuation.md on the desktop GPU machine
(Steps 1–5): retrain V3 Q_win on the corrected labels, export V5, A/B +
Q_win truth-check, probability-point margin sweep, Wave B regret gate
implementation + comparison. All steps done; both swept policies are
negative; the regret gate stays opt-in.

## Decisions / findings

1. **Corrected-label retrain on the desktop (RTX 3060 Ti):** the transferred
   `build/strategic_qwin_cal.csv` (7.57 GB, 809,146 rows / 1,295 seeds —
   full-float format, smaller than the laptop's 1.92 GB / 900,916 rows) had a
   truncated final line (NaN labels inside a valid policy group → NaN group
   CE → detached-loss crash). Fixed by truncating at the last complete line;
   retrain completed (best epoch 40): val_pol_ce 0.4671, policy_top1 0.7967,
   q_brier 0.0409, **q_cal_max 0.0647 vs the doc's <0.03 target — missed**.
   The 7.57 GB size is the re-serialized float format, not more rows.
2. **V5 export + A/B:** export parity 32/32. Own-split A/B: calibrated better
   on Brier/MAE/top1, worse on cal_max (different datasets — indicative).
3. **Truth-check (new `check_vwin_calibration.py --ckpt` mode):** on 44,865
   terminal chosen rows, both Q_win heads are **under-confident at the top
   deciles** (V_win trees remain over-confident): biased Brier 0.097 / decile
   0.306, calibrated 0.113 / 0.376. **Inference:** the bootstrap bias did
   not propagate into the head as over-confidence; the isotonic correction
   (which lowers censored labels) moved the head further from terminal
   calibration. The §94/§95 expectation was falsified; the K=6 transfer
   datagen remains the definitive test (deferred).
4. **Margin sweep (§96):** every Q_win point loses to the V3 legacy reference
   (39.8%); only biased m0.01 (33.6%) spans zero (−6.2pp CI [−15.6,+3.1]).
   Recalibration did not improve policy: biased m0.01 beats calibrated m0.01
   (33.6 vs 27.3); m≥0.03 both ≈ baseline (21.1%).
5. **Wave B regret gate:** implemented (env `STS_OOC_STRATEGIC_GATE=regret`,
   `STS_OOC_STRATEGIC_GATE_EPS`; `regretGateChoose`/`regretGateTail`;
   fingerprint-identified a_heur against the **live fallback chain**).
   First version mis-specified SHOP's a_heur as the datagen default
   (relic-buy-or-random via `stepOutOfCombatPolicy`) instead of the live
   `shopVPolicy` fallback — measured 13.3–18.8% (below baseline); after the
   fix (t_shopV + live-fallback runners incl. eventV/bossRelicV/pathV
   mirrors) the gate is ≈ baseline at every ε (19.5–22.7%) and strictly
   worse than the margin gate. Pre-registered adoption rule fails at 128 →
   **regret gate stays opt-in (default off)**; no 256 run.
6. **Process:** (a) server sync must include the net headers — a stale
   pre-V5 `apps/ooc_strategic_net.h` on the rsync-copied server tree made the
   V5 model fail to load ("truncated payload") and all runs silently measured
   the flags-off baseline; (b) the transferred CSV truncation crashed the
   trainer with a misleading autograd message; (c) the GCP VM was terminated —
   `gcloud compute instances start` before sweeping.

## Evidence

EXPERIMENTS.md §96; `apps/one_combat.cpp` (regret gate, t_shopV,
regretHeur*); `check_vwin_calibration.py --ckpt`; artifacts
`selfplay/models/ooc_strategic_qwin_cal.{pt,native,metrics.json}`,
`build/qwin{,_cal}_m*.csv`, `build/regret_cal_e*.csv`, server
`/tmp/qwin_sweep/`; `ooc_strategic_qwin_cal_train.log`.

## Status and follow-up

Wave A1/B execution complete and recorded; no default-flip. Follow-ups
(deferred per the plan): Q_boss aux head (needs datagen boss-flag column);
K=6 calibration transfer validation on 50–100 fresh seeds; V4 Q_win retrain;
C++-side bootstrap recalibration in `finishOocCounterfactual` (only
justified if the K=6 check shows the head inherits the V_win error — the
terminal truth-check argues it does not, in the inflation direction).
