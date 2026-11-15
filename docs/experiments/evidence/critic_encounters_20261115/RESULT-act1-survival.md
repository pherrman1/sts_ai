# Follow-up to §801: encounter lists against act-1 survival, and feature importance (RESULT)

Pre-registration: [PREREG-act1-survival.md](PREREG-act1-survival.md) (review K PASS on 9b12a846, delta PASS
9b12a846..923a22fe). Philipp's go: 2026-11-15 19:36 CET. Run on the PC (CPU only, nice 10) 20:09-20:54 CET at
`923a22fe`; offline, no seeds, no games, no GPU. Raw records (refs `ppo-xfer/critic-enc-act1` = `9e33efb0`,
`ppo-xfer/critic-enc-act1-imp` = `dc6dc54d`) in [act1_survival/](act1_survival/): `report.json`, `gbm.json`,
`gbm_enc.json`, `importance.json`, `importance_801_gbm_enc.json`, `commands.log`, `run.stdout`, `run2.sh`,
`failed-9b12a846/`.

## Deviations

1. The first launch at 9b12a846 stopped while loading the training data (`KeyError: 'act'` on the one stalled-game
   line, `traj-0361-p37`) before any model existed. Fixed in 923a22fe with the PREREG amendment; K delta PASS.
2. The `--game-frac 1.0` fit was killed by the RAM guard (MemAvailable 3,892 MB < 4,096 MB at 20:15 CET) while the
   #1053 rollout-prior grid ran its 7.9 GB fit on the same PC. As pre-registered, both fits ran at **0.5**
   (400,491 train / 21,024 val rows each).
3. `importance` keyed its output by file name, so §801's `gbm.json` / `gbm_enc.json` (Heart target) were overwritten
   in `importance.json` by the act-1 models of the same names (`gbm_run.json` is §801's). §801's `gbm_enc` was rerun
   alone (`importance_801_gbm_enc.json`, input sha256 `27a75831…` = the §801 file). The tool now keys by path
   (after this run; no result depends on it).
4. Importance is xgboost total gain over every tree of the saved model, including the ≤ 100 early-stopping rounds
   past the best iteration (review K N1).

## Part 1: feature importance (descriptive)

| Model (target) | enc_* share of total gain | enc_* features used | best enc_* rank |
| --- | --- | --- | --- |
| §801 gbm_enc (Heart) | 2.2% | 295 / 319 | 91 |
| §801 gbm_run (Heart) | 9.8% | 466 / 493 | 56 |
| gbm_enc (act-1 survival) | 13.9% | 121 / 121 | 21 |

The GBM does use the encounter features (all scopes), most on the act-1 target. On the Heart target that use buys no
EV (§801), so gain share here is fitting effort, not predictive value.

## Part 2: act-1 survival (act-1 decisions of the 10,400 test games; act-1 survival 81.3% of decisions)

| Estimator | First decision AUC / EV | Act-1 AUC / EV | Act-1 log loss |
| --- | --- | --- | --- |
| online_cal | 0.501 / −0.002 | 0.660 / 0.047 | 0.4597 |
| gbm | 0.542 / 0.004 | 0.768 / 0.145 | 0.4062 |
| gbm_enc | 0.557 / 0.0085 | 0.772 / 0.150 | 0.4038 |

| Contrast (95% CI) | First decision Δ EV | Act-1 Δ EV | Act-1 Δ log loss |
| --- | --- | --- | --- |
| gbm_enc − gbm | +0.0048 [+0.0021, +0.0075] | **+0.0053 [+0.0024, +0.0080]** | −0.0024 [−0.0036, −0.0012] |
| gbm_enc − online_cal | +0.0102 [+0.0060, +0.0147] | +0.1029 [+0.0933, +0.1123] | −0.0559 [−0.0611, −0.0505] |

Rule checks: gain over gbm ≥ +0.03: **no**; its CI above 0: yes; gain over online_cal CI above 0: yes →
**NONE** (the verdict's NO_GO).

## Interpretation

- The encounter lists carry real but small information even for the near target: knowing the act's remaining
  normals and elites adds +0.005 EV to act-1 survival (0.145 → 0.150, AUC 0.768 → 0.772), about 4% of what the
  public state already explains and a sixth of the pre-registered bar. Diluted over acts 2-4, that matches §801's
  zero on the Heart.
- **Inference:** a better model class is unlikely to change the conclusion. The GBM visibly uses the features
  (13.9% of gain, rank 21) and finds a small effect with a tight CI, so the information content, not the model,
  limits the gain. A net could exploit encounter × deck interactions better, but would have to find ~6× more signal
  than the GBM on the near target to reach the bar there, and more than that for the Heart.
  Caveat (review K W2): these act-1 fits used half the training games (RAM fallback), §801's Heart fits all of
  them, so the importance shares and the +0.005 come from different data sizes; more data could raise the act-1
  gain somewhat, but not by the factor needed.
- The online PPO critic ranks act-1 survival far worse than the public GBM (AUC 0.660 vs 0.768). It is trained on
  the Heart outcome, not on survival, so this is a different target and not a defect by itself (**descriptive**).

## Decision

NONE: the encounter lists do not predict act-1 survival beyond the public state by the pre-registered margin. The
encounter-list direction of #1050 is closed (step 1, step 2 via a privileged critic, and a net variant). No default
change.

## Cost

About 45 min PC CPU (fits 18 min at 0.5, evaluate 21 min, importance seconds) plus 14 min in the aborted first
launch; no GPU, no seeds, no cloud core-hours.
