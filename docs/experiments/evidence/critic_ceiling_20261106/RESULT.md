# Offline critic ceiling check (stage 0): RESULT

Pre-registration: [PREREG.md](PREREG.md) (review K PASS on 22b30629, merged as #998 `c5369c58`). Run on the PC
(pop-os, RTX 3060 Ti) 2026-11-06 23:33 CET to 2026-11-07 05:06 CET, after LONG_C finished (SERVE_DONE 23:29 CET).
Philipp's go: 2026-11-06 23:32 CET ("Go"). Offline only: no seeds, no games, no cloud workers.

Raw records (transport ref `ppo-xfer/critic-ceiling` = `38508ccf`, parentless commit, copied here):
`report_primary.json`, `report_gbm_secondary.json`, `commands.log`, `gbm_primary.json`, `gbm_secondary.json`.
The fitted models (`net_primary.pt` 24.4 MB, the xgboost `.ubj` files) stay on the PC in `~/critic-ceiling-out/`.

## Provenance

- Code: worktree `~/sts-critic-ceiling` at `22b30629` (= main `c5369c58` in the tool, tests and PREREG), `/usr/bin/python3`
  (numpy 2.5.1, scipy 1.18.0, xgboost 3.4.0, torch 2.5.1+cu121); `python3 -m unittest tests.test_critic_ceiling` 6 OK on the PC.
- Freeze point **N = 420** (newest complete LONG_C iteration 0419 at the start). Test: LONG_C iterations 0400-0419,
  800 parts, 10,400 games, 1,140,464 net decisions. Primary training: 0220-0399 (7,200 parts). Secondary: plus LONG_B
  0000-0219 (8,800 parts). Init net `net-0399.bin` sha256 `accf8720…b515b99c`.
- Test Heart rate 20.55% of games.

## Deviations (all in `commands.log`)

1. Running the GBM and net primary fits in parallel pushed available RAM under the 4 GB guard, so they were rerun one after the other.
2. The **net primary** did not fit in host RAM at full data, so it ran with `--game-frac 0.5`: 470,995 train and 24,668 val rows. The GBM primary used full data: 941,186 train and 49,129 val rows.
3. The GBM secondary ran with `--game-frac 0.5` for the same reason: 1,047,771 train rows. The net secondary was skipped, because the primary had already decided and the evaluate is slow (about 50-115 min).
4. The secondary evaluate was stopped once by a 2 h limit on the background runner, then rerun unchanged.

## Fits (5% seed-hashed validation split of the training games; not test scores)

- GBM primary: val log loss 0.5126 at round 0, 0.3825 at the best iteration 1871 (1,399 features, 610 s).
- Net primary: val log loss 0.5154 at epoch 0, **0.4021 at epoch 1 (kept)**, 0.4030 at epoch 2, 0.4416 at epoch 3 (overfits), 1,116 s.
- GBM secondary: 0.4919 → 0.3728 at the best iteration 1969 (1,401 features, 1,085 s).

## Primary result: **NO_GO**

Per act on every test decision (AUC / EV against the outcome):

| Estimator | First decision | Act 1 | Act 2 | Act 3 | Act 4 | All |
| --- | --- | --- | --- | --- | --- | --- |
| online (raw) | 0.526 / 0.001 | 0.671 / 0.073 | 0.782 / 0.221 | 0.825 / 0.312 | 0.817 / 0.279 | 0.784 / 0.244 |
| online_cal | 0.526 / 0.001 | 0.671 / 0.072 | 0.782 / 0.219 | 0.825 / 0.315 | 0.817 / 0.282 | 0.784 / 0.243 |
| net (game-frac 0.5) | 0.523 / 0.001 | 0.655 / 0.062 | 0.776 / 0.210 | 0.821 / 0.307 | 0.827 / 0.296 | 0.773 / 0.227 |
| gbm | 0.511 / 0.000 | 0.662 / 0.063 | 0.785 / 0.224 | 0.833 / 0.331 | 0.839 / 0.318 | 0.782 / 0.242 |
| gbm secondary (+LONG_B, 0.5) | | 0.662 / 0.064 | 0.783 / 0.221 | 0.829 / 0.324 | 0.838 / 0.316 | 0.781 / 0.239 |

Decisions per act: 515,422 / 354,651 / 230,047 / 40,344.

The gate compares each estimator with online_cal: difference in log loss and in EV, with 98.75% game-cluster bootstrap CIs (2,000 resamples).

| Estimator, scope | Δ log loss [98.75% CI] | Δ EV [98.75% CI] | Verdict |
| --- | --- | --- | --- |
| net, act 1 | +0.0247 [+0.0192, +0.0301] | −0.0101 [−0.0146, −0.0059] | NOT_BETTER |
| net, all | +0.0138 [+0.0101, +0.0175] | −0.0164 [−0.0229, −0.0097] | NOT_BETTER |
| gbm, act 1 | +0.0419 [+0.0340, +0.0494] | −0.0095 [−0.0148, −0.0041] | NOT_BETTER |
| gbm, all | +0.0169 [+0.0109, +0.0229] | −0.0011 [−0.0079, +0.0056] | NOT_BETTER |
| gbm secondary, act 1 | +0.0454 [+0.0377, +0.0529] | −0.0077 [−0.0116, −0.0037] | NOT_BETTER |
| gbm secondary, all | +0.0206 [+0.0149, +0.0267] | −0.0033 [−0.0105, +0.0034] | NOT_BETTER |

Against raw online the picture is the same (`bootstrap_vs_raw_online`: net act 1 Δ log loss +0.023, Δ EV −0.011).
The per-act Platt fit (act 1: a −2.59, b 5.69) barely changes the online critic on these data: act-1 EV −0.001 and log loss −0.0013. The raw value head was already roughly calibrated at LONG_C's scale; cov8's 0.965 came from heart1 values.

## Interpretation

- **Inference:** the online PPO critic already gets about as much act-1 signal as these records and model classes offer.
  - Act-1 EV is 0.07 and AUC 0.67. At the run's first decision, AUC is 0.53 and EV ≈ 0.
  - Neither a separate-trunk net (BCE, 470k rows) nor an all-field GBM (941k rows) beats it, and doubling the data with LONG_B does not help.
  - Within these model classes and data, act 1 therefore looks near its ceiling. The lower offline AUC is calibration-free, so it carries the NO_GO. Limits: the net used half the games and stopped at epoch 1, and both offline models trained on older policies.
- **Known bias (PREREG):** the offline models train on older policies (220-399) than the test (400-419). That works against them.
  - Their worse act-1 log loss together with similar AUC fits a calibration offset from this policy shift.
  - Adding LONG_B (at half the games, with online_cal refitted on other parts) did not help. Act-1 EV is 0.064 vs 0.063, and act-1 log loss is +0.045 vs +0.042 against each run's online_cal. That comparison is confounded.
- **Not pre-registered, descriptive:** in acts 3-4 the GBM ranks better than the online critic (AUC 0.833 vs 0.825 and 0.839 vs 0.817; EV 0.331 vs 0.315 and 0.318 vs 0.282). No CI was computed for these scopes. A late-act Φ is a separate question.
- For PPO, a better critic or a learned Φ (potential-based shaping) is not a lever for act 1 at this data scale. The remaining levers for act-1 credit assignment are more games per update and paired CRN continuations from act-1 decisions (option G of the plan doc). Both cost actor time.

## Decision

NO_GO for stage 1 (arm A with Φ = offline critic). The critic direction for act 1 is dropped. No default change.

## Cost

About 5.5 h of PC time (GPU about 19 min for the net fit; the rest CPU and file reading). No seeds, no cloud core-hours.
