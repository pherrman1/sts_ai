# Shared-child exploration, flat 10,000, 128 paired seeds — 2026-09-28

Ledger §373. `manifest.json` is the pre-registration (committed before any
outcome was inspected); the 32-seed screen's pre-registration is in
`../silver_shared_child_exploration_flat10k32_2026-09-28/`.

- `shards/`: per-offset bestbench results, sidecars and logs (2 arms × 32
  shards of 4 seeds). The offset-32 result files also hold copies of seeds
  0..31 (an analysis file was written to that name before phase 2 appended
  its rows); `merge.py` asserts the copies are identical and drops them.
- `control_128.csv`, `shared_128.csv`: one row per seed 0..127 (`merge.py`).
- `control_32.csv`, `shared_32.csv`: seeds 0..31, the 32-seed screen.
- `paired_128.txt`, `paired_32.txt`: `paired_analysis.py` output.
- `job.sh`, `status.txt`: the job script and per-shard exit statuses.
- `results.json`: outcome summary and artifact hashes.
