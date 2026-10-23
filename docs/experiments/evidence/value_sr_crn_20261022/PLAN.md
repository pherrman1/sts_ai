# Sibling-ranking loss on the common-seed labels (plan, 2026-10-22)

Written before any run of this round. Exploratory, offline only. Philipp typed "go gpu" (2026-10-22 17:50Z) after
the common-seed recapture result (#815).

## Question
On the common-seed VALIDATION (80 sources, 5,587 groups), the SR_w1 head alone ranks siblings below X2-B: 0.645
against 0.664, −0.019 [−0.031, −0.008]. Its blend still gains +0.026 [+0.020, +0.032]. SR_w1 was trained on round-2
TRAIN (8,458 groups: every 8th root, 64 independent repeats).

Does training on the recapture's TRAIN labels help? Those labels come from every root, with sibling differences at
0.36 of round 2's stream variance per repeat.

## Data
- `data/crn_train_groups.jsonl.gz` (sha256 `dc5b67e0…`), made by `tools/crn_groups.py` from the recapture's TRAIN
  split (seed % 4 != 3), with cap 8 rows per action and seed 0.
  - It has 15,129 groups and 155,368 rows (419,970 before the cap) from 240 sources.
  - The target is the mean of the 32 common-seed rollout3 values.
  - Wing Boots rows are kept, because the capture ran with the deployed counter encoding.
- `../value-sr/data/r2_train_groups.jsonl.gz` (sha256 `b1933cc4…`) is the round-2 TRAIN file from #812.
- **Holdout:** groups whose source seed % 8 == 6 are never trained on. They are reported per epoch, as before.
- The recapture's VALIDATION (seed % 4 == 3) and round-2 VALIDATION are never read by training.

## Arms (`tools/run_sr_crn.sh`)
Both arms use exactly the SR_w1 recipe of `../value-sr/tools/run_sr.sh`, seed 0. Only `--sr-data` changes.
- **SR_crn:** the common-seed TRAIN groups.
- **SR_crn_r2:** the common-seed TRAIN groups plus round-2 TRAIN.

Shared settings:
- init student_sel, VDF_T1 v0.5 targets, mono 0.3, anchor 0.3, `--sr-weight 1`;
- the same selection: fold objective, patience 3, `--val-at-end`;
- `--save-epochs` also keeps every epoch's weights. It does not change training.

A one-epoch smoke on 48 files comes first.

## Evaluation (cloud)
- **Tools:** `crn_analyze.py score` (in #815), with the §577 concordance and `one_combat` 193b0000 on the exported .bin.
- **Primary:** head-alone concordance on the common-seed VALIDATION.
  - It gets a paired source bootstrap against X2-B (0.664) and against SR_w1 seed 0 (0.645).
- **Secondary:**
  - round-2 VALIDATION (X2-B 0.633, SR_w1 0.644);
  - the blend sigmoid((1 − w)·logit X2-B + w·logit head), with w ∈ {0.05, 0.10, 0.15, 0.20, 0.25, 0.30} chosen on the
    common-seed TRAIN holdout (seed % 8 == 6);
  - regret;
  - the per-epoch holdout curve.
- **Bars, as in #812:**
  - selection-fold value BCE ≤ 0.552;
  - "−3 HP sign" ≥ 85 % in the prices check.
- **Exploratory:** if the epoch with the best holdout concordance is not the selected one, it is exported and scored
  too. It is labelled exploratory, because the selection rule is the open question from §641.

## Gate (per arm, common-seed VALIDATION, head alone, bars met)
- **PASS:** ≥ 0.664 (X2-B). The arm is then a leaf candidate and gets seeds 1–2 before any online test. Philipp
  decides.
- **IMPROVED:** above SR_w1 seed 0, with the paired CI above 0, but below X2-B. The blend numbers then decide whether it
  replaces SR_w1 as the online candidate.
- **FAIL:** otherwise. A FAIL is a negative result for the ledger.

## Cost
Two runs of about 40 min each on Philipp's GPU, plus the smoke. No game seeds are used.
