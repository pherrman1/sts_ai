#!/usr/bin/env python3
"""GPU bench of the whole-net kernel (fused_net.py) against the current self-play inference path (forward_packed,
fp16, varlen attention + fused layers, torch.compile: tools/az_bench/selfplay.py --packed-h2d --fused-layer --compile)
on synthetic packed batches shaped like self-play's.

    python3 tools/az_bench/fused_net_bench.py [--rows 2048] [--mean-tokens 26] [--net 0.44M] [--sweep]

Prints positions / s of both paths, the max abs difference of their outputs, and the kernel's useful TFLOP/s and MFU
(live tokens only, attention within rows only: Amber Eye's "MFU ... after discounting padded attention operations";
--peak-tflops default 32.4 = RTX 3060 Ti FP16 tensor cores with FP32 accumulation). --sweep tries tile / warp
settings (fresh process per setting: the knobs are read at import). Do not run while another job owns the GPU.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    key = "az_bench_" + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, name + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[key] = m
        spec.loader.exec_module(m)
    return sys.modules[key]


def synthetic_packed(A, tokens, actions, seed=0, extra_rows=0, a_frac=0.7):
    """A packed batch as RunDriver.next_flat(packed_tokens=True) writes it (int8 / int16 / fp32 here) plus the
    [R, T]-layout inputs forward_packed takes for the same rows. Row r has tokens[r] live tokens (the run token first,
    the others of random types in type order) and `actions` action slots, a share a_frac live; src / tgt point at
    random tokens of the row or -1. extra_rows empty rows follow (row bucket padding)."""
    rng = np.random.default_rng(seed)
    rows = len(tokens)
    R = rows + extra_rows
    tt, ids, f, so = [], [], [], [0]
    for n in tokens:
        tt += [0] + list(np.sort(rng.integers(1, len(A.TOKEN_TYPES), n - 1)))
        ids.append(rng.integers(0, A.ID_VOCAB, (n, 4)))
        f.append(rng.normal(0, 1, (n, 64)))
        so.append(so[-1] + n)
    so += [so[-1]] * extra_rows
    b = {"tok_type": torch.tensor(tt, dtype=torch.int8), "ids": torch.from_numpy(np.concatenate(ids)).short(),
         "f": torch.from_numpy(np.concatenate(f)).float(), "seq_off": torch.tensor(so, dtype=torch.int32)}
    src = np.full((R, actions), -1)
    tgt = np.full((R, actions), -1)
    for r, n in enumerate(tokens):
        src[r] = np.where(rng.random(actions) < 0.8, rng.integers(0, n, actions), -1)
        tgt[r] = np.where(rng.random(actions) < 0.4, rng.integers(0, n, actions), -1)
    b["a_type"] = torch.from_numpy(rng.integers(0, A.ACTION_TYPES, (R, actions))).short()
    b["a_src"] = torch.from_numpy(src).short()
    b["a_tgt"] = torch.from_numpy(tgt).short()
    b["a_f"] = torch.from_numpy(rng.normal(0, 1, (R, actions, 8))).float()
    b["a_mask"] = torch.from_numpy(rng.random((R, actions)) < a_frac)
    b["a_mask"][:, 0] = True
    mask = torch.zeros(R, max(tokens), dtype=torch.bool)
    for r, n in enumerate(tokens):
        mask[r, :n] = True
    ref = {k: (v.long() if v.dtype in (torch.int8, torch.int16) else v) for k, v in b.items()}
    ref["mask"] = mask
    ref["pack_idx"] = A.pack_index(mask)
    return b, ref


def useful_flops(tokens, a_live, d, layers, hid, nf=64, n_out=57, n_hp=256, n_hpf=56):
    """Multiply-adds x 2 of the net on live tokens, attention within each row only."""
    n = np.asarray(tokens, dtype=np.float64)
    per_tok = 2 * nf * d + layers * 2 * (4 * d * d + 2 * d * hid)
    attn = layers * 4 * d * n * n                   # QK^T and PV
    heads = 2 * (2 * d * d + 3 * d * d + d * (n_out + n_hp + n_hpf) + d * d)   # summary, 3 heads, W_c c
    pol = a_live * 2 * (3 * d * d + 8 * d + d)     # W_s h, W_t h, pol MLP, W_f f
    return float((n * per_tok + attn + heads).sum() + pol.sum())


def timeit(fn, iters, warm=10):
    for _ in range(warm):
        fn()
    torch.cuda.synchronize()
    t = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t) / iters


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=2048)
    ap.add_argument("--mean-tokens", type=float, default=26.0, help="mean live tokens per row (card stacks: ~26)")
    ap.add_argument("--max-tokens", type=int, default=212)
    ap.add_argument("--actions", type=int, default=16, help="action slots per row (act bucket)")
    ap.add_argument("--net", default="0.44M")
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--peak-tflops", type=float, default=32.4)
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--json", action="store_true", help="one JSON line (used by --sweep)")
    args = ap.parse_args(argv)
    if args.sweep:
        for tile, warps, rows in ((64, 4, 16), (64, 8, 16), (128, 4, 16), (128, 8, 16), (128, 8, 32), (256, 8, 16),
                                  (256, 16, 16)):
            env = dict(os.environ, AZ_FUSED_NET_TILE=str(tile), AZ_FUSED_NET_WARPS=str(warps),
                       AZ_FUSED_NET_ROWS=str(rows))
            cmd = [sys.executable, __file__, "--json", "--no-baseline", "--rows", str(args.rows), "--mean-tokens",
                   str(args.mean_tokens), "--net", args.net, "--iters", str(args.iters)]
            r = subprocess.run(cmd, env=env, capture_output=True, text=True)
            line = r.stdout.strip().splitlines()[-1] if r.returncode == 0 else r.stderr.strip()[-300:]
            print(f"tile {tile} warps {warps} rows/tile {rows}: {line}", flush=True)
        return 0

    A = _load("amber_net")
    K = _load("fused_net")
    dev = torch.device("cuda")
    d, layers = A.SIZES[args.net]
    torch.manual_seed(0)
    net = A.jitter_1d_params(A.AmberNet(d, layers, hp_floors=56).eval())
    with torch.no_grad():
        net.a_none.normal_()
    net.sdpa = True
    rng = np.random.default_rng(1)
    # token counts: lognormal around the mean, clipped to [4, max]
    sig = 0.5
    tokens = np.clip(np.round(rng.lognormal(np.log(args.mean_tokens) - sig * sig / 2, sig, args.rows)), 4,
                     args.max_tokens).astype(int).tolist()
    b, ref = synthetic_packed(A, tokens, args.actions, seed=2)
    a_live = ref["a_mask"].sum(1).numpy()
    flops = useful_flops(tokens, a_live, d, layers, 4 * d)

    net32 = net.to(dev)
    with torch.no_grad():
        want = net32({k: v.to(dev) for k, v in ref.items()})
    infer = __import__("copy").deepcopy(net32).half()
    fused = K.FusedNet(infer)
    bd = {k: v.to(dev) for k, v in b.items()}
    bd["f"], bd["a_f"] = bd["f"].half(), bd["a_f"].half()
    so_host = b["seq_off"].numpy()
    res = {"rows": args.rows, "mean_tokens": float(np.mean(tokens)), "tile": K.TILE, "warps": K.WARPS,
           "rows_per_tile": K.SM_ROWS}
    with torch.inference_mode():
        got = fused(bd, K.make_tiles(so_host, args.rows), args.rows)
        res["max_err_vs_fp32"] = {k: round(float((w.float() - g.float()).abs().max()), 5)
                                  for k, w, g in zip(("logits", "outcome", "hp", "hpf"), want, got)}
        t_tiles = time.perf_counter()
        for _ in range(20):
            tiles = K.make_tiles(so_host, args.rows)
        res["make_tiles_ms"] = round((time.perf_counter() - t_tiles) / 20 * 1e3, 3)
        res["tiles"] = [len(tiles["small"][0]), len(tiles["big"][0])]
        res["tile_fill"] = round(sum(tokens) / (len(tiles["small"][0]) * K.TILE + len(tiles["big"][0]) * K.BIG_TILE),
                                 3)
        sec = timeit(lambda: fused(bd, tiles, args.rows), args.iters)
        res["fused_pos_per_s"] = round(args.rows / sec)
        res["fused_tflops"] = round(flops / sec / 1e12, 2)
        res["fused_mfu"] = round(flops / sec / 1e12 / args.peak_tflops, 3)
        if not args.no_baseline:
            infer.varlen_attn = A.load_kernel("varlen_attn")
            infer.fused_layer = A.load_fused_layer()
            import torch._dynamo as dynamo
            dynamo.config.cache_size_limit = 64
            run = torch.compile(infer)
            x = {k: v.to(dev) for k, v in ref.items()}
            x["f"], x["a_f"] = x["f"].half(), x["a_f"].half()
            torch._dynamo.mark_dynamic(x["pack_idx"], 0)
            base = run(x)
            res["max_err_fused_vs_baseline"] = {k: round(float((w.float() - g.float()).abs().max()), 5)
                                                for k, w, g in zip(("logits", "outcome", "hp", "hpf"), base, got)}
            sec_b = timeit(lambda: run(x), args.iters)
            res["baseline_pos_per_s"] = round(args.rows / sec_b)
            res["baseline_mfu"] = round(flops / sec_b / 1e12 / args.peak_tflops, 3)
            res["speedup"] = round(sec_b / sec, 2)
    print(json.dumps(res) if args.json else json.dumps(res, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
