# Native Silver gate (2026-09-24)

Whole-run comparison of the Silver search ported onto the main engine
(`STS_NATIVE_SILVER=1`) against the vendored Silver backend on the standard
128-seed block. Ledger entry: [§348](../../ledger-06.md).

## Command

```bash
STS_NATIVE_SILVER=1 STS_SILVER_ADAPTIVE=1 bash tools/seed_guard.sh \
  one_combat bestbench 1000 128 0 126700 bestbench_native_adaptive_126700_128.csv
```

- Binary: Release `one_combat` from branch `claude/native-silver-searcher`
  at commit `f81eabb`, SHA-256
  `5b9adfa3d533e4644a4204115ebf0c03a34ed2a32966166d8859f49a08c8ed5e`.
- 4-core container, 4 OpenMP threads, ascension 0, project-fair, native OOC
  trees, keys skipped. Adaptive retained-root policy (500 → 10,000).
- Baseline: the vendored Silver run of §340
  (`../silver_handoff_timing_2026-09-24/bestbench_adaptive_126700_128.csv`,
  commit `2a602f6`, same command without `STS_NATIVE_SILVER`).

## Files

- `bestbench_native_adaptive_126700_128.csv` and `.meta.json`: results and
  run metadata.
- `bestbench_native_adaptive_126700_128.log`: run log.
- `paired_summary.py` / `paired_summary.txt`: paired analysis against the
  baseline (no third-party packages).

## Result

```
vendored wins 83/128, native wins 86/128
paired difference +2.3 pp, normal 95% CI [-6.2, +10.9] pp
discordant seeds: native-only 17, vendored-only 14, McNemar z = +0.54
mean floor vendored 48.26, native 47.81
```

CPU per run: native 37.37 s, vendored 38.05 s (wall 1,210 s vs 1,240 s).
