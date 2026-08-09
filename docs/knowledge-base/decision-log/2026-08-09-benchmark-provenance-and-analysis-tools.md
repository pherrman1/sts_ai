# 2026-08-09 — Benchmark provenance and OOC analysis tools

Date: 2026-08-09
Session/task: Continue the honest-V4 Wave 0 correctness/analysis handoff.

## Decision

`bestBench` writes machine-readable JSON-lines provenance to
`<resultsFile>.meta.json` when a results file is requested. The sidecar records
objective, argv, seed block, explicit `STS_COLLECT_KEYS` state, search settings,
OOC settings, model load paths/status, and timestamp without changing game
behavior.

Add strict consumers for the existing deployment artifacts:
`tools/analyze_strategic_trace.py` summarizes `STS_OOC_STRATEGIC_TRACE`,
`tools/vnet_distribution_shift.py` accepts the `vnetPred` query-log schema,
and `tools/analyze_screen_ablation.py` summarizes full-minus-screen arms by
paired seed. The screen harness uses the corrected honest V4 token artifact and
requires an explicit Act-3/Heart objective through `STS_COLLECT_KEYS`.

## Rationale

**Inference:** the human BEST banner is insufficient provenance for later
causal analysis, while a sidecar can be written at the existing results-file
boundary without affecting benchmark policy behavior.

**Inference:** analysis tools should consume producer headers strictly and keep
actual paired seed sweeps separate from cheap self-tests.

## Evidence

- `apps/one_combat.cpp::bestBench` writes the sidecar.
- `tools/analyze_strategic_trace.py`, `tools/vnet_distribution_shift.py`, and
  `tools/analyze_screen_ablation.py` each provide focused self-tests.
- `run_screen_ablate.sh` uses `STS_OOC_STRATEGIC_TOK_NN` and validates
  `STS_COLLECT_KEYS` as 0 or 1.
- `cmake --build build --target one_combat -j2` passed.
- Sidecar smoke: `bestbench 20 2 0 0 build/wave0c_smoke.csv` produced a valid
  `build/wave0c_smoke.csv.meta.json` with `collectKeys=false`.
- Analyzer self-tests and `bash -n run_screen_ablate.sh` passed.

## Status

Implemented. Full 64/128-seed gameplay gates and six-arm ablations remain
explicit benchmark experiments, not automated self-tests.
