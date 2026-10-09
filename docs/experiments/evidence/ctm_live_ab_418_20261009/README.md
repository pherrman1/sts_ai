# #418 live CTM A/B: production vs pathb-r2 inside live OOC MCTS (2026-10-09)

Ledger: §412 in [ledger-06.md](../../ledger-06.md).

- Pre-registration: [PREREG.md](PREREG.md) (sha256 `3e62bef7…`, reviewed at `3b5d77c2`) and the frozen analyzer
  [live_ab_analyze.py](live_ab_analyze.py) (sha256 `510ccf0d…`).
- Venue: 4 cloud workers × 4 CPU, run by [cloud_worker.sh](cloud_worker.sh) from checkout `a159119d`, binary built at
  `648334e3` (`one_combat` sha256 `dddb09f0…`). Deviations D1–D9: [DEVIATIONS.md](DEVIATIONS.md).
- Seeds `63000000..63000127` (128 pairs), smoke seed `63009000`; arms `prod`, `cand`, `off`.
- Reviews: pre-run [reviews/prerun/REVIEW.md](reviews/prerun/REVIEW.md) (NOT PASSED at `5ff7e557`, delta re-review
  PASSED at `3b5d77c2`); result [reviews/result/REVIEW.md](reviews/result/REVIEW.md) (PASS; reproduces the report
  with the D9 handling; requires the D9 correction) with its
  [trace_gap_audit.py](reviews/result/trace_gap_audit.py).

## Committed outputs

| File | What |
|---|---|
| [combined/report.json](combined/report.json) | Full analyzer output (sha256 `9486c582…`). `runDir` is the local scratch copy used for the D9 handling. |
| [combined/report.summary.json](combined/report.summary.json) | Verdict, flags, win rates, Δwin CI, McNemar, boss deaths |
| [combined/D9-TORN-TRACE-LINES.md](combined/D9-TORN-TRACE-LINES.md) | D9 note; the repo copy appends the result review's correction |
| `workers/wNN/PREREG-FROZEN.txt` | Each worker's freeze record (identical from line 4 on; run checkout `a159119d`) |
| `workers/wNN/DONE.txt` | Each worker's completion record: 12 units rc=0, no seed failures, sha256 of all 84 unit files |
| [workers/w01/SMOKE_PASS](workers/w01/SMOKE_PASS) | Smoke gate (seed `63009000`, worker 1 only), with the per-arm s/run and projected wall time |
| [workers/RAW-FILE-SIZES.txt](workers/RAW-FILE-SIZES.txt) | Size of every raw file in `w01..w04` |

Every committed file except this README, `DEVIATIONS.md`'s D9 section and the appended correction in the D9 note is a
byte-exact copy of the share file.

## Raw data (not committed)

The raw run files are **not committed**: the run tree is about 91.7 MB (w01 22.3 MB, w02 23.3 MB, w03 22.6 MB,
w04 23.4 MB), almost all of it trace JSONL. They stay in the project share under
`/mnt/project-files/ctm-pathb/live-ab-cloud/` (`w01/`..`w04/`, each with `run/`, `logs/`, `units.txt`; `w01/smoke/`).
The candidate artifacts used by the run are in `candidate/` there (4.2 MB; `SHA256SUMS.txt`). Each worker's
`DONE.txt` (committed) holds the sha256 of every unit file, so the share copies can be verified.

Per-kind sizes (all four workers; per-file sizes in [workers/RAW-FILE-SIZES.txt](workers/RAW-FILE-SIZES.txt)):

| Kind (`run/`) | Files | Total bytes | Per file |
|---|---|---|---|
| `{cand,prod,off}-*.csv` (primary metric source) | 48 | 18,065 | 373–380 |
| `*.done` (exit status) | 48 | 3,584 | 74–75 |
| `*.csv.meta.json` (sidecars) | 48 | 68,960 | 1,436–1,437 |
| `*.log` | 48 | 176,411 | 1,149–4,994 |
| `{cand,prod}-*.mcts.csv` | 32 | 76,488 | 2,348–2,446 |
| `{cand,prod}-*.mcts.csv.support.jsonl` | 32 | 37,952 | 1,173–1,235 |
| `{cand,prod}-*.mcts.csv.actions.jsonl` | 32 | 6,269,238 | 166,422–212,567 |
| `cand-*.trace.jsonl` | 16 | 25,756,949 | 1,331,009–1,820,197 |
| `prod-*.trace.jsonl` | 16 | 25,422,479 | 1,290,787–1,732,467 |
| `off-*.trace.jsonl` | 16 | 33,003,060 | 1,862,158–2,235,779 |
| `DONE` | 4 | 5,680 | 1,420 |
| `w01/smoke/` (3 arms, 21 files) | 21 | 790,061 | 74–289,551 |

Worker 1's `logs/RESUMES.txt` records one setup re-run at 15:05:31Z, before the smoke and any launch, with the frozen
inputs unchanged (the result review judged it harmless). No unit was restarted or aborted.
