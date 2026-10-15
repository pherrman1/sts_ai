# Deterministic selected-child reroot diagnostic (2026-09-21)

This is a bounded correctness and sanity check, not a Silver policy-quality promotion. Only the frozen 64-case DEV cohort was used. No HOLDOUT or 10k run was made.

- Input: `../silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`, SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
- Functional baseline: `289e1ab96d4a022d894756b9108bb081e34be8a3` (`baseline-uninstrumented.jsonl.gz`).
- Baseline diagnostics: temporary value-only instrumentation on the baseline matching behavior, before the selected-child fix (`baseline-diagnostic.jsonl.gz`). Its 64 action traces match the uninstrumented baseline exactly.
- Earlier corrected functional SHA: `ea8a728802d3cbce3222e34cdc55a0a19672e0b8` (`corrected-diagnostic.jsonl.gz`).
- Safety-corrected SHA after merge of `main` at `eb7c5fa76f1373c2f27ad0ec272a2c8e91a453c8`: `db4edf1cfeb7f8c81bd384c4f02d72f99d7bdc8c` (`pre-fpu-merge-diagnostic.jsonl.gz`; executable SHA-256 `ff1b458d1b5e4de3880112d6ac9ad0efdf5cf48a8965498e27a4c7a2e78ffdb2`).
- Final functional SHA after `main` advanced again to `149954a3c7ef451616611afacce59f3891d09484` with default-off Silver FPU work: `ca45781abed16db3e440a8e20dedfe70be8759d4` (`final-diagnostic.jsonl.gz`; executable SHA-256 `6e4a635dce114970eb4aef6d303498da20588d1d3297abb3611c2f129defea64`). The subsequent evidence update does not change replay behavior.
- All runs: Release GCC, `OMP_NUM_THREADS=4`, 1,000 simulations per decision, allocated reuse cap 32,768, adaptive/exact-lock/rho off.

The final run repeated the corrected command on frozen functional SHA `ca45781a`, with `--internal-fpu` absent (default off):

```sh
OMP_NUM_THREADS=4 bash tools/seed_guard.sh build/linux-gcc-release-ccache/silver_hard_combat_replay docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --reroot-diagnostics > final.jsonl
```

To recalculate `summary.json` from the compressed raw rows:

```sh
python3 docs/experiments/evidence/silver_deterministic_reroot_20260921/summarize.py
```

`baseline-diagnostic.jsonl.gz` predates the added initial-root record. All runs have 64 initial roots; the baseline archive records only its 2,168 subsequent reroot attempts, while the corrected, pre-FPU-merge, and final archives also record 64 `no_predecessor` initial decisions. The summarizer excludes initial roots from deterministic and stochastic attempt counts.

| Measure | Baseline | Earlier corrected | Final functional SHA |
| --- | ---: | ---: | ---: |
| Deterministic attempts / exact-or-equivalent reroots | 1,287 / 1,287 | 1,287 / 1,287 | 1,287 / 1,287 |
| Deterministic cap blocked / candidate missing | 0 / 0 | 0 / 0 | 0 / 0 |
| Stochastic attempts / candidate missing | 881 / 541 | 881 / 541 | 881 / 541 |
| Selected edges without child | 0 | 0 | 0 |
| Wins | 51/64 | 51/64 | 51/64 |
| Mean terminal HP fraction | 0.3440911508 | 0.3440911508 | 0.3440911508 |
| Nodes per simulation | 0.9246209677 | 0.9246209677 | 0.9246209677 |
| Exact reroots / cap fallbacks | 1,627 / 0 | 1,627 / 0 | 1,627 / 0 |
| Mean inherited visits per reroot attempt | 535.6849631 | 535.6849631 | 535.6849631 |
| Action-trace discordance versus prior run | — | 0/64 | 0/64 |

All 64 cases completed with `status=ok` in each run. The pre-FPU-merge rows match the earlier corrected rows in every field except elapsed `wall_seconds`. The final run adds seven FPU/depth/timing telemetry fields from the newly merged replay seam; all fields shared with the pre-FPU run except elapsed `wall_seconds` match on all 64 rows. The summarizer reports both comparisons. No deterministic hand-order, equivalent-copy UID, or other selected-child mismatch occurred in this cohort. The hand-order and cached chance-action failures are covered by the focused bridge fixture. Stochastic misses remain outside this task's correctness gate. This is bounded DEV confirmation, not holdout, whole-run, or live-game qualification.

The compressed archives use `gzip -n` to omit local filename and timestamp metadata. Their SHA-256 digests are:

| Archive | SHA-256 |
| --- | --- |
| `baseline-uninstrumented.jsonl.gz` | `f62e27b609f9eb1e52cca0612af7f22b7aaff0fa4afe959d6b25d65420f70e24` |
| `baseline-diagnostic.jsonl.gz` | `858b9fc9896141f5dd7716344c6ed41b505b1f3c630bf14bc29b3a314780bdac` |
| `corrected-diagnostic.jsonl.gz` | `3751354e26bf6b2077402ba2b1bfa7bdfddebf29e4c0fa33b1b02ac436e9d1ed` |
| `pre-fpu-merge-diagnostic.jsonl.gz` | `fc102c6dace095ec60a78e9e953be5e21ada9ace5d4c1b34cac3de942fd3884b` |
| `final-diagnostic.jsonl.gz` | `ff812c6e36e8690b81d0e861c58f0406ce6e24757c0e86bc06cd8a732b6bebaa` |
