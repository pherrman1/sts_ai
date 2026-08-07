# 2026-08-07 — VNet target experiment (§132): quantile-R GBM beats endHp GBM on the leaf-utility scale; deployment gate is the next step

Date: 2026-08-07
Session/task: User asked whether to run an experiment on the target (the
§131-recommended deployable test). Answer: yes — ran the GBM target
experiment offline.

## Decision

- Trained two 9-quantile XGBoost models on the SAME rows as the deployed
  vnet (`build/vcombat_honest.csv`), identical split and hyperparameters,
  differing only in label: `utility_R = won ? 50+endHp : 0` vs raw `endHp`.
- Result: the utility-R model's mean-of-quantiles is on the leaf's terminal
  scale (EV-MAE vs R **10.10** vs 45.89/45.90 for both endHp variants,
  including the deployed 804-tree model on identical val rows). Win
  prob-from-quantiles slightly worse (0.085 vs 0.074). Quantile coverage
  calibrated for both.
- The deployable recipe (§131) is confirmed transferable: same cheap GBM
  class, better target. Deployment itself (C++ export + α sweep + paired
  gate) is NOT run this session — recorded as the next step.

## Rationale

- The deployed endHp model predicts ~46 HP below the terminal utility R —
  the scale mismatch the stack has compensated with α-blending and
  rank-sensitivity since §123/§126. An on-scale EV leaf could support a
  higher α (cf. §129's α 0.3→0.5 shift with better calibration).
- 9-quantile regression ≈ 9×150 = 1350 trees ≈ 1.7× the deployed 804-tree
  eval cost — within the §126 cpu-trade bar, unlike a 51-class softprob port
  (~50×).
- The R target also removes the old target's noise from 493 abandoned-fight
  rows (loss with endHp>0).

## Alternatives considered

- 51-class softprob port — rejected: ~50× the trees kills the cheap eval.
- Quantiles of endHp (old target, quantile flavor) — run as the control:
  45.89 EV-MAE — the target, not the quantile machinery, is the lever.
- Target-only transformer ablation — already done (§131).

## Evidence

- `build/vcombat_q150_results.json` (val, 43k rows): utility_R EV-MAE 10.10,
  win Brier 0.0851, covL2 0.0219; endHp EV-MAE 45.89, win Brier 0.0739;
  deployed vnet EV-MAE 45.90, endHp-MAE 5.59. `train_vcombat_quantile.py`,
  EXPERIMENTS.md §132.

## Status and follow-up

- **Next (deployment experiment):** C++ export of the 9 quantile sets +
  `leafValue` = mean-of-quantiles (± CVaR), α sweep, paired 256-seed gate vs
  the §126 deployed-vnet config. Coordinates with the parallel vnet-retrain
  line (other agent) — this is the target half of that line's recipe.

## Verdict (2026-08-07, gate §133 — appended, supersedes "next")

- **Falsified, line closed.** `combat_quantile_v1` implemented (loader +
  `predictQuantileEV`, parity max diff 0.0005, no searcher changes) and gated
  at 256 seeds × 3 αs: α0.3 37.5%, α0.5 40.2%, α0.7 32.0% vs the deployed
  vnet's 50.4% — all significantly negative (CIs exclude zero), at 1.7-2×
  cpu. The deployed honest-data vnet (§126) stays.
- The §132 offline EV-calibration win (10.1 vs 45.9) does NOT transfer —
  third consecutive offline≠online falsification (§124c, §127, §133).
  Hypothesis: the under-scaled endHp value blended at α0.3 is a better
  ranking prior than the correctly-scaled EV; the mean-of-9-quantiles
  estimator is crude for the bimodal R (90% wins).
- The transformer 51-bin CE model (§128/§131) remains the best offline value
  signal; no deployable GBM port exists. The vnet-retrain (data side, §129)
  stays the open deployable line.
