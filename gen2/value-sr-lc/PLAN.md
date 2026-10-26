# SR head data learning curve (plan, 2026-10-27)

Written before any run. Offline only, no game seeds. Philipp approved the check on 2026-10-26 23:32Z ("Yes ask
coordinator for that", answering the proposal "Train the SR head on 25%, 50% and 100% of the existing data and plot
sibling ranking against data size").

## Question
The best sibling-ranking (SR) heads rank the common-seed VALIDATION siblings at about X2-B's level, 0.660-0.667
(§645, §649; X2-B 0.664). Is that level limited by the amount of training data? If the ranking still climbs from 50 %
to 100 % of the data, more data pays and the slope says how much; if it is flat, the limit is the labels, the features
or the recipe.

## Baseline (100 %, already run, not re-run)
SR_crn_r2_s1 and SR_crn_r2_s2 (§649, `../value-sr-crn/tools/run_sr_crn.sh seeds`): SR_crn_r2's command with
`--seed 1/2 --patience 0`, 20 epochs, `--save-epochs`. Training data:
- 2,016 training row files of `~/h1distill/gen2/vdistill/rows_T1` (one AZ run each, 350,256 rows; value targets z and
  teacher_v);
- 19,781 sibling-ranking groups from 1,151 training sources (common-seed TRAIN 12,327 groups / 200 sources, round-2
  TRAIN 7,454 / 951), `crn_r2_train_groups.jsonl.gz` sha256 `3f78ae0c…`.
These are the gen-2 data the recipe uses. The gen-3 rows (§643) carry no `teacher_v` and are not part of this recipe,
so they are not used.

## Runs (`tools/run_lc.sh main`, Philipp's GPU)
- **Subsets** (`tools/lc_subset.py`): a training source is kept when int(sha256("lc:<seed>")) % 4 < K, K = 1 (25 %) or
  2 (50 %). The 25 % subset lies inside the 50 % one. Applied jointly to the training row files and the training
  ranking groups. Validation files (seed % 8 == 7), selection-fold files (% 8 == 6) and the in-training ranking
  holdout (group seed % 8 == 6) are always kept, so every run is scored on the same sets. Expected groups: 5,074
  (25.7 %) and 10,457 (52.9 %); the row counts are logged.
- **Matched optimizer steps:** `--epochs 80` at 25 % and `--epochs 40` at 50 % (20 × 4 / K), so the one-cycle
  schedule and the ranking stream span the same number of steps as the 100 % runs. Everything else is SR_crn_r2_s1/s2's
  command exactly (`--patience 0 --save-epochs`, torch seeds 1 and 2).
- **Primary:** LC25_s1, LC25_s2, LC50_s1, LC50_s2.
- **Secondary, after the primary (same GPU queue):** LC25rows_s1 (rows 25 %, all groups, 80 epochs) and LC25groups_s1
  (all rows, groups 25 %, 20 epochs), to tell which data axis carries the slope.
- STS_ACTIVE_POWER_FEATURES is a combat-net flag that the heart1 OOC student does not read; it is left as in §645/§649
  and its value is logged in each train.log.

## Epoch choice (fixed now)
`../value-sr-crn/tools/pick_epoch.py` unchanged: highest in-training holdout ranking among epochs with selection-fold
value BCE ≤ 0.570, ties to the earliest. For the 100 % runs that is s1 epoch 13 and s2 epoch 20 (§649). If no epoch
passes the bar, the run's best-ranking epoch is used and flagged.

## Evaluation (cloud, `tools/lc_eval.py`)
- **Primary metric:** the chosen head alone on the common-seed VALIDATION (seed % 4 == 3, 80 sources), §577
  concordance, as in `crn_eval.py`; per data fraction the mean of seeds 1 and 2.
- **Slope:** c(100 %) − c(50 %) and c(50 %) − c(25 %), each the seed mean, with a paired source bootstrap over the
  VALIDATION sources (2,000 resamples; both seeds' rows resampled together).
- **Secondary:** the blend with X2-B (w chosen on the TRAIN holdout as in crn_eval.py); in-training holdout curves
  against steps (where each fraction peaks, train_first1000 memorisation); concordance on VALIDATION pairs whose label
  gap is below 1.5 pp; outcome BCE/AUC on the selection fold.

## Verdict per doubling 50 % → 100 %
- **CLIMBING:** c(100) − c(50) ≥ +0.005 with the CI above 0. More data pays. Fit c = a + b·log2(data) on the three
  fractions and report the projected head-alone concordance at 2×, 4×, 10× and 40× today's data, and the data multiple
  at which the head would gain +0.03 over X2-B, with the caveat that a log-linear fit is an assumption.
- **FLAT:** the CI includes 0 and |c(100) − c(50)| < 0.005. The amount of data is not the bottleneck for this recipe;
  a negative result for the ledger.
- **INCONCLUSIVE:** anything else (e.g. a positive point estimate with a CI that includes 0).

## Cost
Each run has the 100 % runs' step count, about 75-110 min on the GPU (more epochs means more per-epoch evaluation).
Four primary runs, two side by side if the GPU is free: about 4 h; the two secondary runs about 2 h more. Cloud
evaluation about 1 h. No game seeds.
