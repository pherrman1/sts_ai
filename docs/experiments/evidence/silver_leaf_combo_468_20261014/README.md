# §468 evidence: situational Silver leaf bundle vs legacy leaf, paired whole runs

- Pre-registration: [PREREG.md](PREREG.md). Smoke: [SMOKE.md](SMOKE.md). Worker brief: [BRIEF-worker.md](BRIEF-worker.md)
  (sha256 `b10ac92c…`, pre-launch review PASS after one round of fixes).
- Code commit [CODE_COMMIT](CODE_COMMIT) `f41ec4d3`; run commit `7fc41609`; binary sha256 [binary.sha256](binary.sha256)
  `a45ef01e…` on all 8 workers.
- Raw data: `/mnt/project-files/silver-leaf-468/w01..w08.tar` and `.DONE.txt` ([SHA256SUMS](SHA256SUMS)).
- Analysis: `python3 tools/analyze_silver_leaf_468.py report.json <8 extracted out dirs>` → [report.json](report.json).
- Validity: 2,000/2,000 units rc=0; no stalls, timeouts, restarts or `[bestbench-seed-failure]`; every `.env` holds its
  arm's four options; 500/500 pairs per cohort.

Per-act deaths below are descriptive (computed from the same rows; not pre-registered).

| | A0 base | A0 all | A20 base | A20 all |
|---|---|---|---|---|
| wins | 370 | 357 | 52 | 71 |
| died act 1 (floor ≤ 17) | 3 | 4 | 96 | 120 |
| died act 2 (18–34) | 43 | 43 | 166 | 161 |
| died act 3 before floor 50 | 25 | 27 | 61 | 58 |
| died floor 50 (act-3 boss / A20 first boss) | 59 | 69 | 51 | 42 |
| died floor 51+ (A20 second boss) | – | – | 74 | 48 |
| mean floor | 48.54 | 48.36 | 35.25 | 33.96 |
| seconds per run | 62.4 | 62.8 | 42.8 | 41.1 |

A20 paired act-1 deaths: `all` only 50, `base` only 26 (exact McNemar p = 0.008). Of the 113 A20 seeds where both arms
reached floor 50, `base` won 38 and `all` won 52.
