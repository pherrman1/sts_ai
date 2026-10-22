# Sibling-ranking loss and auxiliary heads for the OOC value head (plan, 2026-10-22)

Written before any run of this round. Exploratory, offline only. Philipp chose "more offline research before any play
test" (2026-10-22 09:51Z) and asked about auxiliary targets (10:02Z).

## Question
Can the value head learn to rank leaf siblings like X2-B? Every head so far ranks round-2 VALIDATION siblings at
0.55 concordance against X2-B's 0.633 (§577, §622, §636). Fixing its slopes did not change that (counterfactual deltas
and the monotone hinge, §622). Mixing 15 % of the head into X2-B gained +0.011 (§636). Two training-side tries:
1. **Sibling-ranking loss (SR):** train the value logit to order one decision's children like their 64-rollout3 targets.
2. **Auxiliary heads (AUX):** shorter-horizon outcomes on the trunk: passed the next boss, reached act 4, final floor /
   55. Tried once as VT_aux0.3 (gen-2 value-targets queue): select BCE 0.5595, AUC 0.739. That is about the same as
   runs without them. It had one seed, no matched control, an older recipe and no sibling check.

## Data
`data/r2_train_groups.jsonl.gz` (sha256 `b1933cc4…6493567`), made by `tools/sr_groups.py` from the §503 round-2
delivery **TRAIN** split, cap 8 rows per action, seed 0. It has 8,458 groups and 97,500 rows from 1,088 sources (one
source has no group left). The acceptance rules are value_leaf_check's. Groups with Wing Boots (relic 177) are dropped:
these captures encode its relic data, but the deployed encoding holds charges. The target is the mean of the 64
rollout3 values (each ends in X2-B or a terminal), as in §577.
- **Holdout:** sources with seed % 8 == 6 (1,004 groups, 136 sources) are never trained on. They are reported per
  epoch as a diagnostic. X2-B scores 0.6445 there with this tool, and 0.636 on all TRAIN groups.
- VALIDATION and §494 are not read by training. CONFIRM stays unused.

## Arms (`tools/run_sr.sh`)
Every arm uses the M0.3 recipe of `gen2/value-cf/tools/run_cf.sh`: init student_sel, VDF_T1 v0.5 targets,
`--mono-weight 0.3`, seed 0, the same selection (fold-6 objective, patience 3, `--val-at-end`). Every arm also takes
`--sr-data` for the holdout report.
| arm | change |
|---|---|
| SR_w0.3, SR_w1, SR_w0.1 | `--sr-weight w`: each step adds one batch of 16 groups, at most 2 rows per action (about 126 rows). The loss is RankNet over the group's row pairs, weighted by the target gap. |
| AUX0.3 | `--aux-weight 0.3` (training-only heads, saved to aux.pt, never in student.pt); no SR loss |

**Control:** M0.3 seed 0, the existing run (data `c3bd827a`, `gen2/value-cf/weights/M0.3/student.bin`). Seeds 1 and 2
show the seed spread.

## Evaluation (cloud, as for §636)
- **Primary:** round-2 VALIDATION sibling concordance of the head alone. It uses the §577 aggregation
  (value_leaf_check / outcome_head_sibling_check `group_metrics`, `one_combat` 193b0000 on the exported .bin), with a
  paired source bootstrap against M0.3 s0 (0.555) and X2-B (0.633).
- **Secondary:**
  - §494 concordance;
  - regret;
  - outcome AUC;
  - the blend sigmoid((1 − w)·logit X2-B + w·logit head), with w chosen on the TRAIN holdout sources only (SR arms
    trained on the other TRAIN groups);
  - the in-training holdout concordance and `train_first1000` (memorisation).
- **Bars:**
  - selection-fold value BCE ≤ 0.552 (export bar);
  - "−3 HP sign" ≥ 85 % in the prices check (M0.3: 89 %).

## Gate (per arm)
- **PASS:** VALIDATION concordance ≥ 0.633 (X2-B) and both bars met. The arm is then a leaf candidate. It gets seeds 1–2
  before any online test, and Philipp decides.
- **PARTIAL:** concordance ≥ 0.585 (M0.3 + 0.03) and both bars met. Report it, and let the blend numbers say whether an
  online test is worth it.
- **FAIL:** otherwise. A FAIL goes into the ledger as a negative result.

## Cost
One smoke (`run_sr.sh smoke`: 1 epoch on 48 files, SR and AUX together) and four runs on Philipp's GPU. A plain M0.3
run took about 35–60 min. SR adds about half a batch per step.
