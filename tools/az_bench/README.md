# Stage 0 throughput bench (Amber-Eye-style self-play loop)

Measures whether a search with a neural-network leaf can reach the positions-per-second rate a from-scratch
self-play loop needs on one RTX 3060 Ti (8 GB). Decision rule from the 2026-11-16 assessment: at least 300k
positions/s end to end continues to stage 1 as planned, 100k to 300k continues with a smaller game budget, below
100k after one profiling round stops. One position = one net leaf evaluation.

| Part | Tool | Measures |
|---|---|---|
| 1 | `gpu_forward_bench.py` | GPU forward rate of the token combat net (`tools/combat_net/model.py`), random weights, per net size and batch size, with and without the host-to-device copy |
| 2 | (planned) | CPU rate of simulator step plus input encoding per core |
| 3 | (planned) | End to end: parallel searches whose leaves are batched onto the GPU |

Part 1 is an upper bound for the end-to-end rate: the search can't evaluate positions faster than the net.

```
python3 tools/az_bench/gpu_forward_bench.py --out gpu_forward.json            # 64x4, 96x4, 128x4; batches 256..8192
python3 tools/az_bench/gpu_forward_bench.py --arrays DIR --nets 64x4          # real rows from tensorize.py output
```

No game seeds are driven, so the seed guard does not apply.
