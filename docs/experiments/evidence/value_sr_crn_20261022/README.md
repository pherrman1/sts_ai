# Sibling-ranking loss on the common-seed labels (2026-10-22)

Exploratory and offline. [PLAN.md](PLAN.md) is the plan as it was written before any run. It is a frozen copy of
`gen2/value-sr-crn/PLAN.md` on the data branch `claude/az-gen2-data` at `a8ab7da` (sha256 `dc80511c…`).
- Philipp typed "go gpu" on 2026-10-22 at 17:50Z, after the common-seed recapture result (§644).
- Training ran on Philipp's GPU from 18:03Z to 19:31Z. Evaluation ran in the cloud.

## Question
On the common-seed VALIDATION (80 sources, 5,587 groups), the SR_w1 head alone (§641) ranks siblings below X2-B:
0.645 against 0.664. Its blend with X2-B still gains +0.026.

SR_w1 learned its ranking from round-2 TRAIN: 8,458 groups, every 8th root, 64 independent repeats. Does the same
recipe do better on the recapture's labels? Those come from every root, and their sibling differences carry 0.36 of
round 2's stream variance per repeat (§644).

## Setup
- **Ranking data:**
  - `crn_train_groups.jsonl.gz` (sha256 `dc5b67e0…`): the recapture's TRAIN split (seed % 4 != 3), made by
    `gen2/value-sr-crn/tools/crn_groups.py`.
    - 15,129 groups from 240 sources, with at most 8 rows per action.
    - Each target is the mean of the 32 common-seed rollout3 values.
  - Round-2 TRAIN as in §641 (`r2_train_groups.jsonl.gz`, 8,458 groups).
  - **Holdout:** groups whose source seed % 8 == 6 are never trained on. The two VALIDATION splits are never read by
    training.
- **Arms:** both use SR_w1's recipe exactly (§641; seed 0, `--sr-weight 1`). Only the ranking data change.
  - **SR_crn:** the common-seed TRAIN groups.
  - **SR_crn_r2:** those plus round-2 TRAIN (23,587 groups).
    - `run_sr_crn.sh` concatenates the two files into `crn_r2_train_groups.jsonl.gz`. SR_crn_r2's training log
      records that file's sha256, `3f78ae0c…`.
    - `cat crn_train_groups.jsonl.gz r2_train_groups.jsonl.gz` reproduces that hash.
  - Code: `gen2/value-sr-crn/tools/distill.py` (sha256 `40a9d5a3…`; #812's copy plus `--save-epochs`) and
    `run_sr_crn.sh` (`9b9be1cf…`).
- **Selection:** the fold objective with patience 3, as for SR_w1.
  - `--save-epochs` keeps every epoch.
  - When the epoch with the best in-training holdout ranking is not the selected one, it is exported too and labelled
    exploratory.
- **Evaluation:** [tools/eval_runs.sh](tools/eval_runs.sh) runs three steps per head.
  - The prices check, as in #812.
  - [tools/crn_eval.py](tools/crn_eval.py) on the common-seed capture. It reports the §577 concordance and paired
    source bootstraps against X2-B and against SR_w1.
    - It also chooses each head's blend weight w on the TRAIN holdout, from 0.05 to 0.30.
    - It then compares the blend on VALIDATION with SR_w1's blend, whose w was chosen the same way.
  - #812's `sr_eval.py` on round 2, with SR_w1 as the control.
- **Gate** (per arm: the head alone on the common-seed VALIDATION, with the bars met):
  - PASS at ≥ X2-B (0.664).
  - IMPROVED above SR_w1, with the paired CI above 0.
  - FAIL otherwise.
  - Bars: selection-fold value BCE ≤ 0.552, and "−3 HP sign" ≥ 85 %.

## Results
**Training and bars** ([results/train_summaries.json](results/train_summaries.json),
[results/prices_srcrn.txt](results/prices_srcrn.txt), [results/prices_srcrnr2.txt](results/prices_srcrnr2.txt), and the
training logs [results/train_SR_crn.log](results/train_SR_crn.log) and
[results/train_SR_crn_r2.log](results/train_SR_crn_r2.log), copied from the data branch):

| head | selected / run epochs | selection-fold value BCE (≤ 0.552) | holdout ranking in training | −3 HP sign (≥ 85 %) | gold +50 valued higher | max HP +5 valued higher |
|---|---|---|---|---|---|---|
| SR_w1 (control, §641) | 7 / 10 | 0.547 | – | 88.1 % | 65.4 % | 54.0 % |
| SR_crn | 5 / 8 | **0.556** | 0.644 | 87.9 % | 82.8 % | 63.7 % |
| SR_crn_r2 | 8 / 11 | 0.543 | 0.646 | 90.1 % | 86.8 % | 54.9 % |
| SR_crn epoch 8 (exploratory) | – | **0.587** | 0.657 | 85.7 % | 84.6 % | 67.0 % |
| SR_crn_r2 epoch 11 (exploratory) | – | **0.557** | 0.656 | 88.2 % | 84.4 % | 55.5 % |

- The training holdouts differ.
  - SR_crn's has 2,802 common-seed groups from 40 sources.
  - SR_crn_r2's adds round 2's 1,004 groups, for 3,806 groups from 176 sources.
  - So the "holdout ranking in training" column is not on the same set for the two runs.
- The exploratory epochs' BCE comes from the training logs.
  - In the logs, an epoch's "sibling-rank holdout" line comes just before its "ep N" line.
  - Its "select fold" line, which holds the value BCE, comes just after.
- **Both runs were stopped while the holdout ranking still rose.**
  - SR_crn: 0.521 at the start, 0.644 at the selected epoch 5, 0.657 at epoch 8.
  - SR_crn_r2: 0.515, 0.646 at the selected epoch 8, and 0.656 at epoch 11.
  - The value objective stopped both runs: past their selected epochs, the selection-fold BCE got worse.

**Sibling concordance** (common-seed VALIDATION, where X2-B scores 0.664; round-2 VALIDATION, where it scores 0.633;
[results/crn_eval_srcrn.txt](results/crn_eval_srcrn.txt), [results/crn_eval_srcrnr2.txt](results/crn_eval_srcrnr2.txt),
[results/sr_eval_srcrn.txt](results/sr_eval_srcrn.txt), [results/sr_eval_srcrnr2.txt](results/sr_eval_srcrnr2.txt)):

| head | VALIDATION | − X2-B | − SR_w1 | blend w | blend | blend − X2-B | blend − SR_w1's blend | round 2 | round-2 blend |
|---|---|---|---|---|---|---|---|---|---|
| SR_w1 (control) | 0.645 | −0.019 [−0.031, −0.008] | – | 0.10 | 0.689 | +0.025 [+0.019, +0.031] | – | 0.644 | 0.673 (w 0.05) |
| SR_crn | 0.640 | −0.024 [−0.036, −0.012] | −0.005 [−0.012, +0.002] | 0.15 | 0.688 | +0.024 [+0.017, +0.031] | −0.001 [−0.007, +0.004] | 0.610 | 0.664 (w 0.10) |
| SR_crn_r2 | 0.649 | −0.015 [−0.027, −0.003] | +0.004 [−0.002, +0.010] | 0.20 | 0.690 | +0.026 [+0.017, +0.034] | +0.001 [−0.004, +0.007] | 0.639 | 0.669 (w 0.05) |
| SR_crn epoch 8 (exploratory) | 0.650 | −0.014 [−0.026, −0.001] | +0.005 [−0.001, +0.013] | 0.15 | 0.692 | +0.028 [+0.019, +0.036] | +0.003 [−0.003, +0.009] | 0.624 | 0.666 (w 0.05) |
| SR_crn_r2 epoch 11 (exploratory) | 0.660 | −0.004 [−0.017, +0.009] | +0.015 [+0.009, +0.022] | 0.10 | 0.703 | +0.039 [+0.031, +0.046] | +0.014 [+0.009, +0.019] | 0.648 | 0.678 (w 0.10) |

- **Gate:**
  - SR_crn **FAIL**: it is level with SR_w1, and it misses the BCE bar.
  - SR_crn_r2 **FAIL**: it is +0.004 over SR_w1, with the CI including 0.
- **Round 2:**
  - The heads trained only on common-seed labels lose there: SR_crn scores 0.610, against SR_w1's 0.644.
  - SR_crn_r2 is level with SR_w1, −0.005 [−0.013, +0.003].
  - Epoch 11 is level with SR_w1, +0.004 [−0.005, +0.013], and its blend is the best on round 2 (0.678).
- **Outcome AUC on round-2 VALIDATION** is 0.671–0.675 for every head (X2-B 0.683).
- On §494's siblings, epoch 11's blend scores 0.642, against 0.631 for SR_w1's blend and 0.601 for X2-B.

## Interpretation
- **Cleaner and more labels did not lift the selected heads.**
  - SR_crn's ranking data are cleaner than SR_w1's, and SR_crn_r2 has nearly three times as many groups.
  - Yet on the common-seed VALIDATION both are level with SR_w1, and both stay below X2-B.
  - So label noise was not what held the head back at the selected epochs.
- **The selection rule held them back.**
  - The value objective stops training while the ranking still improves.
  - The ranking-selected epochs carry that gain to VALIDATION, which no choice here read:
    - +0.010 for SR_crn (epoch 8 vs 5);
    - +0.011 for SR_crn_r2 (epoch 11 vs 8).
  - This is §641's lesson (select on value and ranking) in a stronger form.
- **SR_crn_r2's epoch 11 is the best evaluator so far, but it is exploratory.**
  - Alone, it is level with X2-B (0.660 vs 0.664) and +0.015 [+0.009, +0.022] over SR_w1.
  - Its blend scores 0.703, +0.039 over X2-B and +0.014 [+0.009, +0.019] over SR_w1's blend.
  - It costs a little calibration: selection-fold BCE 0.557, against a bar of 0.552.
  - Its monotonicity is better than SR_w1's: gold +50 is valued higher in 84 % of cases, against 65 %.
  - Caveats:
    - It is one seed.
    - Its epoch was chosen on the holdout after the run, which the plan labels exploratory.
    - The holdout chose its blend weight too.
- **Training only on common-seed labels does not transfer to round 2.** Mixing in round 2's labels removes that loss.
  The two captures sample roots differently (every root against every 8th), which may explain it; this was not tested.

## Decision and next steps
- **No default change.** Both pre-registered arms FAIL the gate. The leaf stays X2-B, and SR_w1's blend stays the
  online candidate.
- **Next, if Philipp agrees:** confirm the ranking-selected recipe with seeds 1 and 2, about 2 h on his GPU.
  - The recipe is SR_crn_r2's data with the epoch chosen by the holdout ranking.
  - It needs its own plan before the runs, fixing the selection rule, the patience on ranking and the BCE bar.
  - If it replicates, epoch 11's blend would replace SR_w1's as the online candidate in the parked A/B.
- No game seeds were used.

## Reproduce
```
# training (Philipp's GPU), on the data branch at a8ab7da:
gen2/value-sr-crn/tools/run_sr_crn.sh all
# evaluation (cloud): V = #812's evaluation dir, DATA = a clone of claude/az-gen2-data (beada99),
# REPO = this repository, CRN = `crn_analyze.py rows` output of §644's capture
cd results
V=... DATA=... REPO=... CRN=... ../tools/eval_runs.sh srcrn SR_crn SR_crn_ep8
V=... DATA=... REPO=... CRN=... ../tools/eval_runs.sh srcrnr2 SR_crn_r2 SR_crn_r2_ep11
python3 ../../value_sibling_rank_20261022/tools/train_summaries.py train_summaries.json \
  SR_crn=$DATA/gen2/value-sr-crn/runs/SR_crn/summary.json SR_crn_r2=$DATA/gen2/value-sr-crn/runs/SR_crn_r2/summary.json
```
- The weights are at `0bfe39a` (SR_crn, SR_crn epoch 8) and `beada99` (SR_crn_r2, SR_crn_r2 epoch 11) on the data
  branch. Their sha256 values are in [results/weights.sha256](results/weights.sha256).
- The run on 2026-10-22 used `crn_eval.py`'s copy on the data branch. It differs only in how it finds this
  repository.
- Each `eval_runs.sh` call takes about 26 min on 4 cores. Most of that is `value_leaf_check.py check` on round 2.
