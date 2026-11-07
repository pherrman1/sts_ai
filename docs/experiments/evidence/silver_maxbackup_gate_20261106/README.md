# STS_SILVER_MAX_BACKUP=4 gate (campaign)

PREREG.md has the design. Files: `campaign.manifest`, `units.txt` (2,048 seeds), `run_unit.sh` (arms D, M per seed),
`analyze.py` (gate). Share `/mnt/project-files/silver-maxbackup-gate`. Workers: `bash tools/cloud/worker.sh setup|start
docs/experiments/evidence/silver_maxbackup_gate_20261106 W` at RUN_COMMIT.

Binary: `worker.sh publish-binary` at code_commit c01bad53 (preset linux-gcc-release-x86-64-v3) built
73a32e99d1640d53… and put it in the bin cache.

Smoke (author container, 2026-11-06 17:35 CET, `run_unit.sh` directly, cached binary, net-0220 from the share):
111769990 D rc 0 win floor 56 (40 s), M rc 0 loss floor 50 (24 s, log `max backup min visits=4`);
111769991 D and M rc 0, both die on floor 6 (1 s). All per-game checks passed in both arms.
