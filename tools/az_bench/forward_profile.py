#!/usr/bin/env python3
"""Stage 0 throughput bench: where the GPU time of one AmberNet flat forward goes, and how much each forward variant
saves. Measures, for one batch shape (default 2048 rows x 56 token slots x 32 action slots, the shape of the best e2e
run so far), the compiled forward of each variant with the net's weights shared, checks each variant's outputs
against the eager fp32 reference, and prints the top CUDA kernels of a variant from torch.profiler.

Variants (comma list, --variants):
  ref        forward_flat under autocast (what e2e_bench.py runs)
  sdpa       ref with AmberNet.sdpa = True (one QKV matmul + F.scaled_dot_product_attention per layer)
  half       ref with the weights cast to the autocast dtype and autocast off
  sdpa_half  both
  packed     forward_packed (per-token work on live tokens only; pack_idx padded to --pack-step)
  packed_half  packed with half weights
  gpacked, gpacked_half  packed with unpack_idx (padded layout by one gather instead of zero fill + scatter)
  any name containing "ffn" (e.g. gpacked_half_ffn): LayerNorm + FFN + residual as one Triton kernel (fused_ffn.py)
  any name containing "math" (e.g. gpacked_half_math): attention as plain matmuls + fp32 softmax (AmberNet.attn_math)
A suffix "#BACKEND" compiles that variant with another torch.compile backend: torch_tensorrt (needs the
torch-tensorrt package; fp16 kernels enabled) or emmy (cloudrift-ai/emmy, `pip install "emmy-ml[compile]"`).
A suffix "@MODE" compiles that variant with torch.compile mode MODE (e.g. sdpa_half@max-autotune-no-cudagraphs).

The batch is synthetic: each row has a random number of live tokens (--min-tokens..T, run token first, the rest
grouped by type as nextBatchFlat writes them) and a random number of live actions whose sources / targets point at
live tokens. No game seeds are driven.

usage: forward_profile.py [--net 0.44M] [--rows 2048] [--tokens 56] [--actions 32] [--dtype fp16]
                          [--variants ref,sdpa,half,sdpa_half] [--profile ref,sdpa] [--no-compile] [--out prof.json]
"""

import argparse
import copy
import importlib.util
import json
import os
import time

import numpy as np

# Name each inductor kernel after the ops it fuses (otherwise every Triton kernel shows up as "triton_").
os.environ.setdefault("TORCHINDUCTOR_UNIQUE_KERNEL_NAMES", "1")
import torch  # noqa: E402

try:
    import torch._inductor.config as _ic
    _ic.triton.unique_kernel_names = True
except (ImportError, AttributeError):
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
amber_net = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amber_net)


def flat_batch(R, T, A, rng, min_tokens=20, min_actions=4):
    """A flat batch as nextBatchFlat lays it out: per row n live tokens (run token first, then the other types in
    TOKEN_TYPES order), padding after them; n_a live actions."""
    K = len(amber_net.TOKEN_TYPES)
    tt = np.zeros((R, T), np.int64)
    mask = np.zeros((R, T), bool)
    a_src = np.full((R, A), -1, np.int64)
    a_tgt = np.full((R, A), -1, np.int64)
    a_mask = np.zeros((R, A), bool)
    for r in range(R):
        n = int(rng.integers(min(min_tokens, T), T + 1))
        tt[r, 1:n] = np.sort(rng.integers(1, K, n - 1))
        mask[r, :n] = True
        na = int(rng.integers(min(min_actions, A), A + 1))
        a_mask[r, :na] = True
        a_src[r, :na] = np.where(rng.random(na) < 0.8, rng.integers(1, max(2, n), na), -1)
        a_tgt[r, :na] = np.where(rng.random(na) < 0.5, rng.integers(1, max(2, n), na), -1)
    a_mask[:, 0] = True
    return {"tok_type": torch.from_numpy(tt), "ids": torch.from_numpy(rng.integers(1, amber_net.ID_VOCAB, (R, T, 4))),
            "f": torch.from_numpy(rng.normal(0, 1, (R, T, 64)).astype(np.float32)), "mask": torch.from_numpy(mask),
            "a_type": torch.from_numpy(rng.integers(0, amber_net.ACTION_TYPES, (R, A))),
            "a_src": torch.from_numpy(a_src), "a_tgt": torch.from_numpy(a_tgt),
            "a_f": torch.from_numpy(rng.normal(0, 1, (R, A, 8)).astype(np.float32)), "a_mask": torch.from_numpy(a_mask)}


def compile_backend(net, backend, dtype):
    if backend == "torch_tensorrt":
        import torch_tensorrt  # noqa: F401  (registers the backend)
        return torch.compile(net, backend="torch_tensorrt", dynamic=False,
                             options={"enabled_precisions": {dtype, torch.float32}, "min_block_size": 1,
                                      "truncate_double": True})
    if backend == "emmy":
        try:
            import emmy  # noqa: F401  (registers the backend if the package does so on import)
        except ImportError:
            pass
        return torch.compile(net, backend="emmy", dynamic=False)
    return torch.compile(net, backend=backend, dynamic=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--net", default="0.44M")
    ap.add_argument("--rows", type=int, default=2048)
    ap.add_argument("--tokens", type=int, default=56)
    ap.add_argument("--actions", type=int, default=32)
    ap.add_argument("--min-tokens", type=int, default=20)
    ap.add_argument("--dtype", default="fp16", choices=["fp16", "bf16"])
    ap.add_argument("--variants", default="ref,sdpa,half,sdpa_half")
    ap.add_argument("--profile", default="ref,sdpa", help="variants whose top kernels are printed")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--pack-step", type=int, default=2048)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out")
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = {"fp16": torch.float16, "bf16": torch.bfloat16}[args.dtype]
    torch.manual_seed(args.seed)
    d, layers = amber_net.SIZES.get(args.net) or tuple(int(v) for v in args.net.lower().split("x"))
    base = amber_net.AmberNet(d, layers).eval().to(dev)
    x = {k: v.to(dev) for k, v in flat_batch(args.rows, args.tokens, args.actions, np.random.default_rng(args.seed),
                                               args.min_tokens).items()}
    with torch.inference_mode():
        ref = [o.float() for o in base(x)]

    results = []
    for name in args.variants.split(","):
        vname, _, mode = name.partition("@")
        vname, _, backend = vname.partition("#")
        net = copy.deepcopy(base)
        net.sdpa = "sdpa" in vname or "packed" in vname
        net.attn_math = "math" in vname
        net.fused_ffn = "ffn" in vname
        half = "half" in vname
        if half:
            net = net.to(dtype)
        xin = {k: (v.to(dtype) if half and v.is_floating_point() else v) for k, v in x.items()}
        if "gpacked" in vname:
            xin["pack_idx"], xin["unpack_idx"] = amber_net.pack_index(x["mask"], args.pack_step, inverse=True)
        elif "packed" in vname:
            xin["pack_idx"] = amber_net.pack_index(x["mask"], args.pack_step)
        if args.no_compile:
            run = net
        elif backend:
            run = compile_backend(net, backend, dtype)
        else:
            run = torch.compile(net, dynamic=False, mode=mode or "default")
        ac = torch.autocast(dev.type, dtype=dtype, enabled=not half)

        def step():
            with torch.inference_mode(), ac:
                return run(xin)

        tc = time.perf_counter()
        out = step()
        if dev.type == "cuda":
            torch.cuda.synchronize()
        compile_s = time.perf_counter() - tc
        live = x["a_mask"]
        err = {"logits": float((out[0].float() - ref[0]).abs()[live].max()),
               "outcome": float((out[1].float() - ref[1]).abs().max()),
               "p_win": float((torch.softmax(out[1].float(), -1)[:, 0] - torch.softmax(ref[1], -1)[:, 0]).abs().max())}
        for _ in range(args.warmup):
            step()
        if dev.type == "cuda":
            torch.cuda.synchronize()
            e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            e0.record()
            for _ in range(args.iters):
                step()
            e1.record()
            torch.cuda.synchronize()
            ms = e0.elapsed_time(e1) / args.iters
        else:
            t0 = time.perf_counter()
            for _ in range(args.iters):
                step()
            ms = (time.perf_counter() - t0) * 1e3 / args.iters
        r = {"variant": name, "live_tokens_per_row": round(float(x["mask"].float().sum(1).mean()), 1), "ms_per_batch": round(ms, 3), "positions_per_s": round(args.rows / ms * 1e3),
             "compile_s": round(compile_s, 1), "max_abs_err_vs_fp32": err}
        print(json.dumps(r), flush=True)
        if name in args.profile.split(",") and dev.type == "cuda":
            from torch.profiler import ProfilerActivity, profile
            with profile(activities=[ProfilerActivity.CUDA]) as prof:
                for _ in range(10):
                    step()
                torch.cuda.synchronize()
            table = prof.key_averages().table(sort_by="cuda_time_total", row_limit=40, max_name_column_width=160)
            print(f"# top kernels, {name} (10 batches)\n{table}", flush=True)
            r["profile"] = table
        results.append(r)

    if args.out:
        with open(args.out, "w") as f:
            json.dump({"device": torch.cuda.get_device_name(0) if dev.type == "cuda" else "cpu",
                       "torch": torch.__version__, "args": vars(args), "results": results}, f, indent=1)


if __name__ == "__main__":
    main()
