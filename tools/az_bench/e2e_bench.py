#!/usr/bin/env python3
"""Stage 0 throughput bench, part 3 (Amber-Eye-style self-play loop, 2026-11-16): end-to-end positions per second.

C++ worker threads (az_bench_native.Driver, apps/az_bench/az_driver.h) each run --games combat games with a Gumbel
AlphaZero search (64 / 16 positions per full / fast move, playout cap randomization p = 0.25, as Amber Eye's
self-play); every leaf is a request on one queue. --batchers Python threads each take up to --batch requests, run
the Amber-Eye-shaped net (amber_net.py, random weights) on the GPU, and post the policy logits and P(win) back.
One position = one net evaluation. No game seeds: fights restart from the wire rows' states.

usage: e2e_bench.py --module-dir BUILD_DIR [--wires tests/data/combat_net_wire_sample.jsonl] [--net 0.44M]
                    [--workers 10] [--games 256] [--batchers 2] [--batch 4096] [--seconds 60] [--compile]
                    [--dtype fp16] [--out e2e.json]

Prints positions/s every --report seconds and a final JSON object (also written with --out).
"""

import argparse
import importlib.util
import json
import os
import sys
import threading
import time

import torch
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
amber_net = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amber_net)

LONG_KEYS = [t + "_ids" for t in amber_net.TOKEN_TYPES] + ["a_type", "a_src", "a_tgt"]


def round_up(x, m):
    return (x + m - 1) // m * m


def to_device(b, dev, bucket):
    """numpy batch -> device tensors in AmberNet.forward's dtypes. With `bucket`, rows are padded to a power of two
    (>= 256) and every token segment / the action axis to a multiple of 8, so torch.compile sees few shapes."""
    rows = b["ticket"].shape[0]
    out = {}
    R = max(256, 1 << (rows - 1).bit_length()) if bucket else rows
    seg_slots = {t: b[t + "_mask"].shape[1] for t in amber_net.TOKEN_TYPES}
    old_off, new_off, o1, o2 = {}, {}, 0, 0
    for t in amber_net.TOKEN_TYPES:
        old_off[t], new_off[t] = o1, o2
        o1 += seg_slots[t]
        o2 += round_up(seg_slots[t], 8) if bucket else seg_slots[t]
    for k, v in b.items():
        if k == "ticket":
            continue
        x = torch.from_numpy(v)
        x = x.pin_memory().to(dev, non_blocking=True) if dev.type == "cuda" else x.to(dev)
        if k in LONG_KEYS:
            x = x.long()
        elif x.dtype == torch.float16:
            x = x.float()   # sent as float16 (half the transfer); autocast picks the compute dtype
        if bucket:
            pad = []
            if x.dim() >= 2:
                seg = k.rsplit("_", 1)[0] if not k.startswith("a_") else None
                n = x.shape[1]
                n2 = round_up(n, 8)
                pad = [0, 0] * (x.dim() - 2) + [0, n2 - n]
            pad += [0, R - rows]
            x = F.pad(x, pad, value=(-1 if k in ("a_src", "a_tgt") else 0))
        out[k] = x
    if bucket:
        # Re-map action source / target indices to the padded segment offsets.
        for k in ("a_src", "a_tgt"):
            idx = out[k]
            new = idx.clone()
            for t in amber_net.TOKEN_TYPES:
                lo, hi = old_off[t], old_off[t] + seg_slots[t]
                sel = (idx >= lo) & (idx < hi)
                new = torch.where(sel, idx - lo + new_off[t], new)
            out[k] = new
        out["run_mask"][:, 0] = True   # padded rows: keep the run token live so attention has a key
        out["a_mask"][rows:, 0] = True
    return out, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module-dir", required=True, help="directory holding the built az_bench_native module")
    ap.add_argument("--wires", default=os.path.join(ROOT, "tests", "data", "combat_net_wire_sample.jsonl"))
    ap.add_argument("--net", default="0.44M", help="amber_net size name or DxL[xH]")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--games", type=int, default=256, help="games per worker thread")
    ap.add_argument("--batchers", type=int, default=2, help="Python threads taking batches to the GPU")
    ap.add_argument("--batch", type=int, default=4096, help="max rows per batch")
    ap.add_argument("--min-batch", type=int, default=0,
                    help="wait for this many queued requests (default half of min(batch, workers * games))")
    ap.add_argument("--full-sims", type=int, default=64)
    ap.add_argument("--fast-sims", type=int, default=16)
    ap.add_argument("--full-prob", type=float, default=0.25)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--warmup", type=float, default=10, help="seconds before the timed window")
    ap.add_argument("--report", type=float, default=5)
    ap.add_argument("--dtype", default="fp16", choices=["fp16", "bf16", "fp32"])
    ap.add_argument("--sdpa", action="store_true", help="AmberNet.sdpa: fused-attention trunk (same weights and math)")
    ap.add_argument("--fused-layer", action="store_true",
                    help="with --varlen-attn: each layer as norm1+QKV, attention and out_proj+FFN kernels")
    ap.add_argument("--varlen-attn", action="store_true",
                    help="with --pack-step: attention on the packed tokens as one Triton kernel (varlen_attn.py)")
    ap.add_argument("--fused-ffn", action="store_true",
                    help="with --pack-step: LayerNorm + FFN + residual per layer as one Triton kernel (fused_ffn.py)")
    ap.add_argument("--attn-math", action="store_true",
                    help="with --sdpa / --pack-step: attention as plain matmuls + fp32 softmax instead of SDPA")
    ap.add_argument("--half", action="store_true",
                    help="flat layout: weights and float inputs in --dtype, autocast off (default: fp32 weights + autocast)")
    ap.add_argument("--layout", default="flat", choices=["flat", "segments"],
                    help="flat: one token axis per row, rows / tokens / actions padded to bucket sizes, packed by C++ "
                         "into pinned buffers (default); segments: per-type segments padded to the batch's longest")
    ap.add_argument("--row-buckets", default="256,512,1024,2048,4096")
    ap.add_argument("--tok-buckets", default="32,48,64,96,128,212")
    ap.add_argument("--act-buckets", default="16,32,64,96")
    ap.add_argument("--pack-step", type=int, default=0,
                    help="flat layout: AmberNet.forward_packed (per-token work on live tokens only), the live-token "
                         "count padded to a multiple of this (e.g. 2048); 0 = off")
    ap.add_argument("--pipeline", action="store_true",
                    help="flat layout, one batcher: pack the next batch on the CPU while the GPU runs the current one "
                         "(two pinned buffer sets; results come back through pinned memory)")
    ap.add_argument("--sort-window", type=int, default=1,
                    help="flat: sort this many batches' worth of requests by token count and serve them in order, so "
                         "each batch pads to a tight token bucket")
    ap.add_argument("--precompile", action="store_true",
                    help="flat + compile: compile every (rows >= batch/2, token, action) bucket in the main thread "
                         "before the batchers start; batchers then never compile (an unseen shape runs eager), "
                         "which allows several batchers")
    ap.add_argument("--compile-mode", default=None,
                    help="torch.compile mode (e.g. max-autotune-no-cudagraphs); overrides --cuda-graphs")
    ap.add_argument("--pack-gather", action="store_true",
                    help="with --pack-step: also send unpack_idx (packed -> padded by one gather)")
    ap.add_argument("--cuda-graphs", action="store_true",
                    help="with --compile: mode reduce-overhead (CUDA graphs per shape)")
    ap.add_argument("--compile", action="store_true", help="torch.compile the net (bucketed shapes)")
    ap.add_argument("--backend", default="inductor", help="torch.compile backend (inductor, emmy, ...)")
    ap.add_argument("--encoder", default="amber", choices=["amber", "stub"],
                    help="native Amber encoder (AmberEncoder.h) or the driver's placeholder")
    ap.add_argument("--fake-net", action="store_true", help="no GPU forward: random outputs (CPU-side ceiling)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=0, help="search / weight RNG seed (not a game seed)")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    sys.path.insert(0, args.module_dir)
    import az_bench_native  # noqa: E402

    dev = torch.device(args.device)
    dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[args.dtype]
    torch.manual_seed(args.seed)
    d, layers = amber_net.SIZES.get(args.net) or tuple(int(x) for x in args.net.split("x")[:2])
    net = amber_net.AmberNet(d=d, layers=layers).to(dev).eval()
    net.sdpa = args.sdpa
    net.attn_math = args.attn_math
    net.fused_ffn = amber_net.load_fused_ffn() if args.fused_ffn else None
    net.varlen_attn = amber_net.load_kernel("varlen_attn") if args.varlen_attn else None
    net.fused_layer = amber_net.load_fused_layer() if args.fused_layer else None
    if args.half:
        if args.layout != "flat" or dtype == torch.float32:
            raise SystemExit("--half needs --layout flat and --dtype fp16 / bf16")
        net = net.to(dtype)
    use_autocast = dtype != torch.float32 and not args.half
    in_float = dtype if args.half else torch.float32
    params = sum(p.numel() for p in net.parameters())
    if args.compile:
        import torch._dynamo as dynamo
        dynamo.config.cache_size_limit = 64
        if args.backend == "inductor":
            run = torch.compile(net, dynamic=False, mode=args.compile_mode or ("reduce-overhead" if args.cuda_graphs else "default"))
        else:
            run = torch.compile(net, dynamic=False, backend=args.backend)
    else:
        run = net
    # torch.compile from several threads at once can deadlock (seen on the 3060 Ti): the first call of every new
    # shape runs under this lock, later calls of a known shape run freely.
    compile_lock = threading.Lock()
    seen_shapes = set()

    fallbacks = [0]

    def forward(x, key):
        if not args.compile or key in seen_shapes:
            return run(x)
        if args.precompile:
            fallbacks[0] += 1
            return net(x)
        with compile_lock:
            out = run(x)
            torch.cuda.synchronize() if dev.type == "cuda" else None
            seen_shapes.add(key)
            return out

    row_b = [int(v) for v in args.row_buckets.split(",") if int(v) <= args.batch] or [args.batch]
    if row_b[-1] < args.batch:
        row_b.append(args.batch)
    tok_b = [int(v) for v in args.tok_buckets.split(",")]
    act_b = [int(v) for v in args.act_buckets.split(",")]
    if args.compile and args.precompile and args.layout == "flat" and not args.fake_net:
        tp = time.perf_counter()
        for R in [r for r in row_b if r >= args.batch // 2]:
            for T in tok_b:
                for A in act_b:
                    x = {"tok_type": torch.zeros(R, T, dtype=torch.long, device=dev),
                         "ids": torch.zeros(R, T, 4, dtype=torch.long, device=dev),
                         "f": torch.zeros(R, T, 64, device=dev, dtype=in_float), "mask": torch.zeros(R, T, dtype=torch.bool, device=dev),
                         "a_type": torch.zeros(R, A, dtype=torch.long, device=dev),
                         "a_src": torch.full((R, A), -1, dtype=torch.long, device=dev),
                         "a_tgt": torch.full((R, A), -1, dtype=torch.long, device=dev),
                         "a_f": torch.zeros(R, A, 8, device=dev, dtype=in_float), "a_mask": torch.zeros(R, A, dtype=torch.bool, device=dev)}
                    x["mask"][:, 0] = True
                    x["a_mask"][:, 0] = True
                    with torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=use_autocast):
                        run(x)
                    seen_shapes.add((R, T, A))
        if dev.type == "cuda":
            torch.cuda.synchronize()
        print(f"# precompiled {len(seen_shapes)} shapes in {time.perf_counter() - tp:.0f} s", flush=True)

    drv = az_bench_native.Driver(args.wires, workers=args.workers, games=args.games, full_sims=args.full_sims,
                                 fast_sims=args.fast_sims, full_prob=args.full_prob, seed=args.seed,
                                 encoder=args.encoder)
    # In flight at most one request per game: waiting for more than half of them would only add latency.
    min_rows = args.min_batch or max(1, min(args.batch, args.workers * args.games) // 2)
    stop = threading.Event()
    timing = {"wait": 0.0, "h2d_forward": 0.0, "submit": 0.0, "batches": 0, "rows": 0}
    tlock = threading.Lock()

    errors = []

    def batcher(i):
        try:
            batcher_loop(i)
        except BaseException as e:   # surface it: a dead batcher would otherwise read as 0 positions/s
            errors.append(repr(e))
            stop.set()
            raise

    def pack_idx(host, views, Rp, Tp):
        """forward_packed's index of the live token slots, padded with M up to a multiple of --pack-step."""
        import numpy as np
        M = Rp * Tp
        live = np.flatnonzero(views["mask"][:M])
        n = live.size
        npad = -(-n // args.pack_step) * args.pack_step
        pv = views["pack_idx"]
        pv[:n] = live
        pv[n:npad] = M
        out = {"pack_idx": host["pack_idx"][:npad].to(dev, non_blocking=True).long()}
        if args.varlen_attn:
            so = views["seq_off"]
            so[0] = 0
            np.cumsum(views["mask"][:M].reshape(Rp, Tp).sum(1), out=so[1:Rp + 1])
            out["seq_off"] = host["seq_off"][:Rp + 1].to(dev, non_blocking=True)
        if args.pack_gather:
            uv = views["unpack_idx"]
            uv[:M] = npad
            uv[live] = np.arange(n, dtype=np.int32)
            out["unpack_idx"] = host["unpack_idx"][:M].to(dev, non_blocking=True).long()
        return out, npad

    def flat_loop(i):
        import numpy as np
        rng = np.random.default_rng(i)
        stream = torch.cuda.Stream(dev) if dev.type == "cuda" else None
        R, T, A = row_b[-1], tok_b[-1], act_b[-1]
        pin = dev.type == "cuda"
        host = {
            "tok_type": torch.zeros(R * T, dtype=torch.int8, pin_memory=pin),
            "ids": torch.zeros(R * T * 4, dtype=torch.int16, pin_memory=pin),
            "f": torch.zeros(R * T * 64, dtype=torch.float16, pin_memory=pin),
            "mask": torch.zeros(R * T, dtype=torch.bool, pin_memory=pin),
            "a_type": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
            "a_src": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
            "a_tgt": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
            "a_f": torch.zeros(R * A * 8, dtype=torch.float16, pin_memory=pin),
            "a_mask": torch.zeros(R * A, dtype=torch.bool, pin_memory=pin),
            "pack_idx": torch.zeros(R * T, dtype=torch.int32, pin_memory=pin),
            "unpack_idx": torch.zeros(R * T, dtype=torch.int32, pin_memory=pin),
            "seq_off": torch.zeros(R + 1, dtype=torch.int32, pin_memory=pin),
        }
        views = {k: v.numpy() for k, v in host.items()}
        while not stop.is_set():
            t0 = time.perf_counter()
            got = drv.next_flat(args.batch, min_rows, 5, row_b, tok_b, act_b, views, args.sort_window)
            t1 = time.perf_counter()
            if got is None:
                with tlock:
                    timing["wait"] += t1 - t0
                continue
            ticket, rows, Rp, Tp, Ap = got
            live_t = int(views["mask"][:rows * Tp].sum())
            live_a = int(views["a_mask"][:rows * Ap].sum())
            if args.fake_net:
                logits = rng.random((rows, Ap), dtype=np.float32)
                value = rng.random(rows, dtype=np.float32)
            else:
                shapes = {"tok_type": (Rp, Tp), "ids": (Rp, Tp, 4), "f": (Rp, Tp, 64), "mask": (Rp, Tp),
                          "a_type": (Rp, Ap), "a_src": (Rp, Ap), "a_tgt": (Rp, Ap), "a_f": (Rp, Ap, 8),
                          "a_mask": (Rp, Ap)}
                ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                with ctx, torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=use_autocast):
                    x = {}
                    for k, shp in shapes.items():
                        n = int(np.prod(shp))
                        t = host[k][:n].to(dev, non_blocking=True).view(shp)
                        if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt"):
                            t = t.long()
                        elif t.dtype == torch.float16:
                            t = t.to(in_float)
                        x[k] = t
                    key = (Rp, Tp, Ap)
                    if args.pack_step:
                        pk, npad = pack_idx(host, views, Rp, Tp)
                        x.update(pk)
                        key = (Rp, Tp, Ap, npad)
                    lg, outcome, _, _ = forward(x, key)
                    logits = lg[:rows].float().cpu().numpy()
                    value = torch.softmax(outcome[:rows].float(), -1)[:, 0].cpu().numpy()
            t2 = time.perf_counter()
            drv.submit(ticket, logits, value)
            t3 = time.perf_counter()
            with tlock:
                timing["wait"] += t1 - t0
                timing["h2d_forward"] += t2 - t1
                timing["submit"] += t3 - t2
                timing["batches"] += 1
                timing["rows"] += rows
                timing["padded_rows"] = timing.get("padded_rows", 0) + Rp
                timing["tok_slots"] = timing.get("tok_slots", 0) + Rp * Tp
                timing["live_toks"] = timing.get("live_toks", 0) + live_t
                timing["live_acts"] = timing.get("live_acts", 0) + live_a

    def flat_pipe_loop(i):
        """Two-deep pipeline: while the GPU evaluates batch k (launched asynchronously on a side stream, results
        copied into pinned memory), the CPU packs batch k + 1 into the other host buffer set; then it waits for k,
        posts k's results and launches k + 1. Same inputs and net per batch as flat_loop, so the same outputs."""
        import numpy as np
        stream = torch.cuda.Stream(dev) if dev.type == "cuda" else None
        R, T, A = row_b[-1], tok_b[-1], act_b[-1]
        pin = dev.type == "cuda"

        def buffers():
            h = {"tok_type": torch.zeros(R * T, dtype=torch.int8, pin_memory=pin),
                 "ids": torch.zeros(R * T * 4, dtype=torch.int16, pin_memory=pin),
                 "f": torch.zeros(R * T * 64, dtype=torch.float16, pin_memory=pin),
                 "mask": torch.zeros(R * T, dtype=torch.bool, pin_memory=pin),
                 "a_type": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
                 "a_src": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
                 "a_tgt": torch.zeros(R * A, dtype=torch.int16, pin_memory=pin),
                 "a_f": torch.zeros(R * A * 8, dtype=torch.float16, pin_memory=pin),
                 "a_mask": torch.zeros(R * A, dtype=torch.bool, pin_memory=pin),
                 "pack_idx": torch.zeros(R * T, dtype=torch.int32, pin_memory=pin),
                 "unpack_idx": torch.zeros(R * T, dtype=torch.int32, pin_memory=pin),
                 "seq_off": torch.zeros(R + 1, dtype=torch.int32, pin_memory=pin)}
            out = {"logits": torch.zeros(R * A, dtype=torch.float32, pin_memory=pin),
                   "value": torch.zeros(R, dtype=torch.float32, pin_memory=pin)}
            return h, {k: v.numpy() for k, v in h.items()}, out

        sets = [buffers(), buffers()]
        cur, pending = 0, None   # pending: (ticket, rows, Ap, out, event, t_launch)

        def finish(p):
            ticket, rows, Ap, out, ev, _ = p
            if ev is not None:
                ev.synchronize()
            logits = out["logits"][:rows * Ap].numpy().reshape(rows, Ap)
            value = out["value"][:rows].numpy()
            t2 = time.perf_counter()
            drv.submit(ticket, logits, value)
            return time.perf_counter() - t2

        while not stop.is_set():
            host, views, out = sets[cur]
            t0 = time.perf_counter()
            got = drv.next_flat(args.batch, min_rows, 5, row_b, tok_b, act_b, views, args.sort_window)
            t1 = time.perf_counter()
            launched = None
            if got is not None:
                ticket, rows, Rp, Tp, Ap = got
                live_t = int(views["mask"][:rows * Tp].sum())
                live_a = int(views["a_mask"][:rows * Ap].sum())
                shapes = {"tok_type": (Rp, Tp), "ids": (Rp, Tp, 4), "f": (Rp, Tp, 64), "mask": (Rp, Tp),
                          "a_type": (Rp, Ap), "a_src": (Rp, Ap), "a_tgt": (Rp, Ap), "a_f": (Rp, Ap, 8),
                          "a_mask": (Rp, Ap)}
                ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                with ctx, torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=use_autocast):
                    x = {}
                    for k, shp in shapes.items():
                        n = int(np.prod(shp))
                        t = host[k][:n].to(dev, non_blocking=True).view(shp)
                        if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt"):
                            t = t.long()
                        elif t.dtype == torch.float16:
                            t = t.to(in_float)
                        x[k] = t
                    key = (Rp, Tp, Ap)
                    if args.pack_step:
                        pk, npad = pack_idx(host, views, Rp, Tp)
                        x.update(pk)
                        key = (Rp, Tp, Ap, npad)
                    lg, outcome, _, _ = forward(x, key)
                    out["logits"][:rows * Ap].view(rows, Ap).copy_(lg[:rows].float(), non_blocking=True)
                    out["value"][:rows].copy_(torch.softmax(outcome[:rows].float(), -1)[:, 0], non_blocking=True)
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event()
                        ev.record(stream)
                launched = (ticket, rows, Ap, out, ev, time.perf_counter())
            t2 = time.perf_counter()
            sub = 0.0
            if pending is not None:
                sub = finish(pending)
            t3 = time.perf_counter()
            with tlock:
                timing["wait"] += t1 - t0
                timing["h2d_forward"] += (t3 - t2) - sub + (t2 - t1)   # launch + wait for the previous batch
                timing["submit"] += sub
                if pending is not None:
                    timing["batches"] += 1
                    timing["rows"] += pending[1]
                if launched is not None:
                    timing["padded_rows"] = timing.get("padded_rows", 0) + Rp
                    timing["tok_slots"] = timing.get("tok_slots", 0) + Rp * Tp
                    timing["live_toks"] = timing.get("live_toks", 0) + live_t
                    timing["live_acts"] = timing.get("live_acts", 0) + live_a
                    timing["launched_rows"] = timing.get("launched_rows", 0) + rows
            pending = launched
            if launched is not None:
                cur ^= 1
        if pending is not None:
            finish(pending)

    def batcher_loop(i):
        if args.layout == "flat" and args.pipeline:
            if args.fake_net or args.batchers != 1:
                raise SystemExit("--pipeline needs a real net and --batchers 1")
            return flat_pipe_loop(i)
        if args.layout == "flat":
            return flat_loop(i)
        stream = torch.cuda.Stream(dev) if dev.type == "cuda" else None
        import numpy as np
        rng = np.random.default_rng(i)
        while not stop.is_set():
            t0 = time.perf_counter()
            b = drv.next_batch(args.batch, min_rows, 5)
            t1 = time.perf_counter()
            if b is None:
                with tlock:
                    timing["wait"] += t1 - t0
                continue
            rows = b["ticket"].shape[0]
            if args.fake_net:
                logits = rng.random((rows, b["a_mask"].shape[1]), dtype=np.float32)
                value = rng.random(rows, dtype=np.float32)
            else:
                ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                with ctx, torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=use_autocast):
                    x, rows = to_device(b, dev, bucket=args.compile)
                    lg, outcome, _, _ = forward(x, tuple(v.shape for v in x.values()))
                    lg = lg[:rows, :b["a_mask"].shape[1]].float()
                    v = torch.softmax(outcome[:rows].float(), -1)[:, 0]
                    logits = lg.cpu().numpy()
                    value = v.cpu().numpy()
            t2 = time.perf_counter()
            drv.submit(b["ticket"], logits, value)
            t3 = time.perf_counter()
            with tlock:
                timing["wait"] += t1 - t0
                timing["h2d_forward"] += t2 - t1
                timing["submit"] += t3 - t2
                timing["batches"] += 1
                timing["rows"] += rows

    threads = [threading.Thread(target=batcher, args=(i,), daemon=True) for i in range(args.batchers)]
    for t in threads:
        t.start()
    drv.start()
    print(f"# net {args.net} ({params} params) dtype {args.dtype} compile {args.compile} workers {args.workers} "
          f"games {args.games} batchers {args.batchers} batch {args.batch}", flush=True)
    t_start = time.perf_counter()
    time.sleep(args.warmup)
    s0, w0 = drv.stats(), dict(timing)
    t0 = time.perf_counter()
    last, last_t = s0, t0
    while time.perf_counter() - t0 < args.seconds and not stop.is_set():
        time.sleep(min(args.report, max(0.0, args.seconds - (time.perf_counter() - t0))))
        s, now = drv.stats(), time.perf_counter()
        print(json.dumps({"t": round(now - t_start, 1), "positions_per_s": round((s["evals"] - last["evals"]) / (now - last_t)),
                          "moves_per_s": round((s["moves"] - last["moves"]) / (now - last_t))}), flush=True)
        last, last_t = s, now
    s1, w1 = drv.stats(), dict(timing)
    wall = time.perf_counter() - t0
    stop.set()
    drv.stop()
    for t in threads:
        t.join(timeout=10)

    ev = max(1, s1["evals"] - s0["evals"])
    nb = max(1, w1["batches"] - w0["batches"])
    res = {
        "net": args.net, "params": params, "dtype": args.dtype, "sdpa": args.sdpa, "attn_math": args.attn_math, "fused_ffn": args.fused_ffn, "varlen_attn": args.varlen_attn, "fused_layer": args.fused_layer, "half": args.half, "pipeline": args.pipeline, "pack_step": args.pack_step, "pack_gather": args.pack_gather, "compile_mode": args.compile_mode, "compile": args.compile, "backend": args.backend if args.compile else None, "fake_net": args.fake_net,
        "encoder": args.encoder,
        "workers": args.workers, "games_per_worker": args.games, "batchers": args.batchers, "max_batch": args.batch,
        "full_sims": args.full_sims, "fast_sims": args.fast_sims, "full_prob": args.full_prob,
        "device": torch.cuda.get_device_name(dev) if dev.type == "cuda" else "cpu", "torch": torch.__version__,
        "seconds": round(wall, 2),
        "positions_per_s": round((s1["evals"] - s0["evals"]) / wall),
        "moves_per_s": round((s1["moves"] - s0["moves"]) / wall),
        "fights": s1["fights"] - s0["fights"],
        "layout": args.layout, "sort_window": args.sort_window, "min_batch": min_rows,
        "row_buckets": row_b, "tok_buckets": tok_b, "act_buckets": act_b,
        "mean_batch_rows": round((w1["rows"] - w0["rows"]) / nb, 1),
        "mean_padded_rows": round((w1.get("padded_rows", 0) - w0.get("padded_rows", 0)) / nb, 1),
        "mean_token_slots_per_row": round((w1.get("tok_slots", 0) - w0.get("tok_slots", 0))
                                          / max(1, w1.get("padded_rows", 0) - w0.get("padded_rows", 0)), 1),
        "mean_live_tokens_per_row": round((w1.get("live_toks", 0) - w0.get("live_toks", 0))
                                          / max(1, w1.get("launched_rows", w1["rows"]) - w0.get("launched_rows", w0["rows"])), 1),
        "mean_live_actions_per_row": round((w1.get("live_acts", 0) - w0.get("live_acts", 0))
                                           / max(1, w1.get("launched_rows", w1["rows"]) - w0.get("launched_rows", w0["rows"])), 1),
        "batcher_ms_per_batch": {k: round(1e3 * (w1[k] - w0[k]) / nb, 3) for k in ("wait", "h2d_forward", "submit")},
        "pack_ms_per_batch": round(1e3 * (s1.get("pack_s", 0) - s0.get("pack_s", 0)) / max(1, s1["batches"] - s0["batches"]), 3),
        "worker_us_per_position": {
            "step_enumerate": round(1e6 * (s1["step_cpu"] - s0["step_cpu"]) / ev, 3),
            "encode": round(1e6 * (s1["encode_cpu"] - s0["encode_cpu"]) / ev, 3),
            "search_loop": round(1e6 * (s1["search_cpu"] - s0["search_cpu"]) / ev, 3)},
        "encode_cut": s1["encode_cut"],
    }
    res["eager_fallback_batches"] = fallbacks[0]
    if errors:
        res["errors"] = errors
    print(json.dumps(res), flush=True)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
