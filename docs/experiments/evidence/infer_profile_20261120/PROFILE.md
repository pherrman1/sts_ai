# Inference GPU profile on real states, PC, 2026-11-20 17:14 CET

Relayed text of `tools/az_bench/infer_profile.py` (main 02e75f8c) on the PC (RTX 3060 Ti, torch 2.5.1+cu121), checkpoint
`amber_scratch/ckpt_672852.pt`, the run's saved 10M window, 1,314 rows per batch; then three report rows of the live
run after its restart and `nvidia-smi dmon`. The raw files are on the PC in `amber_scratch/`.

```
# Relayed from PC (amber_scratch/infer_profile_20261120.log, run 2 --batches 1, rc 0). Kernel names shortened in transfer; raw file on PC.
window: samples 10M, mean 35.2, p50 35, p90 51, p99 67, max 107, share>64 1.65 %, >128 0; load_s 10.3
real batch 0: ms_per_batch 5.471, launch_ms 2.561, us_per_row 4.163, us_per_token 0.1156
# top CUDA kernels, real, batch 0 (10 batches)   [Self CUDA, %, calls]
_attn_kernel                    19.990ms  37.32%   60
_ffn_kernel                     10.990ms  20.52%   60
triton_                          8.357ms  15.60%  170
sm80_xmma_gemm_f16f16_f16f32_f32_tn_n_tilesize96x64x32_stage4_warpsize2x2x1_tensor16x8x16_kernel   5.766ms  10.76%  40
_ln_linear_kernel                4.491ms   8.38%   60
ampere_fp16_s1688gemm_fp16_128x128_ldg8_relu_f2f_stages_32x1_tn   2.416ms   4.51%  10
internal::gemvx::kernel<int,int,__half,...>   698.784us  1.30%  10
cutlass_80_wmma_tensorop_f16_s161616gemm_f16_32x32_32x1_tn_align8   218.972us  0.41%  60
direct_copy_kernel_cuda (unrolled_elementwise)   189.536us  0.35%  50
reduce_kernel<512,1,...sum...>        76.352us  0.14%  20
sm80_xmma_gemm...tilesize64x96x32...  76.318us  0.14%  10
elementwise_kernel<128,2,BinaryFunctor...>  76.193us  0.14%  20
softmax_warp_forward<...,6,...>       56.477us  0.11%  20
softmax_warp_forward<...,8,...>       50.976us  0.10%  10
cutlass_75_wmma...64x2_tn_align1    50.077us  0.09%  10
cutlass_80_wmma...64x1_tn_align8    36.321us  0.07%  10
launch_clamp_scalar               15.648us  0.03%  10
BUnaryFunctor<float,...>            13.568us  0.03%  10
cuLaunchKernel (CPU)   1.047ms   2.43% CPU   350
cudaOccupancyMaxActiveBlocksPerMultiprocessor (CPU)  10.763us  0.02%  10
cudaLaunchKernel (CPU) 776.421us  1.80% CPU   290
cudaOccupancyMaxActiveBlocksPerMultiprocessorWithFlags (CPU)  40.590us  0.09%  80
cudaDeviceSynchronize (CPU)  41.242ms  95.65% CPU  2
Self CPU time total: 43.116ms   Self CUDA time total: 53.569ms
real_Rtight 4.011 / 1.866 / 3.052 / 0.0848; short_T64 4.157 / 1.988 / 3.208 / 0.0903; short_Tbig 5.35 / 2.514 / 4.128 / 0.1162; uniform 3.698 / 1.746 / 2.814 / 0.0782  (ms_per_batch / launch_ms / us_per_row / us_per_token)

# ---- run 1 (default --batches 4) crashed: amber_scratch/infer_profile_20261120_try1_crash.log ----
load_s 13.1
batch 0: real 5.488 / 2.565 / 4.177 / 0.116; real_Rtight 4.307 / 2.016 / 3.278 / 0.091; short_T64 3.676 / 1.728 / 2.836 / 0.0799; short_Tbig 4.997 / 2.335 / 3.856 / 0.1085; uniform 3.717 / 1.743 / 2.829 / 0.0786
  (profile: same kernel order, Self CPU 45.444ms, Self CUDA 55.705ms)
batch 1: real 5.007 / 2.342 / 3.81 / 0.108 (rows 1314, live 46347, tok_max 82); real_Rtight 3.996 / 1.875 / 3.041 / 0.0862; short_T64 3.701 / 1.733 / 2.854 / 0.082 (rows 1297); short_Tbig 5.022 / 2.357 / 3.872 / 0.1112 (rows 1297)
Traceback (most recent call last):
  File "tools/az_bench/infer_profile.py", line 280, in <module>  sys.exit(main())
  File "tools/az_bench/infer_profile.py", line 246, in main  h, info = flat_input(rr, rp, tp, apn, step_n)
  File "tools/az_bench/infer_profile.py", line 104, in flat_input  h["a_mask"][:B, :A] = np.arange(A)[None, :] < na[:, None]
ValueError: could not broadcast input array from shape (1314,96) into shape (1324,96)
(batch 1, variant uniform: B 1324 vs na 1314)

# ---- live run on 02e75f8c, PID 1839493 since 17:14:17 CET, 3 rows after ~10 min ----
{"time": "2026-11-20 17:24:32", "moves_per_s": 10274, "positions_per_s": 200077, "infer_tokens_per_row": 36.42, "infer_tok_bucket_batches": {"56": 2, "64": 1, "80": 1765, "96": 2719, "128": 163}, "infer_rows_per_batch": 1301.1, "infer_batches_per_s": 153.6, "ascension": 0}
{"time": "2026-11-20 17:25:02", "moves_per_s": 9883, "positions_per_s": 191882, "infer_tokens_per_row": 36.51, "infer_tok_bucket_batches": {"64": 4, "80": 2517, "96": 1857, "128": 13}, "infer_rows_per_batch": 1319.6, "infer_batches_per_s": 145.2, "ascension": 0}
{"time": "2026-11-20 17:25:32", "moves_per_s": 9867, "positions_per_s": 192529, "infer_tokens_per_row": 36.14, "infer_tok_bucket_batches": {"48": 1, "56": 3, "64": 2, "80": 2248, "96": 2138, "128": 12}, "infer_rows_per_batch": 1322.4, "infer_batches_per_s": 145.7, "ascension": 0}
nvidia-smi dmon -s u -c 30 (17:25-17:26): SM mean 96.7 % (min 73, max 100), mem BW 58.6 %.
```
