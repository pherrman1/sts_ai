# Silver x OOC MCTS simulation grid (in progress)

Descriptive 3x3 grid: real-combat Silver sims {1k, 10k, 100k} x live OOC MCTS
sims {1k, 10k, 100k}, seeds 126700..126731 (32, paired), A0, Act-3 horizon.
Frozen settings and provenance are in `manifest.json`; source commit
`e814b65`, which adds the experimental
`STS_OOC_MCTS_ALLOW_SILVER_BUDGET_MISMATCH=1` override.

Non-10k Silver cells run OOC MCTS with a combat-transition model trained on
10k-Silver outcomes, so those cells carry a teacher/actor mismatch.

- `run_one.sh` runs one (silver, ooc, seed) job through `tools/seed_guard.sh`.
- `run_grid.sh` runs `jobs.txt` with 4 workers and skips completed runs.
- `summarize.py` aggregates `runs/*.csv` into `summary.json` (Wilson 95% CIs).

Status: partial. Per-run CSVs are committed as cells complete.
