# Ranking-selected SR head: seeds 1 and 2 (2026-10-22/23)

Offline. [PLAN.md](PLAN.md) is the plan as it was written before any run. It is a frozen copy of
`gen2/value-sr-crn/PLAN_SEEDS.md` on the data branch `claude/az-gen2-data` at `0341698` (sha256 `cde866c4…`).
- Philipp typed "merge 816 and go seeds" on 2026-10-22 at 20:52Z, after §645.
- Training ran on Philipp's GPU, one seed after the other: seed 1 from 20:59Z to 22:24Z, seed 2 until 23:50Z.
  - The card has 8 GB, so the two seeds could not share it.
  - Seed 2's export and push waited until 06:56Z the next morning, because the session on the PC had gone idle.
- Evaluation ran in the cloud.

## Question
§645's exploratory head is SR_crn_r2 seed 0 at epoch 11, the epoch with its best in-training holdout ranking.
- Alone, it is level with X2-B on the common-seed VALIDATION (0.660 vs 0.664).
- Its blend beats SR_w1's blend by +0.014 [+0.009, +0.019].
- But its epoch was chosen after the run.

Does the recipe "SR_crn_r2's training, with the epoch chosen by the holdout ranking" give the same result on fresh
seeds, with the rule fixed in advance?

## Setup
- **Runs:** SR_crn_r2's command (§645) with `--seed 1` or `--seed 2` and `--patience 0`.
  - `run_sr_crn.sh seeds` on the data branch at `0341698` (sha256 `8b930930…`). `distill.py` is unchanged
    (`40a9d5a3…`).
  - Every run trains all 20 epochs of the same one-cycle schedule and keeps every epoch.
  - The data are SR_crn_r2's: groups file sha256 `3f78ae0c…`, 19,781 training groups, and the mixed in-training
    holdout of 3,806 groups from 176 sources.
- **Epoch choice** ([tools/pick_epoch.py](tools/pick_epoch.py), fixed in the plan):
  - **Primary:** the epoch with the best in-training holdout ranking among the epochs whose selection-fold value BCE
    is at most 0.570. Ties go to the earliest epoch.
    - The cap replaces #812's bar of 0.552 for this round, because the candidate is the blend, with w ≤ 0.30, not the
      head alone.
    - The rule picks epoch 11 on seed 0's curve.
  - **Secondary ("value stop"):** the same choice, but only among the epochs a patience-3 stop on the selection
    objective would have run. That is the procedure that produced seed 0's epoch 11.
- **Evaluation:** §645's [eval_runs.sh](../value_sr_crn_20261022/tools/eval_runs.sh) runs three steps per head.
  - The prices check.
  - `crn_eval.py` on the common-seed capture (§644). Each blend's w is chosen on the TRAIN holdout (seed % 8 == 6)
    from 0.05 to 0.30; then the blend is compared on VALIDATION with SR_w1 seed 0's blend (w 0.10).
  - #812's `sr_eval.py` on round 2.
  - The control is SR_w1 seed 0, the current online candidate.
- **Gate** (per seed, primary epoch):
  - The blend minus SR_w1's blend on the common-seed VALIDATION must have its paired CI above 0.
  - The bar: "−3 HP sign" ≥ 85 %.
  - **REPLICATED** if both seeds pass, **PARTIAL** if one does, **NOT_REPLICATED** if neither does.

## Results
**Training and bars** ([results/pick_epoch_SR_crn_r2_s1.json](results/pick_epoch_SR_crn_r2_s1.json),
[results/pick_epoch_SR_crn_r2_s2.json](results/pick_epoch_SR_crn_r2_s2.json), the training logs in `results/`, and
[results/prices_seed1.txt](results/prices_seed1.txt), [results/prices_seed2.txt](results/prices_seed2.txt)):

| head | holdout ranking in training | selection-fold value BCE (≤ 0.570) | −3 HP sign (≥ 85 %) | gold +50 valued higher | max HP +5 valued higher |
|---|---|---|---|---|---|
| SR_w1 (control, §641) | – | 0.547 | 88.1 % | 65.4 % | 54.0 % |
| seed 0, epoch 11 (§645, exploratory) | 0.656 | 0.557 | 88.2 % | 84.4 % | 55.5 % |
| **seed 1, epoch 13** | 0.667 | 0.565 | 90.9 % | 77.2 % | 60.5 % |
| **seed 2, epoch 20** | 0.669 | 0.562 | 89.4 % | 84.3 % | 59.9 % |
| seed 1, epoch 7 (value stop) | 0.645 | 0.550 | 88.0 % | 87.3 % | 49.2 % |
| seed 2, epoch 9 (value stop) | 0.654 | 0.566 | 87.8 % | 84.8 % | 56.7 % |

- The in-training holdout is the same mixed set for all three seeds.
- Both seeds plateau from about epoch 12, at 0.660–0.667 (seed 1) and 0.662–0.669 (seed 2). Seed 0 stopped at
  epoch 11, while it was still rising.
- The run's own fold-selected epochs (4 and 6) are exported too but were not scored.

**Sibling concordance** (common-seed VALIDATION, where X2-B scores 0.664; round-2 VALIDATION, where it scores 0.633;
[results/crn_eval_seed1.txt](results/crn_eval_seed1.txt), [results/crn_eval_seed2.txt](results/crn_eval_seed2.txt),
[results/sr_eval_seed1.txt](results/sr_eval_seed1.txt), [results/sr_eval_seed2.txt](results/sr_eval_seed2.txt); the
first two rows are §645's):

| head | VALIDATION | − X2-B | − SR_w1 | blend w | blend | blend − X2-B | blend − SR_w1's blend | round 2 | round-2 blend |
|---|---|---|---|---|---|---|---|---|---|
| SR_w1 (control) | 0.645 | −0.019 [−0.031, −0.008] | – | 0.10 | 0.689 | +0.025 [+0.019, +0.031] | – | 0.644 | 0.673 (w 0.05) |
| seed 0, epoch 11 (exploratory) | 0.660 | −0.004 [−0.017, +0.009] | +0.015 [+0.009, +0.022] | 0.10 | 0.703 | +0.039 [+0.031, +0.046] | +0.014 [+0.009, +0.019] | 0.648 | 0.678 (w 0.10) |
| **seed 1, epoch 13** | 0.663 | −0.001 [−0.015, +0.012] | +0.018 [+0.011, +0.025] | 0.10 | 0.702 | +0.038 [+0.031, +0.045] | **+0.013 [+0.008, +0.019]** | 0.653 | 0.675 (w 0.25) |
| **seed 2, epoch 20** | 0.667 | +0.003 [−0.012, +0.017] | +0.022 [+0.015, +0.030] | 0.10 | 0.703 | +0.039 [+0.031, +0.047] | **+0.014 [+0.009, +0.020]** | 0.655 | 0.682 (w 0.10) |
| seed 1, epoch 7 (value stop) | 0.644 | −0.020 [−0.033, −0.008] | −0.001 [−0.007, +0.005] | 0.15 | 0.690 | +0.026 [+0.018, +0.034] | +0.001 [−0.004, +0.006] | 0.633 | 0.660 (w 0.25) |
| seed 2, epoch 9 (value stop) | 0.654 | −0.010 [−0.023, +0.002] | +0.009 [+0.003, +0.016] | 0.20 | 0.692 | +0.028 [+0.019, +0.037] | +0.003 [−0.003, +0.010] | 0.644 | 0.669 (w 0.05) |

- **Gate: REPLICATED.**
  - Seed 1 passes: +0.013 [+0.008, +0.019], with −3 HP sign at 90.9 %.
  - Seed 2 passes: +0.014 [+0.009, +0.020], with −3 HP sign at 89.4 %.
- **Candidate:** the plan picks the best TRAIN-holdout blend among seeds 0–2. The holdout blends are 0.700 (seed 0),
  0.704 (seed 1) and 0.706 (seed 2), so the candidate is **seed 2, epoch 20**, at w 0.10.
- **Round 2:** both primary heads beat SR_w1 alone. Seed 1 is +0.010 [+0.001, +0.019] and seed 2 is +0.011
  [+0.002, +0.021]. Their blends score 0.675 and 0.682, against SR_w1's 0.673.
- **Outcome AUC on round-2 VALIDATION:** 0.679 and 0.677, against 0.672 for SR_w1 and 0.683 for X2-B.
- **§494's siblings:** the blends score 0.652 (seed 1) and 0.642 (seed 2), against 0.631 for SR_w1's blend and 0.601
  for X2-B.

## Interpretation
- **The ranking-selected recipe replicates.**
  - On fresh seeds, with the rule fixed in advance, both blends beat SR_w1's by +0.013 to +0.014. That is the same
    gain as seed 0's exploratory epoch.
  - Alone, the heads are now level with X2-B (0.663 and 0.667 vs 0.664), where SR_w1 was 0.019 below it.
- **The gain comes from training longer, and the ranking is a better stopping signal than the value objective.**
  - The epochs a value-based stop would have kept (7 and 9) do not beat SR_w1's blend.
  - The ranking keeps improving until about epoch 12–13 while the selection-fold BCE drifts from about 0.55 to
    0.56.
- **The cost is small.** Selection-fold BCE is 0.562–0.565 against SR_w1's 0.547. Monotonicity is better than
  SR_w1's for gold and max HP, and slightly better for HP.
- **Caveats:**
  - All of this is offline. The labels end in X2-B (rollout3 means), and the blend weight and the epoch are both
    chosen on the same TRAIN holdout.
  - In both past A20 leaf A/Bs with offline numbers, offline concordance and online play disagreed in direction:
    - §504: the rollout student, distilled from rollout3 means, was WORSE online;
    - §615: the gen 1b head ranked siblings below X2-B but leaned +3.1 pp online.
  - So the offline gain does not by itself predict a gain in Heart kills.

## Decision and next steps
- **No default change.** X2-B stays the leaf.
- **New online candidate:** seed 2's epoch 20 blend (w 0.10) replaces SR_w1's as the candidate (the plan's REPLICATED
  rule).
  - The weights are `gen2/value-sr-crn/weights/SR_crn_r2_s2_ep20/student.bin` on the data branch (sha256 `28523fb5…`).
  - They were trained with `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`, as SR_w1 was.
- **Any online test needs Philipp's go and worker count.** The value-head research plan's running 2×2 A/B uses
  SR_w1's blend; that thread decides whether its later stages use the new head.
- No game seeds were used.

## Reproduce
```
# training (Philipp's GPU), on the data branch at 0341698:
gen2/value-sr-crn/tools/run_sr_crn.sh seeds
python3 gen2/value-sr-crn/tools/pick_epoch.py ~/h1distill/gen2/valuesrcrn/runs/SR_crn_r2_s<S>/summary.json
# evaluation (cloud), as in §645 (V = #812's evaluation dir, DATA = a clone of claude/az-gen2-data at 4913b41,
# REPO = this repository, CRN = `crn_analyze.py rows` output of §644's capture):
cd results
V=... DATA=... REPO=... CRN=... ../../value_sr_crn_20261022/tools/eval_runs.sh seed1 SR_crn_r2_s1_ep13 SR_crn_r2_s1_ep7
V=... DATA=... REPO=... CRN=... ../../value_sr_crn_20261022/tools/eval_runs.sh seed2 SR_crn_r2_s2_ep20 SR_crn_r2_s2_ep9
```
- The runs, weights and these results are on the data branch: `eca4b6f` (seed 1), `4913b41` (seed 2), and
  `d9a85d0` / `43ad57f` (evaluation). The new weights' sha256 values are in
  [results/weights.sha256](results/weights.sha256).
- Each `eval_runs.sh` call took 23–27 min on 4 cores.
