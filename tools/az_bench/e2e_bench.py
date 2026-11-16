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
    params = sum(p.numel() for p in net.parameters())
    if args.compile:
        import torch._dynamo as dynamo
        dynamo.config.cache_size_limit = 64
        run = torch.compile(net, dynamic=False, backend=args.backend)
    else:
        run = net

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

    def batcher_loop(i):
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
                with ctx, torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=dtype != torch.float32):
                    x, rows = to_device(b, dev, bucket=args.compile)
                    lg, outcome, _, _ = run(x)
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
        "net": args.net, "params": params, "dtype": args.dtype, "compile": args.compile, "backend": args.backend if args.compile else None, "fake_net": args.fake_net,
        "encoder": args.encoder,
        "workers": args.workers, "games_per_worker": args.games, "batchers": args.batchers, "max_batch": args.batch,
        "full_sims": args.full_sims, "fast_sims": args.fast_sims, "full_prob": args.full_prob,
        "device": torch.cuda.get_device_name(dev) if dev.type == "cuda" else "cpu", "torch": torch.__version__,
        "seconds": round(wall, 2),
        "positions_per_s": round((s1["evals"] - s0["evals"]) / wall),
        "moves_per_s": round((s1["moves"] - s0["moves"]) / wall),
        "fights": s1["fights"] - s0["fights"],
        "mean_batch_rows": round((w1["rows"] - w0["rows"]) / nb, 1),
        "batcher_ms_per_batch": {k: round(1e3 * (w1[k] - w0[k]) / nb, 3) for k in ("wait", "h2d_forward", "submit")},
        "worker_us_per_position": {
            "step_enumerate": round(1e6 * (s1["step_cpu"] - s0["step_cpu"]) / ev, 3),
            "encode": round(1e6 * (s1["encode_cpu"] - s0["encode_cpu"]) / ev, 3),
            "search_loop": round(1e6 * (s1["search_cpu"] - s0["search_cpu"]) / ev, 3)},
        "encode_cut": s1["encode_cut"],
    }
    if errors:
        res["errors"] = errors
    print(json.dumps(res), flush=True)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
