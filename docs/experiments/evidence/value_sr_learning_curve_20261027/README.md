# SR head data learning curve (2026-10-27)

Offline, no game seeds. [PLAN.md](PLAN.md) is the plan as written before any run: a frozen copy of
`gen2/value-sr-lc/PLAN.md` on the data branch `claude/az-gen2-data` (written at `84de5cb`/`8d40c5d`, unchanged since;
sha256 `05641c15…`).
- Philipp approved the check on 2026-10-26 at 23:32Z and asked for the start at 10:00 CET on 2026-10-27.
- Training ran on Philipp's GPU from 12:08Z until shortly before 19:21Z, two runs side by side
  (`tools/drive_lc.sh` at `e56101c`, run from the PC's clean clone of the data branch). Results were pushed to the data
  branch as `5d7a2ec` (main runs) and `0d84e2c` (split runs). Evaluation ran in the cloud.

## Question
The best sibling-ranking (SR) heads rank the common-seed VALIDATION siblings at about X2-B's level: 0.663 and 0.667
for SR_crn_r2 seeds 1 and 2 (§649), against 0.664 for X2-B. Would more training data lift them? An earlier estimate
put the data a head needs to resolve 1 pp differences at 100k–1M games. That was a guess, so this run measures the
learning curve instead.

## Setup
- **100 %** is the existing SR_crn_r2_s1 and _s2 (§649). They were not re-run. Their data are 2,016 training row files
  (one AZ run each, 350,256 rows, value targets z and teacher_v) and 19,781 sibling-ranking groups from 1,151 training
  sources.
- **Subsets** ([tools/lc_subset.py](tools/lc_subset.py)): a training source is kept when
  int(sha256("lc:<seed>")) % 4 < K. The subsets are nested and apply jointly to row files and ranking groups.
  Validation, selection-fold and ranking-holdout data are always kept.

  | fraction | row files | rows | ranking groups |
  |---|---|---|---|
  | 25 % (K = 1) | 463 (23.0 %) | 81,227 (23.2 %) | 5,074 (25.7 %) |
  | 50 % (K = 2) | 992 (49.2 %) | 172,358 (49.2 %) | 10,457 (52.9 %) |
  | 100 % | 2,016 | 350,256 | 19,781 |
- **Matched optimizer steps:** 80 epochs at 25 % and 40 at 50 %, against 20 at 100 %. The one-cycle schedule and the
  ranking stream therefore span about the same number of steps. Because the row shares are slightly below 25 % and
  50 %, the step counts fall about 7 % and 2 % short. Everything else is SR_crn_r2_s1/s2's command, with
  `distill.py` unchanged (`40a9d5a3…`) and torch seeds 1 and 2 ([tools/run_lc.sh](tools/run_lc.sh)).
- **Split runs (secondary, seed 1):**
  - LC25rows_s1: 25 % of the rows, all groups, 80 epochs.
  - LC25groups_s1: all rows, 25 % of the groups, 20 epochs.
- **Epoch choice:** `pick_epoch.py` of §649 is unchanged. It takes the best in-training holdout ranking among the
  epochs with selection-fold value BCE ≤ 0.570.
- **Metric** ([tools/lc_eval.py](tools/lc_eval.py)): the head alone on the common-seed VALIDATION (80 sources,
  5,587 groups), §577 concordance as in `crn_eval.py`. Seeds are averaged per source, and differences use a paired
  source bootstrap (2,000 resamples). The same file reports concordance on pairs with a label gap below 1.5 pp, and
  the X2-B blend with w chosen on the TRAIN holdout.
- **Check:** the cloud scoring reproduces §649's numbers exactly (0.6628 and 0.6668, X2-B 0.6639;
  [results/crn_eval_base.txt](results/crn_eval_base.txt)).
- STS_ACTIVE_POWER_FEATURES is a combat-net flag (`CombatValueNet.cpp`) that the heart1 OOC student never reads. It was
  unset, as in §645/§649, and each train.log records that.

## Results
**Learning curve** ([results/lc_main.txt](results/lc_main.txt), [results/lc_main.json](results/lc_main.json)):

| data | head alone (s1, s2) | mean | − X2-B | gap < 1.5 pp | blend |
|---|---|---|---|---|---|
| 25 % | 0.628, 0.647 | 0.638 | −0.026 [−0.038, −0.015] | 0.577 | 0.685 |
| 50 % | 0.659, 0.664 | 0.662 | −0.002 [−0.015, +0.011] | 0.595 | 0.698 |
| 100 % | 0.663, 0.667 | 0.665 | +0.001 [−0.013, +0.015] | 0.594 | 0.703 |
| X2-B | | 0.664 | | 0.646 | |

- 25 % → 50 %: +0.024 [+0.018, +0.030].
- **50 % → 100 %: +0.003 [−0.003, +0.009]. Verdict FLAT** by the plan's rule (CI includes 0, |d| < 0.005).
  - Gap < 1.5 pp: −0.000 [−0.007, +0.006].
  - Blend: +0.005 [−0.001, +0.009].
- The plan's log-linear slope, +0.014 per doubling, averages a steep step and a flat one. The curve is concave, so
  that slope is not a usable extrapolation.

**Which data matter** ([results/lc_split.txt](results/lc_split.txt),
[results/lc_split_rows.json](results/lc_split_rows.json); one seed each, compared with SR_crn_r2_s1 at 0.663):

| run | head alone | − 100 % (s1) | blend |
|---|---|---|---|
| 25 % rows, all groups | 0.666 | +0.004 [−0.002, +0.009] | 0.701 |
| all rows, 25 % groups | 0.649 | −0.014 [−0.021, −0.007] | 0.690 |

(`lc_split.txt` labels the two runs 0.25 and 0.26 only so that lc_eval.py keeps them apart. Its "slope" lines are
meaningless for this pair.)

**Training curves** (in-training holdout of 3,806 groups, [results/runs/](results/runs/)):

| run | chosen epoch: holdout / BCE | best holdout of any epoch / its BCE | epochs with BCE ≤ 0.570 |
|---|---|---|---|
| LC25_s1 | 17: 0.621 / 0.568 | 64: 0.663 / 0.599 | 6 of 80 |
| LC25_s2 | 39: 0.645 / 0.569 | 75: 0.656 / 0.598 | 8 of 80 |
| LC50_s1 | 27: 0.659 / 0.570 | 30: 0.660 / 0.575 | 24 of 40 |
| LC50_s2 | 29: 0.658 / 0.568 | 29 (same) | 19 of 40 |
| SR_crn_r2_s1 (100 %) | 13: 0.667 / 0.565 | 13 (same) | |
| SR_crn_r2_s2 (100 %) | 20: 0.669 / 0.562 | 20 (same) | |
| LC25rows_s1 | 49: 0.664 / 0.567 | 56: 0.671 / 0.590 | 21 of 80 |
| LC25groups_s1 | 12: 0.651 / 0.568 | 20: 0.653 / 0.576 | 7 of 20 |

## Interpretation
- **More of the same data does not lift this head.** Doubling from 50 % to 100 % gains +0.003, with a CI that reaches
  +0.009 at most. Even at the upper end, the head would need about 3 more doublings (≈ 10× today's data) to gain
  +0.03. At the point estimate it would need about 9 (≈ 500×). On close pairs (gap < 1.5 pp), the ones a 1 pp
  decision needs, the gain is zero, and every head stays well below X2-B there (0.594 against 0.646).
- **Game outcome rows are not what limits the ranking.** With a quarter of the rows and all the ranking groups, the
  head ranks as well as with everything (+0.004 [−0.002, +0.009]). Rows matter only through the value BCE bar. With
  fewer rows the value head overfits sooner (BCE rises above 0.570). That forces the pick to an early epoch, which is
  why the 25 % joint runs land at 0.638. Their best unconstrained epochs reach a holdout ranking of 0.656–0.663, near
  the 100 % runs.
- **Ranking groups matter, but with diminishing returns.** Cutting the groups to 25 % costs −0.014. The joint
  50 % → 100 % step also doubles the groups, yet gains only +0.003. So the groups curve flattens too, somewhere
  around 10k groups.
- **Implication for generating more data.** The 100k–1M game estimate assumed outcome labels were the bottleneck.
  For this head they are not. More policy-only games would add rows that this head does not use, and more capture
  groups of the same kind are flattening. So the plateau near X2-B's level comes from the labels' kind (rollout3
  means that end in X2-B), the features, or the recipe, not from the amount of data. This is consistent with §645 and
  §649, where cleaner and three times as many groups barely moved the selected heads.
- Caveats:
  - Two seeds per fraction and one seed per split run. Retraining noise between seeds is 0.004 at 100 % and 0.018
    at 25 %.
  - The subsets cut sources, so they keep the same mix of decisions per game. A different kind of data (other
    labels, other screens) is not tested here.

## Decision
- No default change and no data generation proposed. FLAT is a negative result for the ledger.
- If the value head is pursued further, the next lever is the labels or the recipe, not volume. Candidates:
  - labels that do not end in X2-B, or luck-corrected outcome labels (the AIVAT direction, §697/§698);
  - a ranking-first selection that does not let the value BCE bar cut training short.

## Reproduce
```
# PC (Philipp's GPU), in a clone of claude/az-gen2-data at e56101c or later:
gen2/value-sr-lc/tools/drive_lc.sh        # smoke, main (PAR=2), split; exports pick_epoch's epoch and pushes
# cloud: EXT = verify_campaign.py --extract of the §644 capture, CRN = crn_analyze.py rows EXT CRN,
# ONE_COMBAT built from main 9a37d78, weights from the data branch (gen2/value-sr-lc/weights, gen2/value-sr-crn/weights)
STS_REPO=$REPO python3 tools/lc_eval.py $ONE_COMBAT $CRN lc_main.json 0.25:LC25_s1=LC25_s1_ep17.bin \
  0.25:LC25_s2=LC25_s2_ep39.bin 0.5:LC50_s1=LC50_s1_ep27.bin 0.5:LC50_s2=LC50_s2_ep29.bin \
  1.0:SR_crn_r2_s1_ep13=SR_crn_r2_s1_ep13.bin 1.0:SR_crn_r2_s2_ep20=SR_crn_r2_s2_ep20.bin
STS_REPO=$REPO python3 tools/lc_eval.py $ONE_COMBAT $CRN lc_split_rows.json 0.25:LC25rows_s1=LC25rows_s1_ep49.bin \
  1.0:SR_crn_r2_s1_ep13=SR_crn_r2_s1_ep13.bin
```
- The weights' sha256 values are in [results/weights.sha256](results/weights.sha256). Training logs and summaries are
  on the data branch under `gen2/value-sr-lc/runs/`.
