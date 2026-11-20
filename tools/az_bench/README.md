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
`--gpu-timing` logs GPU ms per second of the inference and training streams. PC check 2026-11-18 (ledger
§818): correct, but 0.82× the compiled path at best (272k vs 331k pos/s), so it is not used.

```
TRITON_INTERPRET=1 python3 -m pytest tests/test_fused_net.py        # correctness on a CPU
python3 tools/az_bench/fused_net_bench.py                            # GPU: fused vs. compiled forward_packed, MFU
python3 tools/az_bench/fused_net_bench.py --sweep                    # tile / warp settings
```

## Heart search probe (2026-11-18)

`selfplay.py --heart-arms FULL:FAST:PROB:MFULL:MFAST,... [--heart-reps R]` (default off): every run that reaches the
Heart keeps the fight's start state and plays the fight once per arm and rep from it, each with that arm's search
budget (moves before the Heart use the normal flags); plays go to `heart_probe.jsonl`. Use a frozen net
(`--init-net CKPT --min-replay 1000000000000 --keep-full 0`). `heart_probe_report.py heart_probe.jsonl` prints the
paired per-start damage difference against arm 0. First use: ledger "Heart search probe" (2026-11-18).

## CPU affinity and time split (2026-11-20)

`selfplay.py --pin-inference CPUS` (default off, Linux): the inference thread runs on the given logical CPUs and every
other thread of the process (workers, trainer, main, library pools) on the remaining ones; the sweep over
`/proc/self/task` is repeated at every report, so threads started later follow. `CPUS` is a list such as `5,11` or
`auto` (the SMT siblings of the highest-numbered allowed CPU, one physical core). Give it both siblings of a core:
the pack threads the inference thread starts inherit its CPUs. It changes scheduling only. Live check on the Stage 1
run on the 6-core PC (ledger §820, one before/after comparison): moves/s +10.2 %.

Every report row of `metrics.jsonl` carries the time split (logging only):

- `infer_batches_per_s`, `infer_rows_per_batch`: inference batches and their mean rows.
- `infer_tokens_per_row`, `infer_tok_bucket_batches`: live tokens per evaluated row, and the batches of the report
  window per token bucket. The bucket is the padded length of every row of a batch (the bucket of its longest row);
  the varlen attention kernel's key loop runs to it for every row (`varlen_attn.py`, `MAXLEN`).
- `infer_ms_per_s`: wall ms per second of the inference thread by phase. `wait_pack` = `next_flat` (waiting for rows
  and packing; `pack_s_per_s` is the packing part), `weights` = taking over the trainer's weights, `h2d` = shapes and
  host-to-GPU copies, `forward` = dtype casts and the net (on a GPU: issuing the kernels), `out` = search values and
  output copies (issuing), `sync` = waiting for the previous batch on the GPU, `submit` = results to the driver.
- `train_ms_per_s`: the same for the training thread. `take_add` = finished samples into the window, `idle` =
  sleeping (window too small or at the replay ratio cap), `sample`, `h2d`, `fwd_bwd` = loss, backward and clipping
  (issuing), `sync` = the gradient-norm / loss read that waits for the GPU, `opt`, `loss_read` = reading the loss
  parts (waits for the GPU), `publish` = weights hand-over.
- `worker_cpu_s_per_s`: CPU seconds per second of all worker threads together. `search` is their whole search loop
  and contains `step` (simulator steps and expansions) and `encode` (token encoding).

`infer_profile.py` (2026-11-20) breaks the GPU time of the inference path down on real states: it loads a
checkpoint and the saved window (`--replay-save`) of a run, draws rows, lays them out as the driver does (row /
token / action buckets, padding rows, packed tokens) and times the run's compiled forward with CUDA events, with
the top CUDA kernels of torch.profiler. Variants on the same rows separate the cost of the token bucket
(`short_T64` against `short_Tbig`), of the empty rows of the row bucket (`real_Rtight`) and of mixed lengths
(`uniform`). The window holds root states of real moves, the run evaluates search leaves of such states. It needs
the GPU to itself: stop the run first. No game seeds are driven.

    python3 tools/az_bench/infer_profile.py --module-dir BUILD_DIR --ckpt RUN/ckpt_N.pt --replay RUN/replay \
        --out prof.json

First profile (ledger §823): the varlen attention kernel is 37 % of a batch's GPU time. A batch's token bucket
follows its longest row (80 or 96 for nearly every batch, at 36 tokens per row), and the kernel runs every row,
the padding rows of the row bucket included, to that bucket. `selfplay.py --attn-row-bounds` (default off;
`varlen_attn.py` `ROW_BOUNDS`) ends each row's key loop at the row's own length and skips query blocks past it:
same output values. On a GPU `infer_profile.py` times both settings and compares their outputs.
Result on the PC (ledger §824): outputs equal, 4.80 -> 3.56 ms GPU per real batch, the live run +9 to +12 % moves/s
with the GPU load down from 97 to 80 %; where a batch has no dead blocks (bucket 64 or less) the variant is about
3 % slower. The live run uses the flag.

`selfplay.py --packed-heads` (2026-11-20, default off; needs `--packed-h2d`): what a batch still pays for padding
after the row bounds is in the heads, which run on the padded `[rows, tokens, d]` and `[rows, actions, d]` layout
(the row bucket is 2,048 for about 1,300 live rows, the action bucket 32 or 96 for a handful of legal actions per
row). With the flag the heads run on the packed tokens and on the live actions only (`amber_net.py`
`_heads_packed`, the row summary through the `row_mean.py` kernel), the policy logits are scattered back into
`[rows, actions]`, and the padding rows get length 0 in `seq_off`, so the attention and row-mean kernels do nothing
for them. Same math per row and action up to float rounding (the row mean is accumulated in fp32 and the matrix
products run on other shapes), not bit-identical. `infer_profile.py` times it and reports the largest output
difference against the padded heads on real batches.
Result on the PC (ledger §826): 3.80 -> 2.75 ms GPU per real batch, the best policy action the same in 99.6-100 %
of the rows, largest logit difference 0.02; in the live run 10,639 -> 11,930 moves/s (+12 %, same restart also turned
on `--force-potions`), GPU load 74 %. After that nothing is saturated (workers 63 % on CPU, inference thread 74 %):
the two wait for each other (ledger §TBD).
`worker_cpu_s_per_s.search` contains `step` and `encode`.

Each thread's phases add up to about 1000. With a GPU the issuing phases are CPU time of that thread and the `sync` /
`loss_read` phases are time it waits for the GPU; `--gpu-timing`'s `gpu_ms_per_s` is the elapsed GPU time of each
stream, and the two streams overlap, so their sum is not the GPU's load.

First reading of the time split (ledger §821, 2026-11-20) and the two fixes that followed, both with unchanged
results:

- `search_values` built its two constant vectors in every batch, and `floors[0] = 57.0` on a GPU tensor is a
  synchronous copy that waits for the whole forward on the stream (`out` 4.4 of 10.5 ms per batch, `sync` 0). They are
  now built once per device (`search_consts`). Expect `out` to fall and `sync` to take over whatever GPU wait is left.
- The compact replay window tested every live sample at every chunk to find the samples to evict (two passes over
  a 10M window: `take_add` 58 % of the trainer's time). The scans now read the window from its old end in blocks and
  stop at the first sample that stays (`Replay._first_keep`, `_soft_bytes_evict`), so `take_add` no longer grows with
  `--window`.
