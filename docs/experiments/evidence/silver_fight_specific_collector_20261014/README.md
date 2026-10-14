# §467 evidence: fight-specific (Collector) Silver MLP prior, offline

- `RESULT-offline-pilot.md`: fine-tunes of gen 4 on existing per-boss roots (no new data).
- `PREREG.md`, `BRIEF-worker.md`, `worker.sh`, `env.sh`, `SHA256SUMS`: frozen Collector data run
  (code 1518989b, binary ad90e698, seeds 95000000-95002559). `SHA256SUMS` lists the share copies
  (paths relative to `/mnt/project-files/silver-prior-fight-specific/collector-data/`).
- `ft.py`, `merge.py`, `subpack.py`, `evalpair.py`: analysis code as pinned in PREREG.
- `RESULT.md`, `report-*.json`: gate result and per-run reports.
Raw data, packs and models: `/mnt/project-files/silver-prior-fight-specific/` (w01-w04.tar, `result/`).
