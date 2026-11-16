#!/usr/bin/env python3
"""Stage 0 throughput bench, part 1 (Amber-Eye-style loop assessment, 2026-11-16): how many positions per second the
token combat net (tools/combat_net/model.py CombatNet) evaluates on one GPU, as a function of net size and batch size.

Two nets: --arch amber (default) is tools/az_bench/amber_net.py, a token transformer shaped after Amber Eye's
network (https://8e9f.github.io/amber_eye/; ~40 tokens per state, policy over a legal-action list, sizes 0.44M /
1.2M / 5.4M); --arch combat is our trained combat net's architecture (tools/combat_net/model.py CombatNet).

One position = one row of a forward pass = one net leaf evaluation of a search. The net is randomly initialized (a
throughput bench needs no trained weights). Inputs are either synthetic rows with fixed token counts (--cards,
--mons, --statuses, --queues, --actions) or rows sampled from tensorize.py arrays (--arrays DIR), which also brings
the real padding cost of ragged rows. No game seeds are driven.

Two timings per (net, batch): `gpu` = forward only, inputs already on the device; `h2d` = the same plus copying the
batch from pinned host memory, as an inference server fed by CPU search threads would. Each is the median over
--iters timed passes after --warmup passes, synchronized on the device.

usage: gpu_forward_bench.py [--arch amber|combat] [--nets ...] [--batches 256,1024,4096,8192] [--dtype bf16]
                            [--arrays DIR] [--compile [--compile-mode M]] [--live-frac F] [--out bench.json]

Combat 64x4 has 0.41M parameters (0.26M outside the embeddings); 128x4 is the shape of the trained combat nets
(combat plan stage 3). --arrays (combat only) samples real tensorize.py rows, padded to the longest row of the batch.

Prints one line per measurement and, with --out, writes all of them as JSON together with the device, torch
version and arguments.
"""

import argparse
import importlib.util
import json
import os
import platform
import statistics
import sys
import time

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("combat_net_model", os.path.join(ROOT, "tools", "combat_net", "model.py"))
model = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model)
_spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
amber_net = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amber_net)

A_LEN = 47      # tensorize.py A_LEN (the native CombatTokNet's kCtnActionLen)
G_LEN, M_NUM, Q_LEN, M_MAX = 97, 128, 24, 5


def parse_net(s):
    """'DxL' or 'DxLxH' -> (d, layers, heads); heads default d // 32 (at least 1)."""
    p = [int(x) for x in s.lower().split("x")]
    if len(p) == 2:
        p.append(max(1, p[0] // 32))
    if len(p) != 3:
        raise ValueError(f"bad net spec {s!r}; want DxL or DxLxH")
    return tuple(p)


def synthetic_batch(B, cards, mons, statuses, queues, actions, rng):
    """A batch with every row at the given token counts and random ids / values in the embeddings' ranges."""
    def ints(lo, hi, shape):
        return torch.from_numpy(rng.integers(lo, hi, size=shape, dtype=np.int64))
    b = {
        "glob": torch.from_numpy(rng.normal(0, 3, (B, G_LEN)).astype(np.float32)),
        "relics": ints(0, 2, (B, 128)),
        "sbits": ints(0, 2, (B, 128)),
        "potions": ints(0, model.POT_V, (B, 5)),
        "mnum": torch.from_numpy(rng.normal(0, 2, (B, M_MAX, M_NUM)).astype(np.float32)),
        "nmon": torch.full((B,), mons, dtype=torch.int64),
        "nqueue": torch.full((B,), queues, dtype=torch.int64),
    }
    c = ints(0, 20, (B, cards, 9))
    c[..., 0] = ints(0, model.ZONE_V, (B, cards))
    c[..., 2] = ints(0, model.CARD_V, (B, cards))
    b["cards"] = c
    b["card_mask"] = torch.ones(B, cards, dtype=torch.bool)
    m = ints(0, model.MON_V, (B, M_MAX, 4))
    m[..., 0] = torch.arange(M_MAX)
    b["mcat"] = m
    s = ints(1, model.STAT_V, (B, max(1, statuses), 2))
    if statuses == 0:
        s.zero_()
    b["smap"] = s
    b["queues"] = ints(0, 30, (B, max(1, queues), Q_LEN))
    a = ints(0, 10, (B, actions, A_LEN))
    a[..., 0] = ints(0, 8, (B, actions))
    a[..., 2] = ints(0, model.CARD_V, (B, actions))
    a[..., 13] = ints(-1, mons, (B, actions))
    b["actions"] = a
    b["act_mask"] = torch.ones(B, actions, dtype=torch.bool)
    return b


def arrays_batch(A, B, rng):
    idx = rng.choice(A.n, size=B, replace=B > A.n)
    b = model.collate(A, idx)
    return {k: b[k] for k in ("glob", "relics", "sbits", "potions", "mnum", "nmon", "nqueue", "cards", "card_mask",
                              "mcat", "smap", "queues", "actions", "act_mask")}


def tokens_per_row(b):
    """Mean live tokens per row (global + cards + monsters + statuses + queues) and the padded token count."""
    live = (1 + b["card_mask"].sum(1) + b["nmon"] + (b["smap"][..., 0] > 0).sum(1) + b["nqueue"]).float().mean()
    padded = 1 + b["cards"].shape[1] + b["mcat"].shape[1] + b["smap"].shape[1] + b["queues"].shape[1]
    return float(live), int(padded)


def time_passes(fn, sync, warmup, iters):
    for _ in range(warmup):
        fn()
    sync()
    ts = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        sync()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", default="amber", choices=["amber", "combat"],
                    help="amber: tools/az_bench/amber_net.py (Amber Eye's shape, default); combat: tools/combat_net "
                         "CombatNet")
    ap.add_argument("--nets", help="comma list of DxL[xH]; amber also takes the size names 0.44M, 1.2M, 5.4M "
                                   "(default: amber 0.44M,1.2M,5.4M; combat 64x4,96x4,128x4)")
    ap.add_argument("--live-frac", type=float, default=1.0,
                    help="amber synthetic: share of each token segment that is live (1.0 = no padding)")
    ap.add_argument("--batches", default="256,1024,4096,8192", help="comma list of batch sizes")
    ap.add_argument("--dtype", default="bf16", choices=["fp16", "bf16", "fp32"], help="autocast dtype (combat: fp16 overflows CombatNet's -1e9 action mask; use bf16)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--cards", type=int, default=30, help="synthetic: card tokens per row (deck in all zones)")
    ap.add_argument("--mons", type=int, default=2, help="synthetic: live monsters per row (of 5 slots)")
    ap.add_argument("--statuses", type=int, default=8, help="synthetic: status-map tokens per row")
    ap.add_argument("--queues", type=int, default=1, help="synthetic: card-queue tokens per row")
    ap.add_argument("--actions", type=int, default=10, help="synthetic: legal actions per row")
    ap.add_argument("--arrays", help="tensorize.py output dir: sample real rows instead of synthetic ones")
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--no-h2d", action="store_true", help="skip the host-to-device timing")
    ap.add_argument("--compile", action="store_true", help="torch.compile the net (dynamic=False) before timing")
    ap.add_argument("--compile-mode", default="default",
                    help="torch.compile mode (default, reduce-overhead = CUDA graphs, max-autotune)")
    ap.add_argument("--seed", type=int, default=0, help="RNG seed for weights and synthetic inputs (not a game seed)")
    ap.add_argument("--out", help="write all measurements as JSON here")
    args = ap.parse_args(argv)
    if args.nets is None:
        args.nets = "0.44M,1.2M,5.4M" if args.arch == "amber" else "64x4,96x4,128x4"
    if args.arch == "amber" and args.arrays:
        ap.error("--arrays holds CombatNet rows; use it with --arch combat")

    dev = torch.device(args.device)
    cuda = dev.type == "cuda"
    if cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[args.dtype]
    use_autocast = dtype != torch.float32
    if use_autocast and not cuda and dtype == torch.float16:
        print("note: fp16 autocast on CPU is slow or unsupported; use --dtype bf16 or fp32 there", file=sys.stderr)
    sync = torch.cuda.synchronize if cuda else (lambda: None)
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    A = model.Arrays(args.arrays) if args.arrays else None

    info = {"device": torch.cuda.get_device_name(dev) if cuda else platform.processor() or "cpu",
            "torch": torch.__version__, "cuda": torch.version.cuda, "args": vars(args),
            "arch": args.arch, "input": "arrays" if A else "synthetic", "results": []}
    print(f"# device {info['device']}  torch {info['torch']}  arch {args.arch}  dtype {args.dtype}  "
          f"input {info['input']}")

    batches = [int(x) for x in args.batches.split(",")]
    if args.arch == "amber":
        host = {B: amber_net.synthetic_batch(B, actions=args.actions, rng=rng, live_frac=args.live_frac)
                for B in batches}
        count = amber_net.live_tokens
    else:
        host = {B: (arrays_batch(A, B, rng) if A else
                    synthetic_batch(B, args.cards, args.mons, args.statuses, args.queues, args.actions, rng))
                for B in batches}
        count = tokens_per_row

    for spec in args.nets.split(","):
        if args.arch == "amber":
            d, layers = amber_net.SIZES[spec] if spec in amber_net.SIZES else parse_net(spec)[:2]
            heads = parse_net(spec)[2] if spec not in amber_net.SIZES and spec.count("x") == 2 else None
            net = amber_net.AmberNet(d=d, layers=layers, heads=heads).to(dev).eval()
            heads = net.trunk.layers[0].self_attn.num_heads
        else:
            d, layers, heads = parse_net(spec)
            net = model.CombatNet(d=d, layers=layers, heads=heads, a_len=A_LEN).to(dev).eval()
        params = sum(p.numel() for p in net.parameters())
        run = torch.compile(net, dynamic=False, mode=args.compile_mode) if args.compile else net
        emb = sum(m.weight.numel() for m in net.modules() if isinstance(m, torch.nn.Embedding))
        for B in batches:
            hb = host[B]
            live, padded = count(hb)
            if cuda:
                hb = {k: v.pin_memory() for k, v in hb.items()}
            db = {k: v.to(dev) for k, v in hb.items()}

            def fwd(b):
                with torch.inference_mode(), torch.autocast(dev.type, dtype=dtype, enabled=use_autocast):
                    out = run(b)
                return out

            row = {"arch": args.arch, "net": f"{d}x{layers}x{heads}", "params": params, "params_non_embedding": params - emb,
                   "batch": B, "tokens_live": round(live, 2), "tokens_padded": padded}
            try:
                if cuda:
                    torch.cuda.reset_peak_memory_stats(dev)
                t = time_passes(lambda: fwd(db), sync, args.warmup, args.iters)
                row["gpu_ms"] = round(t * 1e3, 3)
                row["gpu_pos_per_s"] = round(B / t)
                if not args.no_h2d:
                    t2 = time_passes(lambda: fwd({k: v.to(dev, non_blocking=True) for k, v in hb.items()}),
                                     sync, args.warmup, args.iters)
                    row["h2d_ms"] = round(t2 * 1e3, 3)
                    row["h2d_pos_per_s"] = round(B / t2)
                if cuda:
                    row["peak_mem_mb"] = round(torch.cuda.max_memory_allocated(dev) / 2**20, 1)
            except torch.cuda.OutOfMemoryError:
                row["error"] = "out of memory"
                torch.cuda.empty_cache()
            info["results"].append(row)
            print(json.dumps(row), flush=True)
            del db
        del net
        if cuda:
            torch.cuda.empty_cache()

    if args.out:
        with open(args.out, "w") as f:
            json.dump(info, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
