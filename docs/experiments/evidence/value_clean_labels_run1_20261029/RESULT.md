# Clean value labels, run 1: result (2026-10-30)

Campaign: 1,280/1,280 units verified (`verify_campaign.py`: 0 BAD, 2 duplicate tars, run 7195d093), 44 workers,
2026-10-29 19:20Z to 2026-10-30 07:47Z. Raw tars: `/mnt/project-files/value-clean-labels-run1/units`. Extract
(`../value_clean_labels_20261029/tools/extract_a4.py`) `/mnt/project-files/value-clean-labels/run1/run1_a4.pkl`
(sha256 `2911d98bd3a9ea50…`). Python 3.13.17, numpy 2.5.3, xgboost 3.0.5, scikit-learn 1.9.1, scipy 1.18.1.

## V_A4 refit ([`fit_a4_run1.py`](fit_a4_run1.py), [`fit_result.json`](fit_result.json))
536 base games reached Act 4 (41.9%); each entry has 5 games (base + 4 forks), 65.7% Heart kills. Training: 2,337
stage-2 entries (1 outcome) + run-1 entries (5), TRAIN/VALIDATION by seed % 4; TEST = 130 run-1 entries
(650 games), scored per game.

| TEST (130 entries, 650 games) | BCE | AUC (entries, kill share ≥ 0.5) |
|---|---|---|
| constant | 0.668 | — |
| Act-4 CTM, raw | 0.594 | 0.798 |
| Act-4 CTM, recalibrated on TRAIN | 0.589 | 0.798 |
| G (GBM on the public entry record), 5 labels | 0.529 | 0.898 |
| GC (G + CTM logit), 5 labels — picked on VALIDATION | 0.532 | 0.882 |
| GC, base outcome only for run-1 entries | 0.543 | 0.872 |

- Gate (stage 2's): picked − CTM_recal = **−0.056 [−0.085, −0.028] → PASS** (stage 2: −0.004 [−0.028, +0.018]).
- 5 labels vs 1 per run-1 entry: −0.011 [−0.028, +0.005], not shown.
- Single-label TEST BCE (README plan, comparable with stage 2; [`explore_ctm_recal.py`](explore_ctm_recal.py), same
  GC model scored against the base game only): GC 0.507 vs CTM_recal 0.569, −0.062 [−0.106, −0.018].
- Label noise: within-entry variance of the 5 outcomes / p(1 − p) = **0.59**. 41% of the Act-4 outcome variance is
  explained by the entry state; that is the ceiling for any V_A4 at the entry.
- Deviation, disclosed: the first run had a bug in the comparator only (`np.repeat` paired the CTM logits with the
  wrong labels in the recalibration; CTM_recal BCE 0.672, AUC 0.20). The fix (one line, commit with this file) changes
  only the CTM_recal arm; the trained models and their TEST numbers are identical in both runs. TEST was therefore
  read twice for the comparator.
- Exploratory ([`explore_ctm_recal.py`](explore_ctm_recal.py)): recalibrating the CTM on run-1 entries only gives
  BCE 0.596, so the result is not a stale-calibration artefact.
- Why stage 2 failed and this passes is not settled: here TRAIN and TEST include games at today's default, and TEST
  labels are 5-game means (narrower CI). Stage 2's TEST was older-config games with one outcome each.

## Pilot capture ([`pilot_analysis.py`](pilot_analysis.py), [`pilot_result.json`](pilot_result.json))
32 games, 3,782 roots (acts 1-4), N = 64, top 3. Computed on the verified 1,280-unit extract (a first pass used 1,279). Act-end values scored with a provisional V_{k+1} (GBM on real
outcomes at act k+1's first state of the 1,248 non-pilot base games; act 4: base + forks).

| | act 1 | act 2 | act 3 | act 4 |
|---|---|---|---|---|
| rollout variance / p(1 − p) | 0.107 | 0.195 | 0.240 | 1 (game end) |
| sibling difference / independent | 0.042 | 0.077 | 0.093 | 0.215 |
| median label SE (64 rollouts) | 1.7 pp | 2.0 pp | 2.6 pp | 4.8 pp |
| death in act: rollouts (first root of the pilot games) / real (all base games) | 15% / 14% | 36% / 27% | 53% / 33% | 45% / 37% |

- Plan gate "label SE ≤ 2.5 pp in acts 1-2": met.
- 106 of 3,782 rows failed (act-boss map roots, `OOC MCTS actions requested at leaf`, as in stage 0); 264 end records
  name an unexpected act (0.05%), not yet explained.
- Coverage: act-4 entries reached by act-3 rollouts look like real ones in HP (median 91% vs 94% of max).
- CTM rollouts die too often from act 2 on (act 3: 53% vs 33%), so a per-act level calibration on real games is
  required (plan, uniform scheme). Whether the death gap also distorts the ranking is open.
