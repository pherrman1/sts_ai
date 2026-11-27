#!/usr/bin/env python3
"""Root search budget and two-seed agreement on captured out-of-combat roots (2026-11-27, diagnostic).

Captures out-of-combat search roots as root_target_probe.py does (frozen net, capture runs from --seed-base on,
nothing trained), then searches every root noise-free with amber_probe.LIVE_SEARCH (q_rescale, c_scale 0.1,
8 candidates) at each budget of --budgets with each search seed of --search-seeds. Noise-free, the search seed
only moves the chance draws inside the tree (and which worker takes which root).

Per root and search the target is Gumbel's improved policy pi' (the probe result's "policy", the policy target of
a full move). Reports, per budget: the two-seed agreement of argmax pi', split by the root Q range (max - min of
the visited root edges' mean backed-up Q, from the first seed's search at that budget) with the mean max pi';
and top1 agreement / KL(pi'_ref || pi'_b) of every budget against the largest one (all seed pairs; the ref-vs-ref
row across seeds is the noise floor). Out-of-combat only (probe roots in combat are not searched).

  tools/seed_guard.sh python3 tools/az_bench/root_budget_probe.py --module-dir build/linux-gcc-release \
      --ckpt ckpt.pt --seed-base 160260000 --states 500 --out root_budget.json
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import amber_probe as ap  # noqa: E402
import explain as ex  # noqa: E402
import root_target_probe as rtp  # noqa: E402

Q_BUCKETS = (("<0.005", 0.0, 0.005), ("0.005-0.02", 0.005, 0.02), (">0.02", 0.02, math.inf))


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def kl(p, q, eps=1e-9):
    p = np.asarray(p, np.float64) + eps
    q = np.asarray(q, np.float64) + eps
    p /= p.sum()
    q /= q.sum()
    return float((p * np.log(p / q)).sum())


def root_summary(r):
    """The per-search numbers the report needs from one probe result."""
    pol = np.asarray(r["policy"], np.float64)
    n = np.asarray(r["n"], np.int64)
    q = np.asarray(r["q"], np.float64)
    vq = q[n > 0]
    return {"argmax": int(pol.argmax()), "max_pi": float(pol.max()), "pick": int(r["pick"]),
            "q_range": float(vq.max() - vq.min()) if vq.size > 1 else 0.0, "visited": int((n > 0).sum()),
            "root_n": int(r["root_n"]), "policy": [round(float(x), 6) for x in pol]}


def agreement(a, b, idx):
    k = sum(a[i]["argmax"] == b[i]["argmax"] for i in idx)
    return {"n": len(idx), "agree": round(k / len(idx), 4) if idx else None, "ci95": wilson(k, len(idx)),
            "mean_max_pi": round(float(np.mean([a[i]["max_pi"] for i in idx])), 4) if idx else None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--module-dir", required=True)
    p.add_argument("--ckpt", required=True)
    p.add_argument("--seed-base", type=int, required=True)
    p.add_argument("--runs", type=int, default=40, help="at most this many capture runs")
    p.add_argument("--states", type=int, default=500)
    p.add_argument("--capture-sims", type=int, default=32, help="full_sims of the capture runs (fast_sims / 4)")
    p.add_argument("--budgets", default="64,256,1024")
    p.add_argument("--search-seeds", default="0,1")
    p.add_argument("--candidates", type=int, default=8)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--timeout", type=float, default=6 * 3600.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    budgets = [int(x) for x in args.budgets.split(",")]
    seeds = [int(x) for x in args.search_seeds.split(",")]
    torch.set_num_threads(args.threads)
    native = ap.native_module(args.module_dir)
    net, net_flags = rtp.load_net(args.ckpt)
    print(f"# net flags from the checkpoint: {net_flags}", flush=True)
    base = dict(ap.LIVE_SEARCH, **net_flags)
    cap_cfg = dict(base, full_sims=args.capture_sims, fast_sims=max(4, args.capture_sims // 4))
    caps, cap_s = rtp.capture(native, net, args.seed_base, args.runs, args.states, args.workers, 4, cap_cfg,
                              args.timeout)
    print(f"# {len(caps)} states captured in {cap_s:.0f} s from seeds {args.seed_base}..", flush=True)
    states = [c["state"] for c in caps]
    res, timing, meta = {}, {}, None
    for b in budgets:
        for s in seeds:
            t0 = time.time()
            out = ap.probe_states(native, net, states, workers=args.workers, games=4, search_seed=s,
                                  timeout_s=args.timeout, full_sims=b, full_candidates=args.candidates, **net_flags)
            timing[f"{b}/{s}"] = round(time.time() - t0, 1)
            if meta is None:
                meta = [{"seed": int(c["seed"]), "move": int(c["move"]), "floor": int(r["floor"]),
                         "k": len(r["bits"]) if r["status"] == "searched" else 0, "status": r["status"],
                         "decision": ex.decision_kind(ap.row_of(r["sample"])) if r["status"] == "searched" else ""}
                        for c, r in zip(caps, out)]
            res[(b, s)] = [root_summary(r) if r["status"] == "searched" else None for r in out]
            print(f"# {b} sims, search seed {s}: {timing[f'{b}/{s}']:.0f} s", flush=True)
    idx = [i for i in range(len(states)) if all(res[(b, s)][i] is not None for b in budgets for s in seeds)]
    rep = {"ckpt": args.ckpt, "seed_base": args.seed_base, "states": len(states), "searched": len(idx),
           "budgets": budgets, "search_seeds": seeds, "candidates": args.candidates, "capture_s": round(cap_s),
           "probe_s": timing, "two_seed": {}, "vs_ref": {}}
    s0, s1 = seeds[0], seeds[1]
    for b in budgets:
        a, c = res[(b, s0)], res[(b, s1)]
        row = {"all": agreement(a, c, idx)}
        for name, lo, hi in Q_BUCKETS:
            row["q " + name] = agreement(a, c, [i for i in idx if lo <= a[i]["q_range"] < hi])
        row["all"]["share_max_pi_gt_0.95"] = round(float(np.mean([a[i]["max_pi"] > 0.95 for i in idx])), 4)
        row["disagree_mean_max_pi"] = round(float(np.mean([a[i]["max_pi"] for i in idx
                                                           if a[i]["argmax"] != c[i]["argmax"]] or [float("nan")])), 4)
        row["pick_agree"] = round(float(np.mean([a[i]["pick"] == c[i]["pick"] for i in idx])), 4)
        rep["two_seed"][str(b)] = row
    ref = budgets[-1]
    for b in budgets:
        pairs = [(sb, sr) for sb in seeds for sr in seeds if not (b == ref and sb >= sr)]
        top1, kls = [], []
        for sb, sr in pairs:
            x, y = res[(b, sb)], res[(ref, sr)]
            top1 += [x[i]["argmax"] == y[i]["argmax"] for i in idx]
            kls += [kl(y[i]["policy"], x[i]["policy"]) for i in idx]
        kls = np.array(kls)
        rep["vs_ref"][str(b)] = {"pairs": len(pairs), "top1": round(float(np.mean(top1)), 4),
                                 "top1_ci95": wilson(int(np.sum(top1)), len(top1)),
                                 "kl_ref_b_mean": round(float(kls.mean()), 4),
                                 "kl_ref_b_median": round(float(np.median(kls)), 4),
                                 "kl_ref_b_p90": round(float(np.quantile(kls, 0.9)), 4)}
    print(json.dumps(rep, indent=1))
    rows = [dict(meta[i], **{f"{b}/{s}": res[(b, s)][i] for b in budgets for s in seeds}) for i in range(len(states))]
    json.dump({"report": rep, "rows": rows}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
