# Follow-up to §801: encounter lists against act-1 survival, and feature importance (pre-registration)

§801 ([RESULT](RESULT.md)) found that the act's remaining encounter lists add no Heart-kill EV to the critic ceiling
GBM (act 1 −0.0012 [−0.0022, −0.0002]). Philipp, 2026-11-15 19:35 CET, asked why only a GBM and whether a better
model should be trained. Proposed in the thread: (1) read the feature importance of the fitted models, (2) the same
comparison with a near target, act-1 survival. Philipp, 19:36 CET: "ja go mit den beiden sachen". Offline only: no
seeds, no games, no workers, no GPU.

## Question

Does the GBM see the encounter information at all? If the lists predict act-1 survival clearly, the information is
locally real and only washes out on the way to the Heart (then a stronger model or a short-horizon privileged critic
could be a separate question). If they do not predict even act-1 survival, the encounter-list direction is closed.

## Part 1: feature importance (descriptive)

`critic_ceiling.py importance` (total gain) on §801's `gbm_enc` and `gbm_run` (PC `~/critic-enc-out`) and on the two
new fits below: share of total gain on `enc_*` features, number of `enc_*` features used, the best `enc_*` feature's
rank, top features. No data is read; no decision rule.

## Part 2: act-1 survival target

- Target `--target act1_survive`: y = 1 if the game leaves act 1 alive (outcome act ≥ 2, or won). Only act-1 net
  decisions are kept, in training (first act-1 decision + 8 more act-1 decisions per game, seeded as before) and in
  the test.
- Amendment 2026-11-15 ≈ 20:15 CET, before any fit completed (review K N3; the first launch at 9b12a846 stopped
  while loading the training data with `KeyError: 'act'`): a stalled game's line (`ppo_cloud.stalled_game_lines`)
  has only `floor`, `heart_kill`, `stalled`. Its y is 1 iff the stall floor is ≥ 17 (past act 1's boss, as
  `ppo_train.ACT_FLOORS`), so an act-1 stall counts as y = 0. Such games carry no decisions, so they enter no
  training or test row; one exists in the training parts (`traj-0361-p37`). Act-1 decisions after the act-1 boss
  are almost surely y = 1 (review K N2); they stay in, as for the Heart target.
- Importance (review K N1): `importance` sums xgboost's total gain over all trees of the saved model, including the
  ≤ 100 early-stopping rounds after the best iteration; the RESULT states this.
- Data, split, table and settings as §801 (LONG_C 0220-0399 train, 0400-0419 test, `--game-frac 1.0`, table sha256
  `21e81001…c7ad63`, GBM depth 6, eta 0.05, ≤ 3,000 rounds, min-count 20). RAM fallback as §801 (both fits at 0.5).
- Estimators: online, online_cal (the logged Heart value Platt-recalibrated to act-1 survival on the training parts),
  gbm (public), gbm_enc (`--enc-scope act`). No gbm_run (later acts cannot change act-1 survival).
- Contrasts gbm_enc − gbm and gbm_enc − online_cal (paired game-cluster bootstrap, 2,000 resamples, seed 20261106,
  95% CIs) on the first decision and on act-1 (= all) decisions.

## Decision rule (fixed before any score is read)

`evaluate --target act1_survive --rule encounters --enc-ev-margin 0.03`, the same rule as §801 on the new target:
**LOCAL_SIGNAL** (the verdict's GO) if EV(gbm_enc) − EV(gbm) ≥ +0.03 with its 95% CI above 0 and EV(gbm_enc) −
EV(online_cal) with its 95% CI above 0, on act-1 decisions. Otherwise **NONE** (the verdict's NO_GO).

- LOCAL_SIGNAL: the lists carry act-1 information that does not reach the Heart outcome. Any follow-up (a net with
  encounter inputs, or a privileged critic for a short-horizon target) is a separate proposal for Philipp.
- NONE: the encounter lists do not even predict act-1 survival beyond the public state; #1050's encounter-list
  direction is closed.

Known limit, as §801: one model class. A LOCAL_SIGNAL does not reopen #1050 step 1 by itself: §801's Heart-kill
result stands. While writing the target code, the outcome fields of one LONG_C test part (iteration 419, p0, 13
games) were printed to confirm their meaning (`act`, `won`, `heart_kill`); no score was computed.

## Cost

PC CPU only (nice 10, 4 threads): two fits of about 10 min, one evaluate on act-1 decisions (~515k) of about
15-25 min, importance in seconds. No GPU, no seeds, no cloud core-hours.
