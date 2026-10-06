# #367 v_win terminal pricing pilot (2026-10-06)

Ledger: [ledger-06 §385](../../ledger-06.md). PR #422.

- Candidate: `b67107500457e94b1f99b5fdf1f1066defcce9c5`, GCC 13 Release, cloud 4-vCPU container; hashes in `provenance.sha256`.
- Seeds 49000001..49000128, A0, fair, `bestbench 10000 32 0 <lo>`, `STS_SILVER_LEARNED_STOP=1`, OOC MCTS off; four 32-seed shards, each running control then treatment (`run.sh`, via `tools/seed_guard.sh`).
- Treatment: `STS_SILVER_VWIN_LEAF=1`, `STS_SILVER_VWIN_LEAF_SAMPLES=4`.
- `control.csv`, `vwin.csv`: merged per-seed rows; `paired_analysis.txt`: `paired_analysis.py control.csv vwin.csv`; `pricer_totals.txt`: per-shard pricer stderr totals.
- Pre-run independent review was skipped on Philipp's explicit instruction.
