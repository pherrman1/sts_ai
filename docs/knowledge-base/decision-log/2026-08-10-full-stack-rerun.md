# 2026-08-10 — Post-correctness-batch full-stack rerun

Date: 2026-08-10
Session/task: Rerun the recommended GCP full stack after the correctness batch.

## Decision

Run the gates-on recommended configuration across A0/A5/A10/A15/A20 on
`sts-test`, using 25 seeds per ascension. The 25-seed allocation was chosen
because agent-driven sweeps have a hard 128-seed ceiling; five ascensions × 25
seeds = 125 total.

## Evidence

- Checkout synced at HEAD `5959e4c`; the fixed C++ build completed.
- The C++ regression tests passed. The aggregate remote CTest command reported
  six unrelated workspace failures: CRLF in `selfplay/loop.sh`, missing NumPy,
  and absent optional Python self-test scripts.
- Startup banners confirmed fair Searcher3, belief/chain off, 64 particles,
  the 7k combat VNet at alpha 0.3, native floor/win models, policy prior, and
  the V4 token-net gates.
- Results: A0 6/25 (24.0%), A5 9/25 (36.0%), A10 7/25 (28.0%), A15 3/25
  (12.0%), A20 1/25 (4.0%). All five CSVs contain 25 valid rows and the
  benchmark log has no runtime abort or assertion.

## Interpretation

**Inference:** the post-fix stack completes normally and produces plausible
ascension scaling, but this is not a paired candidate/control gate and does
not replace the 32-seed-per-ascension §153 result. A larger cap-compliant
rerun, or a human-controlled 160-seed reproduction, remains appropriate before
updating the headline baseline.

## Artifacts

- `build/rerun_2026-08-10_asc{0,5,10,15,20}_gates_1k_25.csv`
- `build/rerun_2026-08-10_gates_v2.log`

Status: completed; measurement recorded in `EXPERIMENTS.md` §166.

## 128-seed confirmation

The standard A0 block was then rerun on the same fixed stack:
`bestbench 1000 128 0 126700`, seeds 126700–126827. It completed with 60/128
wins (46.9%), mean floor 43.9, mean end HP 24.6, 29.33 CPU seconds/run, and
170.0 seconds wall time. The downloaded CSV contains exactly 128 distinct
rows covering the requested range, with no malformed rows or runtime abort.

**Inference:** this confirms successful execution at the standard confirmation
size. It is not a causal pre/post estimate against §153's 21.9% A0/32 result,
because the earlier per-seed control artifact is unavailable and the sample
block differs in size; the +25.0pp absolute difference must not be attributed
to the fixes alone.

Artifact: `build/rerun_2026-08-10_a0_gates_1k_128.csv` and its `.log`.

## Simulation-budget confirmation

The same 128 seeds and full-stack flags were run at two larger budgets:

- 3,000 sims: 66/128 wins (51.6%), mean floor 45.3, mean end HP 27.1,
  506.7 seconds wall time.
- 10,000 sims: 70/128 wins (54.7%), mean floor 44.7, mean end HP 29.8,
  1,486.9 seconds wall time.

Both CSVs contain the complete requested seed range with no malformed rows;
both logs are free of runtime aborts or assertions. The 10k arm therefore
adds 3.1 percentage points and four wins over 3k in this block, at about 2.93×
the wall time. This is a descriptive budget comparison, not a paired policy
comparison against another arm.

Artifacts: `build/rerun_2026-08-10_a0_gates_3k_128.csv` and
`build/rerun_2026-08-10_a0_gates_10k_128.csv`, with matching logs.
