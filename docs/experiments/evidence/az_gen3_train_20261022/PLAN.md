# AZ gen 3: prior training on the full window (written before training)

Requested by Philipp 2026-10-22 14:16Z ("merge 811 and then go", answering whether to start gen-3 training on his
GPU). Offline only. It picks one candidate for a later paired A20 A/B against student_sel, which needs Philipp's
authorization and worker count.

## Data (fixed before any training)
Window: every AZ capture so far, 5,760 runs.

| Source | Runs | Prior that searched | Rows file name |
|---|---|---|---|
| gen 0 search arm (§569) | 1,664 | student_sel | `az-SEED` |
| gen-1b A/B arm A / arm B (§589) | 512 / 512 | student_sel / gen 1b | `az-SEED` / `az-b-SEED` |
| gen-2 A/B arm A / arm B (§621) | 1,024 / 1,024 | student_sel / gen 2 | `az-SEED` / `az-b-SEED` |
| gen-3 exploration (§640) | 1,024 | student_sel + root noise 0.25:0.3 + play sampling floors 0-6 | `az-e-SEED` |

- Rows: `convert_vtargets.py` of the gen-2 value-target round (data branch `claude/az-gen2-data`
  `gen2/value-targets/tools/`), extended only to read `E-SEED` files, with `az_targets.py` from main `90eb9f07`
  (convert unchanged since gen 2) and β = 2.371373705661655 (§573). Every row carries `nstep_v`, the root value of
  the run's 5th later searched decision, else z. The gen-0 and gen-1b rows are the 2,688 files the gen-2 value-target
  runs used (`gen2/value-targets/rows.sha256`); the 3,072 new files are converted from the verified tars
  (`az_gen2_ab_20261021/tars.sha256`, `az_gen3_explore_20261022/tars.sha256`).
- Calibration: `nstep_v_cal = sigmoid(a + b · logit nstep_v)`, refit on the training folds of all non-exploration
  sources (exploration z is depressed by sampled moves) and applied to every row.
- Folds by run seed as in gen 2: validation `seed % 8 == 7` (report only), selection `seed % 8 == 6`, the rest trains.
  Both arms of a seed fall in the same fold.
- Exploration rows: their policy targets are the search's π' at real states and are kept everywhere. Their value
  targets are mostly bootstrapped search values 5 decisions ahead (`nstep_v`), so the sampled moves bias them only
  near the end of the run. Arm `G3_nstep_noEv` drops them anyway on the training fold (z removed from training
  `az-e-*` rows) to measure it; selection and validation files are identical in every arm.

## Runs (Philipp's GPU, after the value-head queue, which finished 14:15Z)
Recipe = the gen-2 pick: init student_sel (`E_d64_sel_xin/student.pt`, export cf6bf7fb), d64/L2, mult 4, heads 4,
lr 1e-4, anchor 0.3, value weight 0.3, `--value-k 32`, bs 256, 20 epochs, patience 3, `--select fold --pack
--val-at-end --extra-inputs --trim-map --amp`, `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`, distill.py sha256 `8aac69b6…`
(the file every gen-2 value-target run used). Torch seed 0.

1. `G3_z`: value target z (the gen-2 pick recipe).
2. `G3_nstep`: value target `nstep_v_cal`, alpha 1 (the gen-2 best-prior recipe, selection KL 0.0526 ± 0.0003 there).
3. `G3_nstep_noEv`: as 2, exploration value rows removed from training.
4. Reference evals on the same folds (lr 0, 1 epoch): student_sel, gen-2 pick (`fc32d8f4`), `VT_nstep5_cal_l1`
   (`a70736fd`, gen 2's best prior, never A/B'd).
5. The pick (rule below) re-run with seeds 1 and 2.

## Choice
- Rule (as gen 2): lowest selection-fold policy KL among runs whose selection value BCE is below the constant BCE.
  It must also beat both gen-2 references on the selection fold, else gen 3 reports NO_CANDIDATE.
- Report: selection and validation KL / top-1 per screen, value BCE / AUC per act, anchor KL to student_sel, epochs, wall.
- Then native parity of the pick's export (torch vs native forward on recorded states, as gen 2) on the PC.
- Caveat carried forward: gen 1b and gen 2 each improved offline KL and were NOT_SHOWN online (§589, §621). Offline
  rank is a filter, not evidence of strength.

## Execution
Philipp's GPU via Remote Control in the gen-2 scratch worktree; the live parity canary's checkout and the game install
are not touched. Rows and results travel on the never-merged data branch `claude/az-gen2-data` under `gen3/`;
the driver is `gen3/tools/run_g3.sh` there (calibration `calibrate_g3.py`, rule `pick.py`, table `summarize_g3.py`).
