<!-- Relayed by the run's thread from the PC, 2026-11-20 22:06 CET; the raw rows and the full profile files are on the PC in amber_scratch/. -->

# #1140 --packed-heads live result, amber_scratch 2026-11-20 (CONFOUNDED with --force-potions)

Restart 21:29 CET (c5_repo @d12d4d2e). --ooc-canon crashed 21:31 (selfplay.py:1664 `oc` overwritten in canon block ~l.1803; fix requested from force-moves thread). Since 21:40 PID 1178460 with --packed-heads + --force-potions, no --ooc-canon. Other flags: amber2-root, A5, no pin, --attn-row-bounds, 10M replay.
StS2 ran on the PC until ~21:56, so rows before 21:58 are not usable.

## Gate profile infer_profile_ph_20261120 (ckpt_738152, --batches 3) ms/batch baseline / row_bounds / packed_heads
- real: 5.054 / 3.799 / 2.750
- real_Rtight: 3.771 / 3.120 / 2.580
- uniform: 3.392 / 3.479 / 2.642
All 9 rows finite, same_argmax 0.996-1.000; max_diff logits <= 0.0195, F <= 0.00031, outcome_dist <= 0.0016, ehp <= 0.032, hp_floor <= 0.0015. Gate passed.

Kernel table (real, batch 0, 10 batches) row_bounds: CUDA 33.0 ms (CPU 22.5): _ffn 9.585 (29.0 %), _attn_kernel_rows 8.022 (24.3 %), _ln_linear 5.630 (17.1 %), triton_ 4.461 (13.5 %, 170 calls), gemm relu 1.929, sm80 96x64 1.884 (40), gemvx 0.703, sm80 64x96 0.071.
packed_heads: CUDA 26.8 ms (CPU 16.3): _ffn 9.902 (37.0 %), _attn_kernel_rows 7.273 (27.1 %), _ln_linear 4.628 (17.3 %), gemm relu 2.259 (8.4 %), triton_ 1.404 (5.2 %, 150), sm80 96x64 0.203 (30), sm80 64x96 0.071, gemvx 0.065.

## Live, without StS2 (22:02:40-22:05:12) vs before restart (21:25:07-21:27:38, no packed-heads, no force-potions)
| | before | after |
|---|---|---|
| moves/s | 10,639 | 10,051 (-5.5 %) |
| pos/s | 209,161 | 195,538 (-6.5 %) |
| infer forward ms/s | 330.9 | 354.3 |
| infer wait_pack ms/s | 411.3 | 425.0 |
| gpu_ms infer / train | 808.5 / 487.0 | 678.2 / 429.5 |
| batches/s, rows/batch | 160.0 / 1,307 | 150.1 / 1,303 |
| cache_hits/s | 40,418 | 38,465 |
| worker_cpu search/step/encode | 6.25 / 2.66 / 1.46 | 5.97 / 2.55 / 1.38 |
| train take_add / idle / sync / fwd_bwd | 57.9 / 410 / 286 / 136 | 53.9 / 473 / 240 / 126 |
dmon after: SM mean 70.8 % (min 33, max 93), mem 44 %. Only desktop apps on GPU.
PC reading: GPU infer time -16 % and SM util down, but throughput -6 %; CPU side (wait_pack, worker CPU) now the limit. Confounders: --force-potions changes play; before-rows from another phase (A5 rolling 40 % vs 42 %); short window. Clean verdict needs A/B with only --packed-heads toggled.
State: A5 rolling 42.3 % over 10,143 runs; MemAvail 3.6 GB.
Raw rows on PC: amber_scratch/pre_1139_1140_rows_20261120.jsonl, post_ph_rows_20261120.jsonl; full profile files infer_profile_ph_20261120.json/.log there.
