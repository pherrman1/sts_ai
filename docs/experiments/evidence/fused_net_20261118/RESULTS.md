# Whole-net Triton kernel (PR #1094): PC GPU check, 2026-11-18 01:13-01:20 CET

Machine: RTX 3060 Ti 8 GB, torch 2.5.1+cu121, Triton 3.1.0, /usr/bin/python3. Commit e3891562 (clone of
claude/project-thread-j3dqhr). GPU idle except desktop clients (Stage 1 run stopped). Synthetic packed batches from
`tools/az_bench/fused_net_bench.py` (2048 rows, lognormal token counts, 16 action slots, random weights with jittered
1-D parameters). Baseline = the self-play inference path: `forward_packed`, fp16, varlen attention + three-kernel
layers, `torch.compile`. MFU = useful FLOPs (live tokens, attention within rows) / 32.4 TFLOPS.

`python3 -m unittest -v tests.test_fused_net`: 8 tests OK (136.5 s).

`fused_net_bench.py --rows 2048 --mean-tokens 26` (tile 64, 8 warps, 1 stage):
```
{"rows": 2048, "mean_tokens": 25.9404296875, "tile": 64, "warps": 8, "stages": 1, "big_tile": 128, "max_err_vs_fp32": {"logits": 0.00084, "outcome": 0.00069, "hp": 0.00087, "hpf": 0.00097}, "make_tiles_ms": 1.176, "tiles_small_big_long": [1007, 44, 1], "tile_fill": 0.756, "fused_pos_per_s": 228041, "fused_tflops": 3.93, "fused_mfu": 0.121, "max_err_fused_vs_baseline": {"logits": 0.00123, "outcome": 0.00109, "hp": 0.00113, "hpf": 0.00115}, "baseline_pos_per_s": 330718, "baseline_mfu": 0.176, "speedup": 0.69}
```
`--mean-tokens 36 --no-baseline`:
```
{"rows": 2048, "mean_tokens": 35.9072265625, "tile": 64, "warps": 8, "stages": 1, "big_tile": 128, "max_err_vs_fp32": {"logits": 0.0012, "outcome": 0.0007, "hp": 0.00118, "hpf": 0.00104}, "make_tiles_ms": 1.643, "tiles_small_big_long": [1292, 149, 7], "tile_fill": 0.715, "fused_pos_per_s": 175768, "fused_tflops": 4.3, "fused_mfu": 0.133}
```
`--sweep --rows 2048 --mean-tokens 26 --iters 100` (fused pos/s, MFU):

| tile | warps | stages | pos/s | MFU |
|---|---|---|---|---|
| 64 | 8 | 1 | 227,317 | 0.121 |
| 64 | 4 | 1 | **272,443** | 0.145 |
| 64 | 8 | 2 | 228,496 | 0.122 |
| 64 | 16 | 1 | 121,795 | 0.065 |
| 128 | 8 | 1 | 220,025 | 0.117 |
| 128 | 16 | 1 | 73,257 | 0.039 |
| 32 | 4 | 1 | 171,813 | 0.091 |

Offline sm_86 compiles (Triton 3.1.0, bundled `ptxas -v`): every configuration uses 255 registers (128 at 16 warps)
and spills (tile 64 / 8 warps / 1 stage: 1,180 B spill stores per thread); a 256-token tile needs 147 KB shared memory
(sm_86 limit 99 KB).
