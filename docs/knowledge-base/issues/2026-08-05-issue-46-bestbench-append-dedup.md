# Issue 46: bestbench appends without dedup — scripts must truncate

- **Status:** closed (producer guarded + strict analyzer, 2026-08-07)
- **Tier:** Medium
- **Last verified:** 2026-08-07
- **Source:** 2026-08-05 S3-ablation re-run; `apps/one_combat.cpp`

## Symptom

`bestbench` opens its results CSV with `std::ios::app` and never truncates or
deduplicates ("The caller owns truncation; batches append",
`one_combat.cpp:2759`). Any benchmark script that does not `rm -f` the output
first silently **doubles rows** when re-run over the same seed block. This
polluted `s3ablate_s2_ref` (128 stale + 128 fresh rows) and `s3ablate_s3_ctl`
(74 stale + 128 fresh rows) on 2026-08-05; the first aggregation of §106 used
the polluted files before the re-run.

## Evidence

- `apps/one_combat.cpp:2760-2767` (append-open, header-on-empty only).
- `build/s3ablate_*_3k_128.csv` history (duplicate seeds, 2026-08-05).
- `paired_analysis.py` validates headers but not duplicate seeds.

## Why it matters

Repeated script runs silently corrupt benchmark artifacts; analyses built on
duplicated rows double-count seeds and shrink effective sample sizes.

## Candidate fix direction

- `run_s3_ablate.sh` now truncates per arm (**fixed 2026-08-05**).
- Optional hardening: `paired_analysis.py` warns on duplicate seeds;
  consider a `--truncate`/`--no-append` flag on `bestbench` itself.

## Relevant code

- `apps/one_combat.cpp::bestBench`
- `apps/one_combat.cpp::main` (`mode == "bestbench"` staleness guard)
- `run_s3_ablate.sh`
- `paired_analysis.py`

## Resolution

**Closed 2026-08-07** by the §134 audit hardening, in two layers:

1. Producer guard (`one_combat.cpp::main`, `bestbench` mode): before
   appending, the mode handler refuses (nonzero exit, clear message) when the
   results file already contains a row for any seed in the requested block.
   Self-play batch appends use disjoint offsets on fresh per-iteration files,
   so they are unaffected; `reprobench` uses `bestBench` directly and still
   appends repeats intentionally.
2. Consumer strictness (`paired_analysis.py`, same session): duplicate seeds
   in either CSV are hard errors by default, so any polluted file fails
   loudly at analysis time even if a producer guard is bypassed.

Scripts that re-run the same seed block against the same results file must
still truncate first (`rm -f`) or the command now errors; they can no longer
silently double rows.
