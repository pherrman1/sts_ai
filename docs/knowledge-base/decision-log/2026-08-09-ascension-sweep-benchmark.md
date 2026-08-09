# 2026-08-09 Ascension sweep benchmark (V4 skewfix + S3 + 7k-vnet)

## Decision

Benchmarked the current recommended configuration (V4 skewfix gates + S3 fair
−belief−chain @64p + 7k-tuned vnet @α=0.3 + 1k sims) at ascensions A0–A20
on the GCP server sts-test (24 threads, 32 seeds each). Also ran a no-gates
baseline and a `STS_STOP_AFTER_ACT=3` comparison for §148 compatibility.

## Rationale

The current-baselines.md recommended configuration had no actual measurement
on the current binary. The `32281a2` key-collection commit changed the
benchmark horizon from Act 3 to Act 3+4, making all prior baselines
non-comparable. A measurement was needed to establish the current state.

## Evidence

- **A0 with Act 4 (current default):** 21.9% (7/32), Wilson 95% CI [9.9%, 40.4%].
  No-gates baseline: 0/32 (but 4/64 = 6.3% across two blocks).
- **A0 Act 3 only (`STS_STOP_AFTER_ACT=3`):** V4 gates 31.2% (10/32),
  no gates 37.5% (12/32 — reproduces §148 24/64 exactly on overlapping seeds).
- **V4 gates reverse sign on S3+vnet at Act 3** (−6.3pp vs no gates) but are
  **essential for Act 4** (+15.7pp delta). **Inference:** the V4 card-reward
  gate picks cards that help survive Spear & Shield / Heart at the expense of
  immediate Act 3 boss performance.
- **Ascension scaling:** A5 ∼12.5%, A10 12.5%, A15 9.4%, A20 0.0%.
- CPU s/run drops with ascension (27.8 → 11.4) as runs end earlier.
- Total wall time: ~4 min for 5-ascension sweep; ~12 min for full suite.

## Alternatives considered

- **STS_STOP_AFTER_ACT=3 for the headline:** rejected — the binary now plays
  Act 4 by default, and the baseline should reflect actual behavior. The
  Act-3-only number is kept as a secondary reference for §148 compatibility.
- **Larger seed counts:** rejected — 32 seeds was the user's request. CIs are
  wide; 128/256-seed follow-up is an open item.

## Status

- Recorded in EXPERIMENTS.md §153 and current-baselines.md.
- CSVs: `build/asc{0,5,10,15,20}_1k_32.csv`, `build/asc{0,5,10,15,20}_nogates_1k_32.csv`,
  `build/asc0_nogates2_1k_32.csv`, `build/asc0_stopact3_{gates,nogates}_1k_32.csv`.
- Open: 128/256-seed gate, 3k win-point measurement, investigation of V4
  sign-flip on S3+vnet.
