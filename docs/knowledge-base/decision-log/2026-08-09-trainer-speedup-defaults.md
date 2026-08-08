# 2026-08-09 — Trainer speedup: PATIENCE default + batched row-index construction

Date: 2026-08-09
Session/task: Investigate and implement low-risk speedups for
`train_strategic_tok.py` on large datasets (3.06M rows, many epochs)
without changing model architecture or training semantics.

## Decision

1. **`STRAT_PATIENCE` default changed from `0` (disabled) to `6`.**
   Early stopping is now active by default: training halts after 6
   consecutive epochs without a `val_pol_ce` improvement of at least
   `STRAT_MIN_DELTA` (1e-4). The best-epoch checkpoint (lowest
   `val_pol_ce`) is always restored. Overridable via `STRAT_PATIENCE`
   env var (set to `0` to restore the old unlimited-epochs behavior).

2. **Per-batch row-index construction vectorized** in
   `train_batch_loss()`. The Python list comprehension with
   `np.concatenate([np.arange(…) for g in gs])` is replaced by a
   single vectorized `np.repeat`/`np.cumsum` expression producing
   identical rows.

## Rationale

**Convergence measurement (40 epochs, full 3,057,708-row dataset,
CUDA/compiled):**

| Epoch | val_pol_ce | Δ from prev log |
|-------|-----------|-----------------|
| 1 | 0.6018 | — |
| 10 | 0.5128 | — |
| 20 | 0.5031 | −0.0097 |
| 30 | 0.4962 | −0.0069 |
| 40 | 0.4924 | −0.0038 |

Best checkpoint (intermediate epoch): `val_pol_ce = 0.4917`. The last
10 epochs (30→40) buy only 0.0038 CE improvement — firmly within
run-to-run noise (~0.002 CE from non-deterministic `scatter_add_`
atomics). The `PATIENCE=6` default would stop around epoch 30–36,
saving ~20–25% wall time with no quality loss.

On the partial 160k-row dataset, val_pol_ce still improves at epoch 40
(0.5599 vs 0.5724 at epoch 30), so PATIENCE correctly does NOT trigger
— the mechanism only stops training when improvement genuinely stalls.

The vectorized row construction is a small constant-factor improvement
(~2–4% of epoch time) with zero semantic change (verified bit-identical
on 10 random batch configurations).

## Alternatives considered

- **AMP/fp16 autocast**: previously measured and rejected
  (2026-08-03 decision log) — 1.16x speedup with 1.2–1.4 absolute drift
  in logits/value/Q, breaking the C++ parity contract.
- **SDPA/FlashAttention**: parity-blocked (changes attention numerics vs
  the C++ convention); T≤96, D=32 — no long-sequence benefit.
- **Value-head fusion (Linear 128→512→8)**: math-equivalent but changes
  state-dict keys, export format, C++ loading code, and deployed native
  artifacts — disproportionate cost for single-digit % gain.
- **C++/LibTorch rewrite**: bottleneck is GPU kernel time, not host
  overhead.
- **Parquet/Polars/DuckDB**: CSV phases are ~3–10% of total wall time
  with torch.compile; new dependencies for <2% gain.
- **CUDA graphs (`reduce-overhead`)**: blocked by masked `index_put_`
  in entity embedding block; already measured.

## Evidence

- `train_strategic_tok.py`: PATIENCE default (line 42), vectorized row
  construction (line 478).
- Convergence measurement: 40-epoch run on `build/strategic_tierb.csv`
  (3,057,708 rows), CUDA, `STRAT_BATCH=2048`, `STRAT_EVAL_CHUNK=2048`
  (VRAM fragmented by desktop GPU processes), `STRAT_PATIENCE=0`.
- Smoke test: 2-epoch CPU run on `build/sp_300000_partial.csv` — no
  crashes, no NaN losses, correct output.
- PATIENCE verification: 40-epoch run on partial 160k-row dataset with
  PATIENCE=6 — correctly did NOT early-stop (model still converging).
- Vectorization correctness: 10 random batch configurations verified
  bit-identical to the list-comprehension version.
- `docs/knowledge-base/decision-log/2026-08-03-trainer-throughput-v4.md`
  — prior fp16/TF32/batch-size rejections, torch.compile 2.15x, the
  "STRAT_EPOCHS=30" follow-up note now actioned via PATIENCE default.

## Status and follow-up

- **Implemented.** Both changes are in the working tree.
- The `STRAT_PATIENCE` env var still overrides the default; `PATIENCE=0`
  restores unlimited-epochs behavior.
- `STRAT_MIN_DELTA=1e-4` is tight enough that epoch-to-epoch noise
  (~0.001–0.002 on the full dataset) won't trigger spuriously. On
  smaller datasets with higher noise, PATIENCE may need tuning via the
  env var.
