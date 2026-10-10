# #418 live A/B: deviations from PREREG.md (venue change)

Recorded 2026-10-09, before any cohort seed ran. PREREG.md (sha256 `3e62bef7…`) was reviewed at `3b5d77c2` and is
unchanged. So are `live_ab_analyze.py` (`510ccf0d…`) and every rule, threshold, seed, arm environment and per-unit
setting in it. Philipp moved the run from his machine to 4 cloud workers. `cloud_worker.sh` (this directory) runs the
frozen harness there. It extracts `arm_env.sh`, `run_unit.sh` and `launch.sh` byte-exact from PREREG.md §7.2 and
regenerates `units.txt` with the §7.2 generator. Each of the four is checked against its sha256 at `3b5d77c2`.

## What changes

| # | PREREG.md | Cloud run | Effect on results |
|---|---|---|---|
| D1 | Venue: Philipp's machine, one process tree, `J=10` concurrent units (§4, §6, §7) | 4 cloud containers × 4 CPU, `J=4` concurrent units per worker, 16 in total | None expected. Each unit is still one single-threaded `bestbench` process (`OMP_NUM_THREADS=1`, 8 seeds). PREREG §9 Q4: J changes wall time only. Silver budgets are simulation counts and MCTS early stop is visit-based (H7). |
| D2 | One `units.txt` (48 units), run in file order | Worker W runs the 12 units of blocks b with `b % 4 == W − 1`, in the frozen file order: all three arms of a seed stay on one worker | None. The order does not affect per-seed results (§2). The full 48-line file is still generated and hash-checked (`units.all.txt` = `7a9b8ba8…`). |
| D3 | Binary: Philipp's `$OC` copied (sha256 `dddb09f0…`) | Each worker builds `one_combat` (Release, `cmake --preset linux-gcc-release`, target `one_combat` only) at `648334e3` and must reproduce sha256 `dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169`. On any mismatch it stops. | None if the hash matches (same bytes). A mismatch is not a permitted deviation; it needs a new decision. |
| D4 | Checkout: `$WT` (offline-A/B worktree at `7d62ba42`) | A fresh clone. The binary is built at `648334e3`, then the clone is checked out at the run commit, where the harness runs (scripts must come from the repo). The script requires `git diff 648334e3 HEAD` to be empty for apps, src, include, CMake files, submodules, `models`, `selfplay/models`, `tools/seed_guard.sh` and `tools/agent/check_benchmark_canary.py`. It also re-checks the 7 model sha256s from §6. | None: identical bytes. `PREREG-FROZEN.txt` records the run-commit HEAD instead of `7d62ba42`. |
| D5 | Candidate files from `$R2/durable` | From `/mnt/project-files/ctm-pathb/live-ab-cloud/candidate/` (raw bytes), copied to local tmp, checked with `sha256sum -c SHA256SUMS.txt` and against `90806c25…`, `b9188de0…` and `d9d8377e…` | None: identical bytes. The manifest pins artifacts by sha256. |
| D6 | Smoke (§7.4) on the one machine before launch | Only worker 1 runs it (seed `63009000`, same checks). Workers 2–4 freeze their inputs, then start only after `w01/SMOKE_PASS` exists, and never after `SMOKE_FAIL`. The projected wall time is printed per worker (32 seeds / J=4). | Same gate. Every worker runs a byte-identical binary and identical scripts; `combine` checks that the four freeze records match. |
| D7 | One `PREREG-FROZEN.txt`, then a tarball hand-back (§7.3, §7.7) | One `PREREG-FROZEN.txt` per worker, in `/mnt/project-files/ctm-pathb/live-ab-cloud/wWW/`. Unit outputs go there directly (`run/`, `logs/` and `smoke/` are symlinks from the local `$HOME/liveab-wWW`). Each worker writes `DONE.txt` with the sha256 of every unit file. No tarball. | None. Writing straight to the share keeps finished units across a container restart; resume works as in §7.6. |
| D8 | `analyze` on one run directory | `combine` copies the unit files of w01..w04 (disjoint names) into one fresh local directory, requires 48 `.done` files and identical freeze records, then runs the frozen `analyze` unchanged | None |

## Unchanged (explicitly)

* Seeds `63000000..63000127`, smoke `63009000`, 8-seed units, 3 arms, one `env -i` environment per arm (`arm_env.sh`).
* `tools/seed_guard.sh` in front of every `bestbench`.
* Per-unit `timeout 3h`.
* Resume semantics: an interrupted unit moves to `run/aborted-<UTC>/` and reruns whole.
* All verdict rules, integrity checks, stall/timeout handling and secondaries in §5, and the analysis constants.
* `STS_EXECUTABLE_GIT_SHA=648334e3…` and the expected `executableGitSha` in the sidecars.

## Timing

Per worker: 32 seeds × (2 × ~114 s MCTS + ~58 s off) ≈ 2.5 CPU-h, which is about 40 min on 4 CPUs (8 MCTS units of
~15 min in two waves, then 4 off units of ~8 min). Add the build (~25–30 min, serial LTO link) and worker 1's smoke
(~5 min, before the others start). The expected total is about 1.2–1.5 h from start to all four `DONE.txt` files.
The cloud per-run CPU figures are §384's own (measured on 4-CPU cloud containers). `sec` in the CSVs is reported, not
a metric.

## D9 (post-run, before reading any result): torn and overwritten trace records

Recorded 2026-10-09 after all four workers wrote `DONE.txt` and before any result was read; corrected after the
independent result review ([reviews/result/REVIEW.md](reviews/result/REVIEW.md), finding 2). Full note:
[combined/D9-TORN-TRACE-LINES.md](combined/D9-TORN-TRACE-LINES.md).

| # | PREREG.md | Cloud run | Effect on results |
|---|---|---|---|
| D9 | `analyze` reads every trace/support JSONL line as JSON (`live_ab_analyze.py:175`) | `cloud_worker.sh combine` crashed with `JSONDecodeError`: 7 of 95,486 JSONL lines in 5 files were torn fragments. The frozen analyzer (`510ccf0d…`, bytes unchanged) was run on a local copy of the combined run tree with only those 7 lines removed; the originals in `w01..w04/run` are untouched and still match each worker's `DONE.txt`. | Primary verdict unaffected (it reads the CSVs). See the correction below for the trace records that were lost. |

**Correction (result review).** The open/write/close appends at `apps/one_combat/run_driver.cpp:102` are not atomic
on the network share. Besides the 7 torn lines, they silently overwrote about 20 whole trace records on 4 seeds, all
wins: `off` 63000066, 63000115 and 63000126, and `prod` 63000073 (one non-boss fight). No `cand` trace is affected.

* **Unaffected, exactly:** the CSV primary, the boss-death counts (cand 19, prod 26, off 18) and `BOSS_DEATH_EXCESS`.
* **Slightly off (descriptive only):** the `off` arm's by-act boss-entry counts (127/124/118 read vs 128/126/119
  implied by the CSVs), its mean start HP and its Smoke Bomb counts.

The share copy of the D9 note (`/mnt/project-files/ctm-pathb/live-ab-cloud/combined/D9-TORN-TRACE-LINES.md`) is the
pre-correction version; the repo copy appends the correction.
