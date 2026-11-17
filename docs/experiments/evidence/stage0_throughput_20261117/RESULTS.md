# Stage 0 throughput: running table

PC = Philipp's pop-os (Ryzen 5 7500F 6c/12t, RTX 3060 Ti 8 GB, torch 2.5.1+cu121). Cloud = 4-core container.
Positions = net leaf evaluations. Amber Eye reference: ~800k pos/s (8c/16t, 14 workers, custom kernel ~75 % MFU).
Decision rule: >= 300k GO, 100k-300k stage 1 with 500k games, < 100k STOP.

| # | Change (commit) | Where | CPU us/pos (worker) | GPU-only pos/s (0.44M) | End-to-end pos/s | Bottleneck |
|---|---|---|---|---|---|---|
| 0 | GPU forward, eager bf16 (df4e87bc) | PC | - | 98k (Amber 0.44M fp16) | - | - |
| 1 | torch.compile (e8dbcc5b) | PC | - | 200k (0.44M), 140k (1.2M), 45k (5M) | - | - |
| 2 | old encoder combatTokEncodeRoot (579b6881) | cloud | 150 encode + 4-5 sim | - | ~6.5k / thread | encoder |
| 3 | E2E driver, stub encoder, fake net (53a95887) | cloud 3 workers | 8.4 | - | 208k (fake net) | CPU (4 cores) |
| 4 | native AmberEncoder #1077 (b4e6d05e) | cloud 3 workers | 9.0 (encode 2.1) | - | 207k (fake net) | CPU |
| 5 | E2E PC, stub encoder, fake net, 10 workers (53a95887) | PC | 10.0 | - | 574k (fake net) | - |
| 6 | E2E PC, native encoder, fake net, 10 workers (e77670cd) | PC | 11.0 (encode 2.3) | - | 551k (C++), 496k (via Python) | - |
| 7 | E2E PC, native encoder, AmberNet 0.44M eager fp16, segmented batches, 2 batchers | PC | 13.0 | ~90-98k synthetic | 53k (batch ~1260 rows, 42 ms) | GPU |
| 8 | flat bucketed batches, eager, 2 batchers (b72dabf9) | PC | 14.8 | - | 37k (rows 1267 padded to 1944, 64 token slots) | GPU (padding) |
| 9 | flat + torch.compile, 1 batcher (b72dabf9) | PC | 12.9 | - | **69k** (1280 rows padded to 2048, 16.9 ms) | GPU (padding) |
| 9b | same + CUDA graphs | PC | 12.8 | - | 68k (no gain) | GPU |
| 9c | same, 1.2M net | PC | 13.5 | - | 48k | GPU |
| 9d | flat + compile, 2 batchers | PC | - | - | hangs (compile in 2 threads) | - |
| 10 | full batches (512 games/worker, min-batch = batch = 2048), tight token buckets, sort-window 4 (e325609c) | PC | 24.6 | - | 105k (1536 of 2048 rows, 46 slots, 12.5 ms) | GPU |
| 10b | same, 2 batchers + precompile (36 shapes, 134 s) | PC | - | - | hangs even without in-run compile | - |
| 10c | batch 4096, 820 games/worker, sort-window 2 | PC | 25.0 | - | 96k (3074 of 4096 rows, 27.3 ms) | GPU |
| 10d | **as 10, sort-window 1** | PC | 19.2 (step 5.3, encode 2.4, search 11.5) | ~135k (2048 rows / 15.2 ms) | **116.5k** (2048 of 2048 rows, 56 slots, 15.2 ms; wait 2.3 ms) | GPU |
| 11 | forward_profile 2048x56x32 fp16 compiled (84848f1e): ref / sdpa / half / sdpa_half | PC | - | 149k / 172k / 92k / **188k** (10.9 ms); max err vs fp32 ~1e-3 logits | - | GPU: Triton elementwise 48-56 %, GEMM ~40 %, attention 11-13 % |
| 11b | e2e --sdpa (2 batchers) | PC | 20.3 | - | 115.5k (1802 of 2048 rows, wait 7.3 ms) | fill |
| 11c | e2e **--sdpa --half** (2 batchers; 2 batchers no longer hang without --precompile) | PC | 20.2 | - | **123.2k** (1750 rows, ~125k at the end) | fill / GPU |
| 12 | **--pipeline** (double-buffered, 1 batcher) + sdpa + half, 512 games/worker (ab9f79b7) | PC | 17.6 | - | 159.3k (1874 rows, wait 6.3 ms) | workers (too few games in flight) |
| 12b | same, **768 games/worker** | PC | 19.2 (step 5.3, encode 2.5, search 11.4) | 188k (row 11) | **173.8k** (2048 rows, wait 2.6 ms; 172-175k steady) | GPU |
| 13 | forward_profile packed_half (294f599c), live 37.8 of 56 slots | PC | - | 198k (10.3 ms) vs sdpa_half 188k | - | GPU: zero fill + scatter 18 %, GELU 12 %, attention 14 % |
| 14 | **--pack-step 2048** + sdpa + half + pipeline, 512 games (294f599c) | PC | 17.4 | - | 187.1k (1881 rows, wait 6.2 ms) | workers (games in flight) |
| 14b | same, 768 games/worker; live 33.2 tokens / 4.5 actions per row of 56 / 16 slots | PC | 18.9 | 198k (row 13) | **189.9k** (2048 rows; 194-196k steady) | GPU |
| 14c | same, 2 batchers without pipeline | PC | - | - | error: dynamo "FX trace of a dynamo-optimized function" (concurrent compile) | - |
| 15 | forward_profile gpacked_half (unpack by gather, 5529d628) | PC | - | **207k** (9.9 ms), +5 % vs packed_half | - | GPU: attention 14.5 %, GELU 13.5 %, SDPA input prep 11.9 % |
| 15b | max-autotune-no-cudagraphs | PC | - | 206k (no gain: "Not enough SMs to use max_autotune_gemm") | - | - |
| 15c | e2e as 14b + --pack-gather | PC | 19.1 | 207k (row 15) | 189.6k (199-200k at the end); no measurable gain over 14b | GPU |
| 16 | torch_tensorrt 2.5.0 / TRT 10.3 backend (9695f3df, venv) | PC | - | gpacked_half 166k, sdpa_half 122k (vs inductor 206k); max err ~0.5 logits: **unusable** | - | - |
| 16b | Emmy | PC | - | not run: no nvcc / CUDA toolkit on the PC (Python 3.12.3 ok) | - | - |
| 17 | attention as plain matmuls + fp32 softmax (3593d67a) | PC | - | 191k vs gpacked_half 208k (-8 %) | - | - |
| 17b | Emmy 0.3.25 in venv on torch 2.5.1 | PC | - | fails: KeyError 'backed_size_oblivious' (needs newer torch); pip nvcc 12.1 wheel has no nvcc | - | - |
| 18 | fused LayerNorm+FFN+residual Triton kernel (66b2e91b), BM 32/64/128 | PC | - | 177k / 179k / 170k vs 207k: graph broke into 5 eager pieces; the kernel itself 1.2 ms/batch vs ~4 ms for LN+GEMM+GELU+GEMM | - | - |
| 19 | **fused FFN as custom op** (68e153dd), BM 64 | PC | 19.3 | **263k** (7.8 ms) vs 207k | **233.5k** (mostly 242-248k per 5 s; 2 dips) | GPU: FFN kernel 18 %, attention 17.6 %, SDPA prep 14.7 % |
| 20 | **varlen Triton attention on packed tokens** (b9210adb) + fused FFN | PC | 21.2 | **392k** (5.2 ms) | **342.0k** (mostly 348-358k per 5 s, 378-380k at the end; 1 dip to 175k); GPU 99 %, CPU ~5.8 of 12 threads | GPU + batcher (wait 2.9 ms ≈ forward 3.0 ms) |
| 21 | packer: no dead-slot zeroing (721028fc), 10 workers x 768, 120 s | PC | 19.1 | 392k | **375.9k** (384-390k steady, 2 external-looking dips); pack 2.36 ms/batch | GPU 99 % ≈ batcher (pack 2.4 + launch) |
| 21b | same, **11 workers x 700** | PC | 19.7 | - | **386.4k** (379-391k, no dip); CPU ~5.8 of 12 threads | GPU 99 % |
| 22 | **whole layer in 3 Triton kernels** (--fused-layer, 151b5179), 11 x 700, 120 s | PC | 18.9 | **533k** (3.8 ms; FFN kernel 38 %, LN+QKV 18 %, attention 16 %) | **440.7k** (446-454k steady, 1 dip) | batcher: pack 2.3 + wait 2.5 ms > GPU 3.8 ms -> CPU side |
| 23 | **--pack-threads 2 / 4** (907367a9), 11 x 700, 120 s | PC | 19.8 / 20.3 | 533k | 466.8k / **471.9k** (466-475k steady, no dip); pack 1.69 / 1.30 ms | GPU 97-98 % (and workers near their ~540k ceiling) |
| 24 | Triton launch-parameter sweep (f2244f44): FFN 22 configs, LN+QKV 12, attention 3 | PC | - | best 533k = default within noise (BO=192 does not compile) | 467.1k (= z2 within noise) | GPU 97 % |
| 25 | 1.2M net (128x4), --fused-layer, 11 x 700, 120 s (f2244f44) | PC | 19.7 | 208k | **212.8k** (210-215k, GPU 99 %) | GPU |
| 25b | 5.4M net (256x5), --varlen-attn only (fused kernels need d <= 128), same | PC | 20.8 | 62k | **68.6k** (67-69k, GPU 100 %) | GPU |
| 26 | **3 repeat runs of row 23** (7b002281 = merged #1075), exact command in final/commands.txt | PC | 20.3 | - | **471.3k / 468.8k / 472.0k** (mean 470.7k, +-0.3 %) | GPU 94-96 % |
| 27 | Inductor on torch 2.11.0+cu128 (venv-torchnew, 7b002281) | PC | - | gpacked_half **224.4k** (+8 % vs 207k on 2.5.1), sdpa_half 201.2k (+7 %); err ~1e-3 | - | - |
| 27b | Emmy 0.3.25 on torch 2.11, nvcc 13.2 (pip) | PC | - | **no result**: compiler stuck > 20 min in its loop-IR assembler (deep recursion assembly.py subroutine/resolve), never reaches codegen; watchdog stop | - | - |
