# 2026-08-03 — V4 trainer throughput: GPU-resident state + fused value heads

Date: 2026-08-03
Session/task: Reduce `train_strategic_tok.py` wall time (~40 min for 40 epochs
on the 3.06M-row §73 Tier-B dataset) without changing training semantics.

## Decision

1. **GPU-resident state (default ON, per user decision).** After the fp16
   group-ordered state file is written/reused, `train_strategic_tok.py` and
   `train_strategic.py` upload it to VRAM once (`state_gpu`) and `fwd_rows`
   gathers rows on-device (~0.15 ms vs ~6-12 ms CPU mmap fancy-index per
   batch). Small arrays (action bits, cat/atype/screen/ent, gold_ge, probes)
   are uploaded once too in the V4 trainer; bit-unpack happens on GPU. Falls
   back to the CPU mmap path on OOM at upload time. Rationale: the CPU gather
   is the data-path bottleneck (6.5 ms/batch at 4096 rows vs 0.15 ms
   on-GPU); the fp16 file moves verbatim, so the loss is unchanged.
2. **Fused per-screen value/quantile heads in `strategic_tok_net.py`.**
   The 8 masked `v[mm] = self.vals[h](z[mm])` writes (source of
   `sum_and_scatter` index_put, DtoD copies, tiny 32×128-tile GEMMs) are
   replaced by full-batch head GEMMs + `gather` by `screen`:
   `vv = torch.stack([self.vals[h](s) for h in range(8)], 1)`, then
   `v = vv[arange, screen-1]`. Math-identical per row (verified: v within
   1.5e-8 = 1 ulp, qq/entity exact; the 8 value-head GEMMs are bitwise
   equal on the subset vs full batch). Rationale: masked per-head writes
   scatter rows into 8 tiny GEMMs and back.
3. **Entity embedding block reverted to the original masked writes.** The
   first uniform-lookup formulation computed all 3 entity tables
   (card/relic/potion) on every row including their backwards; the masked
   version only touches matching rows. Kept because it is cheaper in the
   training distribution (~60% non-entity rows) and it is the exporter's
   reference semantics.
4. **Eval chunk raised to 16,384 rows** (`STRAT_EVAL_CHUNK`; forward-only,
   no group constraint): 150 eval batches/epoch -> ~38. Modest but free.
5. **`STRAT_TOK_COMPILE=1` (opt-in, default off):** `torch.compile(mode=
   "reduce-overhead")` around the net. Not usable here: torch.compile's
   Triton codegen needs CPython dev headers (`Python.h`), which are absent
   and cannot be installed without sudo. Default off so the trainer never
   crashes on machines without headers; the try/except only guards the
   `torch.compile()` call, NOT the lazy first-forward compile, so the env
   var must only be set on machines where compilation is known to work.
6. **`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` set by default** in
   both trainers (setdefault, respects user override): the 2.9 GB (V4) /
   6.2 GB (V3) resident state plus attention intermediates fragment 8 GB
   VRAM otherwise; observed an OOM on a 144 MB alloc with ~2 GB free when
   another process (Slay the Spire 2, 718 MB) held memory.

## Rejected alternatives (measured)

- **fp16 autocast training:** step 62.4 -> 53.6 ms (1.16x) but logit/value/Q
  drift up to 1.2-1.4 absolute vs fp32 — far beyond the metric-equivalence
  band; rejected.
- **TF32 matmul (`torch.backends.cuda.matmul.allow_tf32`):** 62.4 -> 57.5 ms
  (1.08x) with fp rounding risk; rejected.
- **Bigger batch (8192/12288):** per-row cost is flat (0.064-0.067 rows/ms at
  4096/8192/12288) — the step is per-row kernel-bound, not launch-bound;
  no gain.
- **`segment_reduce` for the group logsumexp:** 1.79 ms vs 0.13 ms for the
  existing `scatter_reduce_ amax`; no change.
- **SDPA/flash attention:** changes numerics vs the C++ attention convention;
  out of scope for a runtime-only fix.

## Evidence

- Profiling (RTX 3060 Ti, free GPU): V4 step pre-change 69.0 ms/step
  (kernel self-time ~30 ms/3 steps + launch gaps); post-fusion ~62-64 ms
  with ~100 kernels, ~61 ms CUDA self-time — the step is per-row kernel
  bound (~15.5 us/row), NOT launch/FLOP-bound; data gather 6.45 ms -> 0.14 ms
  GPU-resident; V3 step 6.3 ms (data-gather-bound at 12 ms/batch).
- 40-epoch rerun (eager, post-fusion, batch 4096, GPU-resident state,
  `build/tok_runtime_check.pt`): held-out pol top-1 0.792 / val CE 0.4916 /
  Q MAE 16.81 vs recorded §75 0.790 / 0.492 / 17.00 — metric-equivalent
  (jitter ~0.002 CE expected: the group-CE `scatter_add_` uses nondeterministic
  atomic order).
- Export parity (`export_strategic_tok.py` on the new checkpoint): max err
  logit 2.18e-06, value 1.04e-06, Q 3.01e-06 — below §75's recorded parity.
- Wall time: 40 epochs ~38.5 min before this wave; the data-path + eval
  changes are expected ~48-53 s/epoch (~35 min) — the ~62 ms/step GPU kernel
  cost of the V4 architecture is the remaining dominant term (measured
  intrinsic, not an implementation artifact).

## Status and follow-up

- Implemented and verified for math identity + export parity + metric
  equivalence. The 40-epoch rerun (eager) predates the entity revert (which
  returns the code to the previously validated masked block).
- **Follow-up (same session): torch.compile is now ENABLED.** After the user
  installed `python3-dev`, `STRAT_TOK_COMPILE` defaults to ON with
  `mode="default"` (Triton fusion). Measured: step 67.2 -> 31.3 ms (2.15x);
  same-weights compiled-vs-eager forward diff ~4e-8 (numerically identical);
  steady-state epoch ~22 s (vs ~46 s eager, ~58 s pre-wave); epoch 1 includes
  ~12 s of one-time compilation. `reduce-overhead` (CUDA graphs) is NOT used:
  graph capture rejects the masked `index_put_` in the entity block
  (`RuntimeError: operation not permitted when stream is capturing`).
  `torch._dynamo.config.suppress_errors = True` makes any compile failure
  (e.g. missing headers on other machines) fall back to eager per graph.
  State dicts are saved/loaded via the unwrapped net (`_orig_mod.` key prefix
  would break `export_strategic_tok.py`). Export parity on a compiled-trained
  checkpoint: max err logit 3.78e-06, value 6.53e-07, Q 3.75e-06. Dynamo logs
  benign `aten.baddbmm` fake-tensor meta warnings during tracing.
- **Bug found and fixed during this follow-up:** an edit to route state dicts
  through the unwrapped net accidentally dedented the `if em["val_pol_ce"] <
  best_ce:` block OUT of the epoch loop, so best-checkpoint selection and
  epoch prints only ran after the loop (last epoch instead of best val CE).
  Restored indentation; verified via AST + rerun (epoch 1 and final epoch
  print, best state = best val CE).
- Bigger structural levers if runtime becomes critical: train with
  `STRAT_EPOCHS=30` (the val-CE tail 0.4958@30 vs 0.4916@40 is within noise).
