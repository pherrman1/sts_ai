# Stage 0 throughput bench (Amber-Eye-style self-play loop)

Measures whether a search with a neural-network leaf can reach the positions-per-second rate a from-scratch
self-play loop needs on one RTX 3060 Ti (8 GB). Decision rule from the 2026-11-16 assessment: at least 300k
positions/s end to end continues to stage 1 as planned, 100k to 300k continues with a smaller game budget, below
100k after one profiling round stops. One position = one net leaf evaluation.

| Part | Tool | Measures |
|---|---|---|
| 1 | `gpu_forward_bench.py` | GPU forward rate of a token transformer, random weights, per net size and batch size, with and without the host-to-device copy. `--arch amber` (default): `amber_net.py`, shaped after Amber Eye's net (~40 tokens, policy over the legal-action list, 0.44M / 1.2M / 5.4M); `--arch combat`: our combat net (`tools/combat_net/model.py`) |
| 2 | `az-bench-producer` (apps/az_bench_producer.cpp) | CPU rate per thread of copy + step + enumerate + encode (today's `combatTokEncodeRoot`) |
| 3 | `az-bench-driver` (C++, fake net) and `e2e_bench.py` (pybind module `az_bench_native`, GPU net) | End to end: worker threads with hundreds of Gumbel-AZ games each, one request queue, batching threads feeding the net |

The end-to-end driver (`apps/az_bench/az_driver.h`) follows Amber Eye's self-play setup: Gumbel AlphaZero root,
64 / 16 positions per full / fast move with playout cap randomization p = 0.25, RNG reroll and double progressive
widening at chance edges, Gumbel MuZero selection below the root. Combat only, no tree reuse, one leaf in flight per
game. Its encoder is a stub (real token counts and ids, few features) until the native Amber encoder
(`include/sim/search/AmberTokens.h` interface) lands.

Amber Eye's page quotes ~800k positions/s for its search with small (CPU-bound) nets on an 8-core machine with
14 worker threads of hundreds of games each, a request queue, and batching threads feeding the GPU; FP16 weights in
the GPU's L2 cache and a kernel at ~75 % MFU. The page names neither the GPU nor the framework.

Part 1 is an upper bound for the end-to-end rate: the search can't evaluate positions faster than the net.

```
cmake --build build/linux-gcc-release --target az-bench-producer az-bench-driver az_bench_native
build/linux-gcc-release/az-bench-producer tests/data/combat_net_wire_sample.jsonl --threads 4
build/linux-gcc-release/az-bench-driver tests/data/combat_net_wire_sample.jsonl --workers 10 --games 256
python3 tools/az_bench/e2e_bench.py --module-dir build/linux-gcc-release --net 0.44M --workers 10 --seconds 60
python3 tools/az_bench/gpu_forward_bench.py --compile --out gpu_forward.json  # Amber-Eye sizes, bf16
python3 tools/az_bench/gpu_forward_bench.py --arch combat --arrays DIR        # real combat-net rows (tensorize.py)
```

No game seeds are driven, so the seed guard does not apply.

## Whole-net kernel (2026-11-17)

`fused_net.py` runs the whole AmberNet forward (input embedding, all encoder layers, summary, value heads, policy over
the legal actions) as one Triton kernel per batch, as Amber Eye describes its GPU side (FP16 weights in L2, one
kernel, MFU counted after discounting padded attention). Consecutive rows are grouped into tiles of at most 64 tokens
(longer rows: a 128-token launch; above that, rare, forward_packed on a sub-batch); attention runs padded within a
tile. Same math as
`AmberNet.forward_packed`, fp32 residual stream. `selfplay.py --packed-h2d --fused-net` uses it (default off);
`--gpu-timing` logs GPU ms per second of the inference and training streams.

```
TRITON_INTERPRET=1 python3 -m pytest tests/test_fused_net.py        # correctness on a CPU
python3 tools/az_bench/fused_net_bench.py                            # GPU: fused vs. compiled forward_packed, MFU
python3 tools/az_bench/fused_net_bench.py --sweep                    # tile / warp settings
```
