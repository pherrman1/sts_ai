# AZ gen 2 value distillation (interim, 2026-10-21 16:25Z)
Pick recipe (d64/L2 from student_sel, lr 1e-4 / anchor 0.3 / value weight 0.3, K=32, pack, val-at-end, patience 3, seed 0),
uncached (`--compact`), value target = alpha * teacher_v + (1 - alpha) * z, teacher = T1 (heart1 fine-tuned, sha256 610b509b…).
Teacher values: `tools/label_value.py` (sigmoid of the value head, untrimmed, bf16) on all 2,688 gen-2 files; labeled rows stay on
the PC (`~/h1distill/gen2/vdistill/rows_T1`, `rows_h1raw`), per-file sha256 here. Code: `tools/distill.py` (`--value-teacher-alpha`).

| run | sel policy KL | sel value BCE / AUC (vs z) | val KL | val value BCE / AUC |
|---|---|---|---|---|
| pick (alpha 0, Stage S) | 0.0554 | 0.559 / 0.740 | 0.0542 | 0.526 / 0.758 |
| VD_T1_alpha1_v0.3 | 0.0546 | 0.567 / 0.737 | 0.0537 | 0.536 / 0.750 |
| VD_T1_alpha0.5_v0.3 | 0.0548 | 0.560 / 0.741 | 0.0538 | 0.529 / 0.756 |
| T1 teacher | 0.118 | 0.546 / 0.768 | 0.109 | 0.502 / 0.786 |

Running: VD_T1_alpha1_v1, then the alpha-0 control on the same code path; mono.py probes of every run at the end.
Teacher value-head probes: `mono_teachers.txt` (T1 and raw heart1).
Suspected design miss: K=32 drops ~90% of value-only states per epoch, which suits z (one label per run) but discards
most of the per-state teacher signal; proposed follow-up: alpha 1 without --value-k.
