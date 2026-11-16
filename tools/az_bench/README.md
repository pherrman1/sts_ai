# Stage 0 throughput bench (Amber-Eye-style self-play loop)

Measures whether a search with a neural-network leaf can reach the positions-per-second rate a from-scratch
self-play loop needs on one RTX 3060 Ti (8 GB). Decision rule from the 2026-11-16 assessment: at least 300k
positions/s end to end continues to stage 1 as planned, 100k to 300k continues with a smaller game budget, below
100k after one profiling round stops. One position = one net leaf evaluation.

| Part | Tool | Measures |
|---|---|---|
| 1 | `gpu_forward_bench.py` | GPU forward rate of a token transformer, random weights, per net size and batch size, with and without the host-to-device copy. `--arch amber` (default): `amber_net.py`, shaped after Amber Eye's net (~40 tokens, policy over the legal-action list, 0.44M / 1.2M / 5.4M); `--arch combat`: our combat net (`tools/combat_net/model.py`) |
| 2 | (planned) | CPU rate of simulator step plus input encoding per core |
| 3 | (planned) | End to end: parallel searches whose leaves are batched onto the GPU |

Amber Eye's page quotes ~800k positions/s for its search with small (CPU-bound) nets on an 8-core machine with
14 worker threads of hundreds of games each, a request queue, and batching threads feeding the GPU; FP16 weights in
the GPU's L2 cache and a kernel at ~75 % MFU. The page names neither the GPU nor the framework.

Part 1 is an upper bound for the end-to-end rate: the search can't evaluate positions faster than the net.

```
python3 tools/az_bench/gpu_forward_bench.py --compile --out gpu_forward.json  # Amber-Eye sizes, bf16
python3 tools/az_bench/gpu_forward_bench.py --arch combat --arrays DIR        # real combat-net rows (tensorize.py)
```

No game seeds are driven, so the seed guard does not apply.
