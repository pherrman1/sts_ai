# Stage 0 of the value-head plan: the death price of the OOC leaf on today's stack (offline, 2026-10-22)

Plan: [Value heads: research plan](https://claude.ai/artifact/MoLmbWb4QXdLTEsDVYgt4a), section 7, stage 0. No game
seeds; data are §644's common-seed capture (320 A20 sources of gen-2 A/B arm A play, 70 Heart kills, 20,679
searched roots, 578,987 capture rows with 32 repeats each), `/mnt/project-files/ooc-sibling-crn/units/*.tar`.

## Tools
- [`tools/stage0.py`](tools/stage0.py) `EXTRACT OUT.json [--boot N] [--jobs N]`: calibration, levels, death prices,
  rollout vs real death rates, flips under M0′ (k = 1, 2) and M0, relevance. Output
  [`results/stage0.json`](results/stage0.json).
- [`tools/calib_check.py`](tools/calib_check.py) `EXTRACT OUT.json`: per-act slopes, a TRAIN → VALIDATION held-out
  check (§644's split, seed % 4 == 3), and the points as CSV. Output [`results/calib_check.json`](results/calib_check.json),
  [`results/calib_points.csv.gz`](results/calib_points.csv.gz).

## Results
- **Calibration** (per searched root: X2-B of the executed action's child, label = the run's Heart kill;
  logit p = a_act + b logit x): a = (−2.538, −2.923, −3.652, −3.633), b = 1.054 [0.81, 1.29] (source bootstrap,
  200). Separate slopes per act: 0.90, 0.97, 1.22, 1.10. Held out (fit on 240 TRAIN sources): predicted − observed
  on VALIDATION −0.002, +0.051, +0.070, +0.081 (acts 1–4; every 95% CI includes 0).
- **Level:** decision roots' X2-B vs Heart rate 0.75 vs 0.22 (act 1), 0.80 vs 0.27, 0.91 vs 0.38, 0.96 vs 0.58.
  Surviving rollout ends: x̄ = 0.746, 0.780, 0.889 (acts 1–3).
- **Death price.** Rollout3 prices a death at the surviving level L (ΔQ ≈ (1 − d)ΔL − LΔd). The calibrated price in
  X2-B units is x̄(1 − x̄) / (b(1 − p̄)) = 0.224, 0.196, 0.115, so X2-B over-prices a death **3.3× [2.5, 4.1]**,
  **4.0× [3.0, 5.0]** and **7.7× [5.5, 9.8]** in acts 1–3 (the 10-17 audit had 2.6×, 3.1×, 5.8×).
- **Rollout vs real deaths** (executed action's repeats vs the real run dying by the repeats' median surviving end
  floor): real / rollout 0.59 [0.40, 0.76], 0.85 [0.69, 1.04], 0.62 [0.53, 0.73], 0.80 [0.68, 0.94] (acts 1–4).
  Rollouts die more often than real play, so the effective over-pricing of death risk is larger still.
- **Relevance:** the prior's top action is below 0.95 at 36% of searched roots and below 0.99 at 49%; the search
  overrode the prior at 6.9%.
- **Flips** (PUCT proxy: fixed Q from the capture's 32 repeats per child, the root's priors and completed
  simulations, continuous PUCT allocation; it matches the played action at 91% of roots):

  | change | best-by-mean flips | PUCT flips | PUCT flips to the riskier sibling | mean Δ death share |
  |---|---|---|---|---|
  | M0′ k = 1 (death 0.52 / 0.58 / 0.77) | 13.0% | 5.1% | 97% | +0.10 |
  | M0′ k = 2 (death 0.30 / 0.39 / 0.66) | 7.1% | 3.6% | 96% | +0.09 |
  | M0 (calibrated leaf) | 17.4% | 7.0% (full roots 13.5%) | 74% | +0.075 |

  Predicted change of M0's flips: **+1.8 pp** Heart kills per run under M0's own calibration (act 1 −0.9, act 2 +1.6,
  act 3 +1.0); **−6.1 pp** if today's implied price were right (slope p̄ / x̄ per act).

## Finding: M0′ breaks at act borders
M0′ (the doc's shortcut: X2-B for survivors, death worth c_act) is a linearisation around one act's operating point.
Rollouts that cross an act border mix scales. The worst case is act 3 → 4: a rollout that dies at the act-3 boss
scores c₃ = 0.77, above the ≈ 0.54 average of rollouts that reach act 4 (43% of them die there at 0, kills score 1).
Under M0′ the search would prefer dying at the act-3 boss to reaching act 4. M0 (calibrate every surviving end in its
own act; deaths 0, kills 1) has one unit everywhere, so the A/B uses M0
([value_level_ab_20261023](../value_level_ab_20261023/PREREG.md)).
