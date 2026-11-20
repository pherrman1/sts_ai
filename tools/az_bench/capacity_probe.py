"""Offline capacity probe (2026-11-21): is the stage 1 self-play net capacity-limited?

Trains AmberNet sizes from scratch on one fixed sample of a saved replay window (selfplay.py --replay-save), with the
training step of selfplay.py's trainer (same losses and weights, AdamW, warmup, grad clip 1.0, bf16 autocast on CUDA),
the same sample budget and the same batch sequence for every net, and logs held-out losses per head and the top-1
agreement with the search policy. A clearly lower held-out loss of the larger net at an equal budget means the small net
is capacity-limited on this data; equal losses mean a larger net would mostly cost inference speed.

Read-only on the replay: every array is opened with np.load(mmap_mode="r"), so the window is never copied into memory;
the pages a batch touches go through the page cache (reclaimable). Held-out split by run (the sample's run counter,
hp_ref), so no run has samples on both sides.

  python3 tools/az_bench/capacity_probe.py --replay ~/Documents/sts/stage1/amber_scratch/replay \
      --samples 2000000 --budget 20000000 --nets 0.44M,1.2M --out probe.json

--nets takes amber_net.SIZES keys or DxL (width x layers; heads = D // 32). --init-ckpt CKPT adds a reference row:
the 0.44M net from that checkpoint, evaluated before and after the same budget (its held-out samples were seen by the
live run, so it is a reference, not an unseen test). --infer-bench times the plain inference forward (fp16, eval mode,
padded flat layout, not selfplay.py's packed kernels) per net on the device. Aborts when MemAvailable falls below
--min-avail-gb (checked at start and at every eval).
"""

import argparse
import importlib.util
import json
import math
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("az_selfplay", os.path.join(HERE, "selfplay.py"))
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)
amber_net = sp.amber_net


def mem_available_gb():
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2 ** 20
    except OSError:
        pass
    return float("nan")


class ReplayView(sp.Replay):
    """A saved window opened read-only by memory map, sampled with Replay._gather (same batches as the trainer)."""

    def __init__(self, path):   # noqa: super().__init__ would allocate the window
        with open(os.path.join(path, "state.json")) as fh:
            state = json.load(fh)
        lay = state["layout"]
        if not lay["compact"]:
            raise ValueError("capacity_probe: only --compact-samples windows are supported")
        ld = lambda n: np.load(os.path.join(path, n + ".npy"), mmap_mode="r")
        for k in lay["arrays"]:
            if not k.startswith("meta."):
                setattr(self, k, ld(k))
        self.meta = {k[5:]: ld(k) for k in lay["arrays"] if k.startswith("meta.")}
        self.compact, self.compress = True, lay["compress"]
        self.hp_runs, self.soft_q = lay["hp_runs"], lay["soft_q"]
        self.soft_outcome = None
        self.store = None
        self.tok_type, self.ids = ld("store.tok_type"), ld("store.ids")
        self.f = ld("store.f").view(np.float16)
        self.cs, self.ci, self.ca = len(self.ntok), len(self.tok_idx), len(self.a_type)
        self.cr, self.cq = len(self.hpr), len(self.sq)
        for k, v in state["scalars"].items():
            setattr(self, k, v)
        self.extra = state.get("extra", {})
        self.file_bytes = sum(os.path.getsize(os.path.join(path, n)) for n in os.listdir(path))

    def live_positions(self):
        return (self.s_tail + np.arange(self.s_head - self.s_tail)) % self.cs

    def batch(self, j):
        return self._gather(np.asarray(j))


def split_by_run(rv, n_samples, holdout, rng):
    """(train positions, held-out positions): whole runs drawn at random until n_samples, held out by a hash of the
    run counter (holdout share of the runs)."""
    pos = rv.live_positions()
    run = np.asarray(rv.hp_ref[pos])
    order = np.argsort(run, kind="stable")
    run_s, pos_s = run[order], pos[order]
    starts = np.flatnonzero(np.concatenate([[True], run_s[1:] != run_s[:-1]]))
    ends = np.append(starts[1:], len(run_s))
    pick = rng.permutation(len(starts))
    take = np.searchsorted(np.cumsum((ends - starts)[pick]), n_samples) + 1
    pick = pick[:take]
    held = ((run_s[starts[pick]] * 2654435761) % 1000) < int(round(holdout * 1000))
    cat = lambda sel: (np.concatenate([pos_s[starts[i]:ends[i]] for i in sel]) if len(sel)
                       else np.zeros(0, np.int64))
    return cat(pick[~held]), cat(pick[held]), int(take), int(held.sum())


def make_net(spec, dev, soft_policy):
    d, layers = amber_net.SIZES.get(spec) or tuple(int(x) for x in spec.split("x")[:2])
    net = amber_net.AmberNet(d=d, layers=layers, hp_floors=56, soft_policy=soft_policy).to(dev)
    net.sdpa = True
    return net, (d, layers, max(1, d // 32))


def evaluate(net, batches, args, dev):
    """Mean held-out loss parts over the fixed held-out batches (training-mode forward for the soft head; the net has
    no dropout) and the top-1 agreement of the policy head with the search policy on samples with a policy."""
    net.train()
    tot, n_rows, agree, n_pol = {}, 0, 0, 0
    with torch.no_grad():
        for b in batches:
            bt = sp.to_torch(b, dev)
            with amp_ctx(dev):
                _, parts = sp.losses(net, bt, args.w_policy, args.w_outcome, args.w_hp, args.w_hp_floor,
                                     args.w_soft_policy)
                logits = net(bt)[0]
            B = len(b["outcome"])
            for k, v in parts.items():
                tot[k] = tot.get(k, 0.0) + float(v) * B
            n_rows += B
            has = bt["has_policy"].bool()
            if has.any():
                pa = logits.float().masked_fill(~bt["a_mask"], -1e9).argmax(-1)
                ta = bt["policy"].argmax(-1)
                agree += int(((pa == ta) & has).sum())
                n_pol += int(has.sum())
    out = {k: round(v / n_rows, 5) for k, v in tot.items()}
    out["top1"] = round(agree / max(1, n_pol), 5)
    return out


def amp_ctx(dev):
    return torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda")


def train_one(name, net, rv, train_pos, held_batches, args, dev, log):
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps = max(1, args.budget // args.batch)
    rng = np.random.default_rng(args.seed + 1)   # the same batch sequence for every net
    curve = [{"step": 0, "samples": 0, **evaluate(net, held_batches, args, dev)}]
    log(name, curve[-1])
    t0, t_data, skipped = time.time(), 0.0, 0
    for step in range(steps):
        ta = time.time()
        b = rv.batch(train_pos[rng.integers(0, len(train_pos), args.batch)])
        bt = sp.to_torch(b, dev)
        t_data += time.time() - ta
        for g in opt.param_groups:
            g["lr"] = args.lr * min(1.0, (step + 1) / max(1, args.warmup_steps))
        net.train()
        with torch.enable_grad(), amp_ctx(dev):
            loss, _ = sp.losses(net, bt, args.w_policy, args.w_outcome, args.w_hp, args.w_hp_floor,
                                args.w_soft_policy)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        gn = torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        if not (math.isfinite(float(gn)) and math.isfinite(float(loss))):
            opt.zero_grad(set_to_none=True)
            skipped += 1
            continue
        opt.step()
        if (step + 1) % args.eval_every == 0 or step + 1 == steps:
            avail = mem_available_gb()
            if avail < args.min_avail_gb:
                raise SystemExit(f"capacity_probe: MemAvailable {avail:.2f} GB < {args.min_avail_gb} GB, stopping")
            el = time.time() - t0
            curve.append({"step": step + 1, "samples": (step + 1) * args.batch,
                          "samples_per_s": round((step + 1) * args.batch / el, 1),
                          "data_share": round(t_data / el, 3), "mem_avail_gb": round(avail, 2),
                          **evaluate(net, held_batches, args, dev)})
            log(name, curve[-1])
    return curve, skipped, time.time() - t0


def infer_bench(net, batches, dev, reps):
    """ms per batch of the plain inference forward (fp16 on CUDA, eval mode, padded flat layout)."""
    m = net.eval()
    if dev.type == "cuda":
        m = m.half()
    bts = [sp.to_torch(b, dev) for b in batches]
    if dev.type == "cuda":
        for bt in bts:
            bt["f"], bt["a_f"] = bt["f"].half(), bt["a_f"].half()
    with torch.inference_mode():
        for bt in bts[:2]:
            m(bt)
        if dev.type == "cuda":
            torch.cuda.synchronize()
        t = time.time()
        for _ in range(reps):
            for bt in bts:
                m(bt)
        if dev.type == "cuda":
            torch.cuda.synchronize()
    return round((time.time() - t) * 1000 / (reps * len(bts)), 3)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", required=True, help="a window saved by selfplay.py --replay-save (read-only)")
    ap.add_argument("--samples", type=int, default=2_000_000, help="samples drawn (whole runs) from the window")
    ap.add_argument("--holdout", type=float, default=0.05, help="share of the drawn runs held out")
    ap.add_argument("--eval-samples", type=int, default=20_000, help="held-out samples evaluated (fixed set)")
    ap.add_argument("--budget", type=int, default=20_000_000, help="training samples per net (steps x batch)")
    ap.add_argument("--nets", default="0.44M,1.2M", help="amber_net.SIZES keys or DxL, comma-separated")
    ap.add_argument("--init-ckpt", default="", help="reference: the 0.44M net from this checkpoint ('net')")
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--warmup-steps", type=int, default=500)
    ap.add_argument("--w-policy", type=float, default=1.0)
    ap.add_argument("--w-outcome", type=float, default=1.0)
    ap.add_argument("--w-hp", type=float, default=1.0)
    ap.add_argument("--w-hp-floor", type=float, default=1.0)
    ap.add_argument("--w-soft-policy", type=float, default=8.0, help="as the live run (--w-soft-policy 8)")
    ap.add_argument("--eval-every", type=int, default=1000, help="steps between held-out evaluations")
    ap.add_argument("--infer-bench", action="store_true", help="time the inference forward per net (use with cuda)")
    ap.add_argument("--infer-rows", type=int, default=1280, help="rows per inference batch (live run ~1280)")
    ap.add_argument("--min-avail-gb", type=float, default=3.0)
    ap.add_argument("--threads", type=int, default=0, help="torch CPU threads (0 = torch default)")
    ap.add_argument("--device", default="cpu", help="cpu (default, safe next to a live run) or cuda")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="capacity_probe.json")
    ap.add_argument("--save-nets", action="store_true",
                    help="save each trained net as <out stem>.<net>.pt ({'net': state_dict, ...}; --init-net loadable)")
    args = ap.parse_args(argv)
    if args.threads:
        torch.set_num_threads(args.threads)
    dev = torch.device(args.device)

    rv = ReplayView(args.replay)
    live = rv.s_head - rv.s_tail
    rng = np.random.default_rng(args.seed)
    train_pos, held_pos, n_runs, n_held = split_by_run(rv, min(args.samples, live), args.holdout, rng)
    held_eval = held_pos[rng.permutation(len(held_pos))[:args.eval_samples]]
    share = (len(train_pos) + len(held_pos)) / max(1, live)
    est = {"index_arrays_gb": round((rv.hp_ref.nbytes + 4 * live * 8 + 2 * (len(train_pos) + len(held_pos)) * 8)
                                    / 2 ** 30, 2),
           "page_cache_upper_gb": round(rv.file_bytes / 2 ** 30, 2),
           "page_cache_typical_gb": round(rv.file_bytes * min(1.0, share + 0.4) / 2 ** 30, 2),
           "torch_and_batches_gb": 1.5}
    avail = mem_available_gb()
    print(f"# replay {args.replay}: {live} live samples, step {rv.extra.get('step')}, files "
          f"{rv.file_bytes / 2 ** 30:.2f} GB (memory-mapped, read-only)", flush=True)
    print(f"# drawn {n_runs} runs ({n_held} held out): {len(train_pos)} train / {len(held_pos)} held-out samples, "
          f"eval on {len(held_eval)}", flush=True)
    print(f"# memory estimate: anonymous ~{est['index_arrays_gb'] + est['torch_and_batches_gb']:.1f} GB "
          f"(index arrays {est['index_arrays_gb']} + torch/batches ~{est['torch_and_batches_gb']}); page cache "
          f"(reclaimable) typically ~{est['page_cache_typical_gb']} GB, at most {est['page_cache_upper_gb']} GB; "
          f"MemAvailable now {avail:.2f} GB", flush=True)
    if avail < args.min_avail_gb:
        raise SystemExit(f"capacity_probe: MemAvailable {avail:.2f} GB < {args.min_avail_gb} GB, not starting")
    held_batches = [rv.batch(held_eval[i:i + args.batch]) for i in range(0, len(held_eval), args.batch)]

    logf = open(os.path.splitext(args.out)[0] + ".log.jsonl", "w")

    def log(name, row):
        print(json.dumps({"net": name, **row}), flush=True)
        logf.write(json.dumps({"net": name, **row}) + "\n")
        logf.flush()

    soft = args.w_soft_policy > 0
    results = []
    specs = [s for s in args.nets.split(",") if s]
    for spec in specs:
        torch.manual_seed(args.seed)
        net, shape = make_net(spec, dev, soft)
        params = sum(p.numel() for p in net.parameters())
        print(f"# net {spec}: d {shape[0]}, layers {shape[1]}, heads {shape[2]}, {params} parameters", flush=True)
        curve, skipped, wall = train_one(spec, net, rv, train_pos, held_batches, args, dev, log)
        r = {"net": spec, "d": shape[0], "layers": shape[1], "heads": shape[2], "params": params,
             "init": "scratch", "nonfinite_skips": skipped, "wall_s": round(wall, 1), "curve": curve,
             "final": curve[-1]}
        if args.save_nets:
            r["saved"] = os.path.splitext(args.out)[0] + f".{spec}.pt"
            torch.save({"net": net.state_dict(), "probe": {"net": spec, "d": shape[0], "layers": shape[1],
                                                          "final": curve[-1]}}, r["saved"])
        if args.infer_bench:
            inf_rows = held_eval[:args.infer_rows]
            r["infer_ms_per_batch"] = infer_bench(net, [rv.batch(inf_rows)], dev, 20)
        results.append(r)
        del net
    if args.init_ckpt:
        net, shape = make_net("0.44M", dev, soft)
        ck = torch.load(args.init_ckpt, map_location=dev, weights_only=False)   # our own checkpoint
        net.load_state_dict(ck["net"])
        params = sum(p.numel() for p in net.parameters())
        curve, skipped, wall = train_one("0.44M@ckpt", net, rv, train_pos, held_batches, args, dev, log)
        results.append({"net": "0.44M@ckpt", "d": shape[0], "layers": shape[1], "heads": shape[2], "params": params,
                        "init": args.init_ckpt, "note": "held-out samples were trained on by the live run",
                        "nonfinite_skips": skipped, "wall_s": round(wall, 1), "curve": curve, "final": curve[-1]})

    out = {"args": vars(args), "replay_step": rv.extra.get("step"), "live_samples": live,
           "train_samples": len(train_pos), "heldout_samples": len(held_pos), "eval_samples": len(held_eval),
           "runs_drawn": n_runs, "runs_held_out": n_held, "memory_estimate": est, "results": results,
           "torch": torch.__version__, "device": str(dev)}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    keys = ["policy", "soft_policy", "outcome", "outcome_ema", "hp", "hp_floor", "top1"]
    print("\nnet          params    " + " ".join(f"{k:>11}" for k in keys) + "   samples/s   wall_s")
    for r in results:
        f = r["final"]
        print(f"{r['net']:<12} {r['params']:>8} " + " ".join(f"{f.get(k, float('nan')):>11.4f}" for k in keys)
              + f"   {f.get('samples_per_s', 0):>9}   {r['wall_s']:>6}")
    print(f"# wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
