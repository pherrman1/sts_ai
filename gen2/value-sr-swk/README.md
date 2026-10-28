# SR head on swkeyed sibling labels (#903, issue #883)

The plan and pre-registration live on main's PR #903 branch: `docs/experiments/evidence/ooc_swkeyed_labels_20261028/PLAN.md`.
Philipp's go for the capture and the two GPU runs: 2026-10-28 15:20Z. Proceeding despite the row-level bias flag:
his decision at 19:04Z.

- `data/crn_train_groups_swk.jsonl.gz` (sha256 `4541dc8a…`) comes from `../value-sr-crn/tools/crn_groups.py
  --split train --cap 8 --seed 0` on the verified #903 replay (320/320 units, RUN_COMMIT `27c85529`).
  - It has 15,129 groups and 155,368 rows, identical to `../value-sr-crn/data/crn_train_groups.jsonl.gz` except for
    `target`.
- `tools/run_sr_swk.sh` runs §649's SR_crn_r2 seeds 1–2 command unchanged, on these groups plus the unchanged round-2
  TRAIN groups. Outputs go to `~/h1distill/gen2/valuesrswk/runs/SR_swk_r2_s{1,2}/`.
- Epoch choice: `../value-sr-crn/tools/pick_epoch.py` (the §649 primary rule). Weights are exported like §649's,
  under `weights/`.
