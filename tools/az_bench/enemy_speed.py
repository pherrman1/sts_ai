"""Timing of the inference forward (and a training step) with and without the encounter-token parts, on a GPU:
python3 tools/az_bench/enemy_speed.py [--rows 2048 --d 128 --layers 4 --enc-frac 0.3 --fused-layer --profile]

Cases: off (net without encounter parts on the batch without encounter tokens), tokens (gate, no bias), bias (bias,
no gate), both; each eager and torch.compile (N marked dynamic as selfplay.py --compile). Inference: fp16, varlen
attention with row bounds, packed heads, packed tokens. Synthetic rows: ~--tokens live tokens, a share --enc-frac
of the rows (out-of-combat states) with 8-14 encounter tokens appended and boss / elite / hallway MAP tokens.
Prints ms per forward / step and, with --profile, the top CUDA kernels per case. Random weights (timing only)."""
import argparse
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amber_net as A  # noqa: E402


def batch(rows, enc_frac, tokens, seed):
    rng = np.random.default_rng(seed)
    counts = dict(A.DEFAULT_COUNTS, card=max(4, tokens - 22), monster=14, map=6)
    f = A.to_flat(A.synthetic_batch(rows, counts=counts, live_frac=0.6, rng=rng))
    g = torch.Generator().manual_seed(seed)
    tt = f["tok_type"]
    B, T = tt.shape
    ooc = torch.rand(B, generator=g) < enc_frac
    mon, mp = tt == A.TOKEN_TYPES.index("monster"), tt == A.TOKEN_TYPES.index("map")
    kind = torch.randint(0, 3, tt.shape, generator=g)
    f["ids"][..., 3] = torch.where(mon & ooc[:, None], A.ENC_KIND_BASE + kind, f["ids"][..., 3] % 900)
    room = torch.randint(0, 5, tt.shape, generator=g)
    for r, col in enumerate((6, 7, 9, 18)):
        f["f"][..., col] = torch.where(mp, (room == r).float(), f["f"][..., col])
    # combat rows: no MAP tokens and at most 4 monsters live (as the driver encodes them)
    drop = (mp | (mon & (torch.cumsum(mon.long(), 1) > 4))) & ~ooc[:, None]
    f["mask"] = f["mask"] & ~drop
    for key in ("a_src", "a_tgt"):
        x = f[key]
        on = (x >= 0) & ~torch.gather(f["mask"], 1, x.clamp(min=0))
        f[key] = torch.where(on, torch.full_like(x, -1), x)
    return f


def packed(f, dev, dt):
    f = {k: (v.to(dt) if v.is_floating_point() else v).to(dev) for k, v in f.items()}
    M = f["mask"].numel()
    pk, inv = A.pack_index(f["mask"], 256, inverse=True)
    ip = pk.clamp(max=M - 1)
    return dict(f, pack_idx=pk, unpack_idx=inv, seq_off=A.seq_offsets(f["mask"]),
                act_idx=torch.nonzero(f["a_mask"].reshape(-1)).squeeze(1),
                tok_type=f["tok_type"].reshape(M)[ip], ids=f["ids"].reshape(M, -1)[ip], f=f["f"].reshape(M, -1)[ip])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2048)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--tokens", type=int, default=41)
    ap.add_argument("--enc-frac", type=float, default=0.3)
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--train-batch", type=int, default=1024)
    ap.add_argument("--fused-layer", action="store_true")
    ap.add_argument("--no-row-bounds", action="store_true")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--train-packed", action="store_true", help="training batch with pack_idx (selfplay --train-packed)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--gate-key", action="store_true", help="the key gate (selfplay.py --enemy-gate-key)")
    ap.add_argument("--train-kernel", action="store_true",
                    help="training attention via varlen_attn_train (selfplay.py --enemy-train-kernel; needs "
                         "--train-packed)")
    a = ap.parse_args(argv)
    dev = a.device
    import torch._dynamo as dynamo
    dynamo.config.cache_size_limit = 1024
    dynamo.config.automatic_dynamic_shapes = False
    def sync():
        if dev == "cuda":
            torch.cuda.synchronize()

    V = A.load_kernel("varlen_attn")
    sys.modules["az_bench_varlen_attn"].ROW_BOUNDS = not a.no_row_bounds
    f = batch(a.rows, a.enc_frac, a.tokens, 1)
    st = A.strip_encounters(f)
    enc_rows = int((f["mask"].sum(1) != st["mask"].sum(1)).sum())
    print(f"torch {torch.__version__}, rows {a.rows}, rows with encounter tokens {enc_rows}, tok/row "
          f"{float(f['mask'].sum(1).float().mean()):.1f} (stripped {float(st['mask'].sum(1).float().mean()):.1f}), "
          f"row bounds {not a.no_row_bounds}, fused layer {a.fused_layer}", flush=True)
    cases = (("off", False, False), ("tokens", False, True), ("bias", True, False), ("both", True, True))
    for name, bias, gate in cases:
        torch.manual_seed(0)
        net = A.AmberNet(a.d, a.layers, enemy_bias=bias, enemy_gate=gate)
        with torch.no_grad():
            if net.enemy_gate is not None:
                net.enemy_gate.fill_(0.01)
            if net.enemy_bias is not None:
                net.enemy_bias.normal_(0, 0.01)
        net.gate_key = a.gate_key
        if a.train_kernel:
            net.train_attn = A.load_kernel("varlen_attn_train")
        tr = net.to(dev)
        inf = A.AmberNet(a.d, a.layers, enemy_bias=bias, enemy_gate=gate).to(dev)
        inf.load_state_dict(tr.state_dict())
        inf.gate_key = a.gate_key
        inf.train_attn = None
        inf = (inf.half() if dev == "cuda" else inf).eval()
        inf.sdpa = True
        inf.varlen_attn, inf.row_mean, inf.packed_heads = V, A.load_kernel("row_mean"), True
        if a.fused_layer:
            inf.fused_layer = A.load_fused_layer()
        src = st if name == "off" else f
        x = packed(src, dev, torch.float16 if dev == "cuda" else torch.float32)
        for k in ("act_idx", "pack_idx", "tok_type", "ids", "f"):
            dynamo.mark_dynamic(x[k], 0)
        res = {}
        modes = (("eager", inf),) if a.no_compile else (("eager", inf), ("compile", torch.compile(inf)))
        for mode, run in modes:
            with torch.no_grad():
                for _ in range(5):
                    run(x)
                sync()
                t0 = time.perf_counter()
                for _ in range(a.iters):
                    run(x)
                sync()
            res[mode] = (time.perf_counter() - t0) * 1e3 / a.iters
            if a.profile:
                from torch.profiler import ProfilerActivity, profile
                with torch.no_grad(), profile(activities=[ProfilerActivity.CUDA]) as p:
                    for _ in range(10):
                        run(x)
                    sync()
                print(f"--- {name} {mode}: top CUDA kernels (10 forwards)")
                print(p.key_averages().table(sort_by="cuda_time_total", row_limit=12))
        # training step (fp32 weights, bf16 autocast, padded flat batch as the trainer's)
        idx = np.random.default_rng(2).choice(a.rows, a.train_batch, replace=False)
        tb = {k: v[torch.as_tensor(idx)].to(dev) for k, v in src.items()}
        if a.train_packed:
            tb["pack_idx"] = A.pack_index(tb["mask"], 16)
        tr.train()
        tr.sdpa = True
        opt = torch.optim.Adam(tr.parameters(), lr=1e-6)
        for i in range(13):
            if i == 3:
                sync()
                t0 = time.perf_counter()
            with torch.autocast(dev, dtype=torch.bfloat16, enabled=dev == "cuda"):
                o = tr(tb)
                loss = o[0].float().masked_fill(~tb["a_mask"], 0).sum() + o[1].float().logsumexp(-1).sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
        sync()
        res["train_step"] = (time.perf_counter() - t0) * 1e3 / 10
        if a.profile and dev == "cuda":
            from torch.profiler import ProfilerActivity, profile
            with profile(activities=[ProfilerActivity.CUDA]) as p:
                for _ in range(3):
                    with torch.autocast(dev, dtype=torch.bfloat16):
                        o = tr(tb)
                        loss = o[0].float().masked_fill(~tb["a_mask"], 0).sum() + o[1].float().logsumexp(-1).sum()
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                sync()
            print(f"--- {name} train: top CUDA kernels (3 steps)")
            print(p.key_averages().table(sort_by="cuda_time_total", row_limit=15))
        print(f"{name:7s} " + "  ".join(f"{k} {v:7.2f} ms" for k, v in res.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
