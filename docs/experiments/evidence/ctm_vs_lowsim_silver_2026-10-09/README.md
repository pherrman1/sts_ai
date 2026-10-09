# §408 evidence: CTM vs low-sim Silver as combat-outcome forecasters

- [PREREG.md](PREREG.md): v1 (stopped) and v2 pre-registration, frozen provenance.
- [worker.sh](worker.sh), [teacher.json](teacher.json), [env.sh](env.sh): the v2 run.
- [report.json](report.json): `tools/analyze_ctm_vs_silver.py` on all 16 v2 shards. Its `hp_post`
  section is the review deviation (HP scored as post-combat HP for every forecaster); the
  as-registered `supported`/`paired_vs_ctm` HP numbers are invalid for the CTM (ledger §408).
- [data-sha256.txt](data-sha256.txt): hashes of the raw shard CSVs.
- §410 Run 2 CTM rescoring: [PREREG-R2.md](PREREG-R2.md), [worker_r2.sh](worker_r2.sh),
  [teacher-r2.json](teacher-r2.json), [report-r2.json](report-r2.json) (`tools/analyze_ctm_r2.py`),
  [data-r2-sha256.txt](data-r2-sha256.txt); raw data `/mnt/project-files/ctm-vs-lowsim-silver/r2-a84be6bc/`.

Raw data (not in git, 46 MB):
`/mnt/project-files/ctm-vs-lowsim-silver/v2-ccc3d62a/w00..w03/shard0..3.*`
(states, arms, samples CSVs and per-shard manifests). The stopped v1 run is in
`/mnt/project-files/ctm-vs-lowsim-silver/stopped-128-1f53715d/`
(exploratory, not pooled).

Reproduce the analysis:
`python3 tools/analyze_ctm_vs_silver.py report.json $(for w in 0 1 2 3; do for i in 0 1 2 3; do echo $V/w0$w/shard$i; done; done)`
with `V` the raw-data folder.
