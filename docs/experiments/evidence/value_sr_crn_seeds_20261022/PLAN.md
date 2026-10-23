# Ranking-selected SR head: seeds 1 and 2 (plan, 2026-10-22)

Written before any run of this round. Offline only. Philipp typed "merge 816 and go seeds" (2026-10-22 20:52Z) after
§645 was merged.

## Question
§645's exploratory head is SR_crn_r2 seed 0 at epoch 11, the epoch with its best in-training holdout ranking.
- On the common-seed VALIDATION, it is level with X2-B alone (0.660 vs 0.664).
- Its blend beats SR_w1's blend by +0.014 [+0.009, +0.019].
- But its epoch was chosen after the run.

Does the recipe "SR_crn_r2's training, with the epoch chosen by the holdout ranking" give the same result on fresh
seeds, with the rule fixed in advance?

## Runs (`tools/run_sr_crn.sh seeds`)
- **SR_crn_r2_s1 and SR_crn_r2_s2** use SR_crn_r2's command exactly (§645), with `--seed 1` or `--seed 2` and
  `--patience 0`.
  - `--patience 0` runs all 20 epochs instead of stopping on the value objective.
  - The one-cycle learning-rate schedule still spans `--epochs 20`, so epochs 1–11 follow seed 0's schedule.
  - `--save-epochs` keeps every epoch.
- **Data:** the same as SR_crn_r2, the concatenated `crn_r2_train_groups.jsonl.gz` (sha256 `3f78ae0c…`; 19,781
  training groups, and the mixed holdout of 3,806 groups from 176 sources).
- **Where:** Philipp's GPU, about 90 min per seed. The two seeds run one after the other, or side by side if the PC
  has the cores for it. The result does not depend on that choice.

## Epoch choice (fixed now; `tools/pick_epoch.py`)
- **Primary:** the epoch with the highest in-training holdout ranking (the "sr_holdout" concordance in summary.json)
  among the epochs whose selection-fold value BCE is at most **0.570**. Ties go to the earliest epoch.
  - The BCE cap replaces #812's bar of 0.552 for this round.
    - The candidate here is the blend, with w ≤ 0.30, not the head alone.
    - 0.570 still keeps most of the head's outcome information: the constant predictor scores 0.642, and SR_w1 scores
      0.547.
    - Seed 0's epoch 11 (0.557) passes the cap, and the rule picks it on seed 0's curve.
- **Secondary ("value stop"):** the same choice, but only among the epochs that a patience-3 stop on the selection
  objective would have run, as in seed 0's run.
  - That is the procedure that produced epoch 11.
  - It separates "select on ranking" from "train longer".
- Each seed exports the primary epoch, the secondary epoch if it differs, and the run's own fold-selected
  `student.pt`. They go under `weights/` as before.

## Evaluation (cloud; `docs/experiments/evidence/value_sr_crn_20261022/tools/eval_runs.sh`, as in §645)
- **Primary metric, per seed:** the blend sigmoid((1 − w)·logit X2-B + w·logit head) minus SR_w1 seed 0's blend.
  - It is measured on the common-seed VALIDATION (seed % 4 == 3), with a paired source bootstrap.
  - Each blend's w is chosen on the common-seed TRAIN holdout (seed % 8 == 6), from {0.05, …, 0.30}. SR_w1's is 0.10.
  - SR_w1 seed 0's blend is the current online candidate (the parked A/B).
- **Bar:** "−3 HP sign" ≥ 85 % in the prices check, for the primary epoch's head.
- **Secondary:**
  - the head alone against X2-B and against SR_w1;
  - round-2 VALIDATION (head, blend, minus SR_w1), §494's siblings, and outcome AUC;
  - the value-stop epochs;
  - the per-epoch ranking and BCE curves;
  - for context, SR_w1 seeds 1–2's blends on the common-seed VALIDATION (§644: +0.019 and +0.018 over X2-B, against
    +0.026 for seed 0).

## Verdict
- **REPLICATED:** both seeds have the primary metric's CI above 0, and both meet the bar.
  - Then the ranking-selected recipe replaces SR_w1 as the online candidate.
  - Among seeds 0 (epoch 11), 1 and 2, the head is the one with the best blend on the TRAIN holdout.
  - Any online A/B still needs Philipp's go and worker count.
- **PARTIAL:** exactly one seed does. SR_w1 stays the candidate. The result is recorded as mixed.
- **NOT_REPLICATED:** neither seed does. SR_w1 stays the candidate. This is a negative result for the ledger.

## Cost
Two runs of about 90 min on Philipp's GPU and about 1 h of cloud evaluation. No game seeds are used.
