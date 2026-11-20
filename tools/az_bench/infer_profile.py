#!/usr/bin/env python3
"""Where the GPU time of Stage 1 inference goes on real states: the self-play inference path (selfplay.py:
forward_packed, fp16, varlen attention, three-kernel layers, torch.compile) timed and profiled on rows drawn from a
saved replay window, in the batch layout the run uses (rows padded to the row bucket, the token axis to the token
bucket of the longest row, actions to the action bucket).

Variants on the same rows, to attribute the cost:
  real          the batch as the run forms it
  real_Rtight   the same without the empty rows of the row bucket (rows padded to the next multiple of 64)
  short_T64     only its rows of at most 64 tokens, token bucket 64
  short_Tbig    the same rows with real's token bucket: what the bucket of the longest row costs the short rows
  uniform       real's live tokens cut into rows of equal length (the mean), as in the Stage 0 bench
torch.profiler's top CUDA kernels are printed for `real` (GPU only).

The window's samples are the root states of real moves; the run's inference batches are search leaves of such
states, so the lengths are close but not the same population. No game seeds are driven. Needs the GPU to itself
for clean numbers (stop the run first); on a CPU it runs the padded path as a smoke test.

usage: infer_profile.py --module-dir BUILD_DIR --ckpt CKPT.pt --replay DIR [--rows 1314] [--batches 4]
                        [--iters 30] [--out prof.json]
"""

import argparse
import copy
import json
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))


def bucket(buckets, n):
    """The smallest bucket holding n (the largest bucket when none does), as the driver picks it."""
    return next((b for b in buckets if b >= n), buckets[-1])


def split_rows(b):
    """A Replay.sample(packed=True) batch -> per-row token counts and the live packed tokens / actions."""
    nt = b["mask"].sum(1).astype(np.int64)
    n = int(nt.sum())
    na = b["a_mask"].sum(1).astype(np.int64)
    return {"nt": nt, "na": na, "tok_type": b["tok_type"][:n], "ids": b["ids"][:n], "f": b["f"][:n],
            "a_type": b["a_type"], "a_src": b["a_src"], "a_tgt": b["a_tgt"], "a_f": b["a_f"]}


def take_rows(r, keep):
    """The rows keep (bool [B]) of split_rows' result."""
    tok_keep = np.repeat(keep, r["nt"])
    out = {"nt": r["nt"][keep], "na": r["na"][keep]}
    for k in ("tok_type", "ids", "f"):
        out[k] = r[k][tok_keep]
    for k in ("a_type", "a_src", "a_tgt", "a_f"):
        out[k] = r[k][keep]
    return out


def uniform_rows(r):
    """r's live tokens cut into rows of equal length (the mean); action sources / targets clipped into the row."""
    L = max(2, int(round(float(r["nt"].mean()))))
    B = len(r["tok_type"]) // L
    out = {"nt": np.full(B, L, np.int64), "na": r["na"][:B]}
    for k in ("tok_type", "ids", "f"):
        out[k] = r[k][:B * L]
    for k in ("a_type", "a_f"):
        out[k] = r[k][:B]
    for k in ("a_src", "a_tgt"):
        out[k] = np.minimum(r[k][:B], L - 1)
    return out


def flat_input(r, Rp, Tp, Ap, pack_step):
    """The inference batch selfplay's loop builds from next_flat(packed_tokens=True): host arrays in the driver's
    dtypes. As az_pack.h packFlat: each padding row (B .. Rp) has one live token (type 0, ids 0, floats 0) and one
    live action; packed entries past the live tokens are trash (slot Rp * Tp)."""
    B = len(r["nt"])
    nt, na = r["nt"], r["na"]
    if B > Rp or int(nt.max()) > Tp:
        raise ValueError("rows or tokens exceed the buckets")
    n = int(nt.sum())
    n_all = n + (Rp - B)
    npad = -(-n_all // pack_step) * pack_step
    rows_t = np.repeat(np.arange(B), nt)
    cols_t = np.arange(n) - np.repeat(np.cumsum(nt) - nt, nt)
    h = {"tok_type": np.zeros(npad, np.int8), "ids": np.zeros((npad, r["ids"].shape[1]), np.int16),
         "f": np.zeros((npad, r["f"].shape[1]), np.float16), "pack_idx": np.full(npad, Rp * Tp, np.int32),
         "mask": np.zeros((Rp, Tp), bool), "seq_off": np.zeros(Rp + 1, np.int32),
         "a_type": np.zeros((Rp, Ap), np.int16), "a_src": np.full((Rp, Ap), -1, np.int16),
         "a_tgt": np.full((Rp, Ap), -1, np.int16), "a_f": np.zeros((Rp, Ap, r["a_f"].shape[2]), np.float16),
         "a_mask": np.zeros((Rp, Ap), bool)}
    h["tok_type"][:n], h["ids"][:n], h["f"][:n] = r["tok_type"], r["ids"], r["f"]
    h["pack_idx"][:n] = rows_t * Tp + cols_t
    h["mask"][rows_t, cols_t] = True
    h["seq_off"][1:B + 1] = np.cumsum(nt)
    h["seq_off"][B + 1:] = n + 1 + np.arange(Rp - B)
    h["pack_idx"][n:n_all] = np.arange(B, Rp) * Tp   # the padding rows' tokens (zeros)
    h["mask"][B:, 0] = True
    h["a_mask"][B:, 0] = True
    A = min(Ap, r["a_type"].shape[1])
    na = np.minimum(na, A)
    h["a_mask"][:B, :A] = np.arange(A)[None, :] < na[:, None]
    for k in ("a_type", "a_src", "a_tgt", "a_f"):
        h[k][:B, :A] = r[k][:, :A]
    return h, {"rows": B, "Rp": Rp, "Tp": Tp, "Ap": Ap, "live_tokens": n, "npad": npad,
               "tokens_mean": round(float(nt.mean()), 1), "tokens_max": int(nt.max()),
               "sum_sq_tokens": int((nt * nt).sum())}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--ckpt", required=True, help="a checkpoint of the run (weights and the run's flags)")
    ap.add_argument("--replay", required=True, help="the run's saved window (--replay-save directory)")
    ap.add_argument("--rows", type=int, default=1314, help="live rows per batch (the run's mean)")
    ap.add_argument("--batches", type=int, default=4, help="batches drawn from the window")
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--variants", default="real,real_Rtight,short_T64,short_Tbig,uniform")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    sys.path.insert(0, args.module_dir)
    sys.path.insert(0, HERE)
    import az_bench_native  # noqa: E402
    import selfplay as sp  # noqa: E402
    amber_net = sp.amber_net

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    a = ck["args"]
    d, layers = ck["net_size"]
    amber = a["utility"] in ("amber", "amber2", "amber2-root")
    ema_lam = 0.5 ** (1.0 / a["value_ema_halflife"]) if a.get("value_ema_halflife", 0) > 0 else 0.0
    dev = torch.device(args.device)
    cuda = dev.type == "cuda"

    # ---- rows from the saved window (the run's layout, from its flags) ----
    t0 = time.time()
    replay = sp.Replay(a["window"], hp_floors=56 if amber else 0, soft_outcome=ema_lam > 0,
                       compact=a["compact_samples"], dict_tokens_per_sample=a["replay_dict_tokens"],
                       token_store=az_bench_native.TokenStore if a["compact_samples"] else None,
                       tokens_per_sample=a["replay_tokens_per_sample"],
                       actions_per_sample=a["replay_actions_per_sample"],
                       compress_targets=a["compress_targets"], soft_bytes_per_sample=a["replay_soft_bytes"],
                       hp_runs_per_sample=a["replay_hp_runs"])
    replay.load(args.replay)
    rng = np.random.default_rng(args.seed)
    live = (replay.s_tail + np.arange(len(replay))) % replay.cs
    nt_all = replay.ntok[live[rng.integers(0, len(live), min(len(live), 500000))]].astype(np.int64)
    lengths = {"samples": len(replay), "mean": round(float(nt_all.mean()), 2),
               **{f"p{q}": int(np.percentile(nt_all, q)) for q in (50, 90, 99)}, "max": int(nt_all.max()),
               "share_over_64": round(float((nt_all > 64).mean()), 4),
               "share_over_128": round(float((nt_all > 128).mean()), 4)}
    print(json.dumps({"window": lengths, "load_s": round(time.time() - t0, 1)}), flush=True)
    row_b = [int(v) for v in a["row_buckets"].split(",") if int(v) <= a["batch"]] or [a["batch"]]
    tok_b = [int(v) for v in a["tok_buckets"].split(",")]
    act_b = [int(v) for v in a["act_buckets"].split(",")]
    step_n = a["pack_step"] or 1
    batches = [split_rows(replay.sample(rng, min(args.rows, row_b[-1]), 0.0, packed=True))
               for _ in range(args.batches)]
    del replay

    # ---- the inference net as selfplay.py sets it up ----
    net = amber_net.AmberNet(d=d, layers=layers, hp_floors=56 if amber else 1, soft_policy=a["w_soft_policy"] > 0)
    net.load_state_dict(ck["net"])
    infer = copy.deepcopy(net).to(dev).eval()
    infer.sdpa = True
    if cuda:
        infer.varlen_attn = amber_net.load_kernel("varlen_attn")
        if a.get("fused_layer"):
            infer.fused_layer = amber_net.load_fused_layer()
        infer = infer.half()
    infer_dtype = torch.float16 if cuda else torch.float32
    compiled = bool(a.get("compile")) and not args.no_compile
    if compiled:
        import torch._dynamo as dynamo
        dynamo.config.cache_size_limit = 1024
        dynamo.config.accumulated_cache_size_limit = 4096
        dynamo.config.automatic_dynamic_shapes = False
        run = torch.compile(infer)
    else:
        run = infer

    def to_device(h):
        x = {}
        for k, v in h.items():
            t = torch.from_numpy(v).to(dev)
            if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt", "pack_idx"):
                t = t.long()
            elif t.dtype == torch.float16:
                t = t.to(infer_dtype)
            x[k] = t
        if not cuda:   # the CPU path has no varlen kernel: padded attention, as selfplay.py on a CPU
            x.pop("seq_off")
        if compiled:
            for k in ("pack_idx", "tok_type", "ids", "f"):
                torch._dynamo.mark_dynamic(x[k], 0)
        return x

    def step(x, rows, Ap):
        with torch.inference_mode():
            lg, outcome, hp, hpf = run(x)
            Fv, ehp = sp.search_values(outcome[:rows], hp[:rows])   # the run's output side
            return lg[:rows].float(), Fv, ehp, hpf[:rows].float().clamp(0, 1), torch.softmax(outcome[:rows].float(), -1)

    def timed(x, rows, Ap):
        for _ in range(args.warmup):
            step(x, rows, Ap)
        if cuda:
            torch.cuda.synchronize()
            e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            e0.record()
            t = time.perf_counter()
            for _ in range(args.iters):
                step(x, rows, Ap)
            launch = (time.perf_counter() - t) * 1e3 / args.iters   # CPU side: the launches queue on the GPU
            e1.record()
            torch.cuda.synchronize()
            return e0.elapsed_time(e1) / args.iters, launch
        t = time.perf_counter()
        for _ in range(args.iters):
            step(x, rows, Ap)
        ms = (time.perf_counter() - t) * 1e3 / args.iters
        return ms, ms

    want = args.variants.split(",")
    results, prof_table = [], None
    for bi, r in enumerate(batches):
        Tp = bucket(tok_b, int(r["nt"].max()))
        Ap = bucket(act_b, int(r["na"].max()))
        Rp = bucket(row_b, len(r["nt"]))
        short = take_rows(r, r["nt"] <= 64)
        uni = uniform_rows(r)
        forms = {"real": (r, Rp, Tp, Ap), "real_Rtight": (r, min(Rp, -(-len(r["nt"]) // 64) * 64), Tp, Ap),
                 "short_T64": (short, Rp, 64, Ap), "short_Tbig": (short, Rp, Tp, Ap),
                 "uniform": (uni, Rp, bucket(tok_b, int(uni["nt"].max())), Ap)}
        for name in want:
            rr, rp, tp, apn = forms[name]
            if not len(rr["nt"]):   # no row of at most 64 tokens in this batch
                continue
            h, info = flat_input(rr, rp, tp, apn, step_n)
            x = to_device(h)
            ms, launch = timed(x, info["rows"], apn)
            res = dict(info, batch=bi, variant=name, ms_per_batch=round(ms, 3), launch_ms=round(launch, 3),
                       us_per_row=round(ms * 1e3 / info["rows"], 3),
                       us_per_token=round(ms * 1e3 / info["live_tokens"], 4))
            print(json.dumps(res), flush=True)
            results.append(res)
            if name == "real" and bi == 0 and cuda:
                from torch.profiler import ProfilerActivity, profile
                with profile(activities=[ProfilerActivity.CUDA]) as prof:
                    for _ in range(10):
                        step(x, info["rows"], apn)
                    torch.cuda.synchronize()
                prof_table = prof.key_averages().table(sort_by="cuda_time_total", row_limit=40,
                                                       max_name_column_width=120)
                print(f"# top CUDA kernels, real, batch 0 (10 batches)\n{prof_table}", flush=True)
    summary = {}
    for name in want:
        rs = [x for x in results if x["variant"] == name]
        summary[name] = {"ms_per_batch": round(float(np.mean([x["ms_per_batch"] for x in rs])), 3),
                         "us_per_row": round(float(np.mean([x["us_per_row"] for x in rs])), 3),
                         "us_per_token": round(float(np.mean([x["us_per_token"] for x in rs])), 4),
                         "Tp": sorted({x["Tp"] for x in rs}), "rows": round(float(np.mean([x["rows"] for x in rs])))}
    print(json.dumps({"summary": summary}), flush=True)
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"device": torch.cuda.get_device_name(0) if cuda else "cpu", "torch": torch.__version__,
                       "args": vars(args), "compiled": compiled, "window": lengths, "results": results,
                       "summary": summary, "profile": prof_table}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
