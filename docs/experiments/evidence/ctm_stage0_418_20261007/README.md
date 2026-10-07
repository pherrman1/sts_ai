# #418 Stage 0: CTM transfer and optimism check (2026-10-07)

- Frozen plan: [PLAN.md](PLAN.md) (SHA `46153506`, seeds `50000000..50000127`, two teacher arms per seed, six disjoint shards). Collection scripts are in `bin/`.
- Shard completion: [DONE-all.txt](DONE-all.txt). There are 128/128 seeds per arm, 0 quarantined, and every JSONL/manifest hash verified.
- Scoring: `one_combat ctmscorerows ROWS.jsonl OUT.csv` (production CTM stack: DeepSets Lizard T2, Attention V2 Brew fallback, active-Lizard correction), run at this PR's head on every shard JSONL.
- Analysis: `python3 -I analyze.py SCORES_DIR` writes [results.json](results.json). It uses a seed-level paired bootstrap (2,000 reps, RNG seed 418).
- Raw rows and score CSVs (about 12 MB) live in the project share under `ctm-stage0/`. They are not committed.
- Old-corpus TEST check: scored on Philipp's machine (`~/sts_sweep/runs/ctm-oldtest-score-418/`, TEST.jsonl sha256 prefix `9414f705`). The per-cell table is in ledger §386.
