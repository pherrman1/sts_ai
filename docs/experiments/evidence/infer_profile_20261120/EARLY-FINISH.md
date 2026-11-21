<!-- Relayed by the run's thread from the PC, 2026-11-21 02:09 CET; raw rows on the PC in amber_scratch/ (ef_before_*, ef_after_*). -->

# --early-finish live test (PC, amber_scratch, A5, 11 workers x 450 games)
Same flags both rows except --early-finish; StS2/Discord/Firefox closed in both. Raw: PC ~/Documents/sts/stage1/amber_scratch/early-finish-live.md, ef_before_*, ef_after_*.

| | moves/s (6 rows) | pos/s | GPU SM | workers sleeping | inference thread running |
|---|---|---|---|---|---|
| before 00:15:44-00:18:15 CET (c6_repo) | 11,490 (sd 124) | 225,400 | 66.8 % | ~32 % | 75.3 % |
| after 02:05 CET, 35 min after 01:30 start (ef_repo f17f1e21) | 11,887 (sd 81) | 233,200 | 72.7 % | ~28 % | 72.6 % |

+3.5 % moves/s. infer_early_per_batch 0.23. No errors, no new nonfinite skips, losses normal. Flag stays on.
Note: between 00:18 and 01:30 the run was stopped (capacity probe), resumed from ckpt_776248.
