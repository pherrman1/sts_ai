# Gumbel stop-trace data: result (2026-11-10)

Data run of PREREG.md. Launched 08:51 CET on 40 workers; last tar 11:08 CET.

- `verify_campaign.py`: 1,024/1,024 OK, 0 missing, 0 bad, 0 duplicates, run c718ee47, 40/40 DONE.json
  (`results/verify.txt`). Drops (rc != 0, timeout, no trace rows): 0. Claims snapshot `results/claims.txt`
  (1,024 first attempts); claims/ removed afterwards.
- Cost 166.8 lane-h (sum of game walls; plan about 150).
- Share brief deviation: after the K prelaunch review, step 1 of the share copy of BRIEF-worker.md also fetches the
  code_commit ebd446b3 (`git fetch --depth 1`), which `worker.sh setup` diffs against on shallow clones. The repo copy
  and the hashed campaign files are unchanged.
- Data: `/mnt/project-files/gumbel-stop/data/units/<seed>.wNN.tar`, each with `G16-<seed>.csv.xz`
  (STS_SILVER_GUMBEL_STOP_TRACE rows) next to the game's env, log, err and done files.

Descriptive (no control on these seeds): G16 Heart kills 426/1,024 = 41.6 % (§775 G16 on its seeds: 41.2 %).

Per boundary over 574,741 searched roots (`results/boundaries.json`, `results/summary.json`): the share of roots
whose leader at boundary b is already the 16k pick, and the root's CPU share up to b.

| phases | roots | b = 0 | b = 1 | b = 2 | b = 3 |
|---|---|---|---|---|---|
| 1 | 52,322 | 78.2 % (0 %) | | | |
| 2 | 147,877 | 55.0 % (0 %) | 84.6 % (50.0 %) | | |
| 3 | 263,682 | 34.0 % (0 %) | 66.0 % (33.4 %) | 74.0 % (66.7 %) | |
| 4 | 110,860 | 20.0 % (0 %) | 45.7 % (25.2 %) | 58.3 % (50.2 %) | 69.9 % (75.1 %) |

Agreement here is over all roots; a learned stop needs high agreement only on the roots where it stops.
Next (not yet authorized as a gate): train a stop model on these rows (grouped by root, CV by run) and report
agreement vs CPU fraction offline.
