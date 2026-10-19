# #401 Stage 1 for the deployed learned models (student_sel, g7f_E, A20 CTM)

Ledger: [`ledger-06.md` §546](../../ledger-06.md). Analysis only: no gameplay seeds, no `one_combat` runs.
Run 2026-10-18/19 in a cloud container (PyTorch 2.14.1 CPU, fp32, one torch thread per audit).

| model | artifact (sha256) | held-out split | report |
|---|---|---|---|
| student_sel (OOC policy, heart1 distillation) | `student_sel.bin` `cf6bf7fb…` / `student.pt` `1f96f4bf…`, `claude/heart1-distill-data` 5a7245aa `results/E_d64_sel_xin/` | distill.py held-out runs (seed % 8 == 7), 243,103 rows; 50k sampled | [student_sel/REPORT.md](student_sel/REPORT.md) |
| g7f_E (Silver root prior / root table) | `models/combat_policy_mlp_g7f_E.txt` `c45dcc0a…`; value head from `runs/g7f_E/model.pt`, `claude/silver-gen7-act4-data` 0168b72d | trainer validation fold `r_seed % 5 == 3` (also used for epoch selection), 582,140 roots | [g7f_E/REPORT.md](g7f_E/REPORT.md) |
| A20 CTM fast DeepSets child | `selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native` `ae785ec2…` | #418 source-seed VALIDATION of the Stage 1 corpus (§470 rows), 57,790 fast-child rows | [ctm_a20/REPORT.md](ctm_a20/REPORT.md) |

Each folder holds `REPORT.md`, `results.json` (parity, baselines, every group / subgroup / single-feature
delta with 95% source-seed cluster-bootstrap CIs, the input-to-group mapping, script sha256s) and `scripts/`.
Scripts expect their data in a scratch directory; the data come from the data branches and share paths named in
each report (nothing is copied here). TEST splits were never read.

Method common to all three: each semantic input group is permuted jointly across held-out roots (whole group
block per row; candidate blocks only between roots with the same candidate count), 5 repeats, per-row loss
deltas, 1,000-resample cluster bootstrap. Parity of the loaded artifact against the logged / natively scored
held-out metric was checked first (all PASS).

The ctm_a20 and g7f_E `REPORT.md` files were written by the coordinating session from the auditing workers'
final reports (verbatim for ctm_a20, condensed for g7f_E); all numbers are in the corresponding `results.json`.
