# Deterministic selected-child reroot diagnostic (2026-09-21)

This is a bounded correctness and sanity check, not a Silver policy-quality promotion. Only the frozen 64-case DEV cohort was used. No HOLDOUT or 10k run was made.

- Input: `../silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`, SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
- Functional baseline: `289e1ab96d4a022d894756b9108bb081e34be8a3` (`baseline-uninstrumented.jsonl.gz`).
- Baseline diagnostics: temporary value-only instrumentation on the baseline matching behavior, before the selected-child fix (`baseline-diagnostic.jsonl.gz`). Its 64 action traces match the uninstrumented baseline exactly.
- Corrected functional SHA: `ea8a728802d3cbce3222e34cdc55a0a19672e0b8` (`corrected-diagnostic.jsonl.gz`). The evidence commit adds only these artifacts and the summarizer.
- All runs: Release GCC, `OMP_NUM_THREADS=4`, 1,000 simulations per decision, allocated reuse cap 32,768, adaptive/exact-lock/rho off.

The corrected run command was:

```sh
OMP_NUM_THREADS=4 bash tools/seed_guard.sh build/linux-gcc-release-ccache/silver_hard_combat_replay docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --reroot-diagnostics > corrected.jsonl
```

To recalculate `summary.json` from the compressed raw rows:

```sh
python3 docs/experiments/evidence/silver_deterministic_reroot_20260921/summarize.py
```

`baseline-diagnostic.jsonl.gz` predates the added initial-root record. Both runs have 64 initial roots; the baseline archive records only its 2,168 subsequent reroot attempts, while the corrected archive also records 64 `no_predecessor` initial decisions. The summarizer excludes initial roots from deterministic and stochastic attempt counts.

| Measure | Baseline | Corrected |
| --- | ---: | ---: |
| Deterministic attempts / exact-or-equivalent reroots | 1,287 / 1,287 | 1,287 / 1,287 |
| Deterministic cap blocked / candidate missing | 0 / 0 | 0 / 0 |
| Stochastic attempts / candidate missing | 881 / 541 | 881 / 541 |
| Selected edges without child | 0 | 0 |
| Wins | 51/64 | 51/64 |
| Mean terminal HP fraction | 0.3440911508 | 0.3440911508 |
| Nodes per simulation | 0.9246209677 | 0.9246209677 |
| Exact reroots / cap fallbacks | 1,627 / 0 | 1,627 / 0 |
| Mean inherited visits per reroot attempt | 535.6849631 | 535.6849631 |
| Action-trace discordance | — | 0/64 |

All 64 cases completed with `status=ok` in both runs. No deterministic hand-order, equivalent-copy UID, or other selected-child mismatch occurred in this cohort. The hand-order failure is covered by the focused bridge fixture. Stochastic misses remain outside this task's correctness gate.

The compressed archives use `gzip -n` to omit local filename and timestamp metadata. Their SHA-256 digests are:

| Archive | SHA-256 |
| --- | --- |
| `baseline-uninstrumented.jsonl.gz` | `f62e27b609f9eb1e52cca0612af7f22b7aaff0fa4afe959d6b25d65420f70e24` |
| `baseline-diagnostic.jsonl.gz` | `858b9fc9896141f5dd7716344c6ed41b505b1f3c630bf14bc29b3a314780bdac` |
| `corrected-diagnostic.jsonl.gz` | `3751354e26bf6b2077402ba2b1bfa7bdfddebf29e4c0fa33b1b02ac436e9d1ed` |
