#!/usr/bin/env python3
"""How far RunConfig::rootTarget moves a searched move's search result D_m (2026-11-25, diagnostic).

Captures out-of-combat search roots of a few normal runs with a frozen net (capture_rate, seeds from --seed-base on;
nothing is trained), searches each once as amber_probe does (probe roots: full budget, noise-free) and reads the
search result three ways from the same search: tree (the mean over the root evaluation and every simulation's leaf,
the current target), policy (Gumbel's improved policy x each root edge's mean leaf) and pick (the played edge's
mean leaf); az_run_driver.h RunConfig::rootTarget. Reports P(win), E[HP at the end of the floor] and the total
variation distance of the 57-class outcome distribution against tree, overall and by legal-action count / decision.
Probe roots are out-of-combat only: combat moves are not covered.

  python3 tools/az_bench/root_target_probe.py --module-dir build/linux-gcc-release --ckpt ckpt.pt \
      --seed-base 160260000 --states 500 --out root_target.json
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import amber_net as am  # noqa: E402
import amber_probe as ap  # noqa: E402
import explain as ex  # noqa: E402

AUX_SLOTS = 5   # selfplay.AUX_SLOTS (az_run_driver.h kAuxSlots)


def load_net(path):
    """The inference net of a selfplay.py checkpoint, built from its saved args as selfplay.main builds it, and the
    driver flags its input needs (--consequences, --enemy-tokens). Checkpoints without args: explain.load_net."""
    ck = torch.load(path, map_location="cpu", weights_only=False)
    a = ck.get("args")
    if not a:
        return ex.load_net(path), {}
    a = a if isinstance(a, dict) else vars(a)
    d, layers = am.SIZES.get(a.get("net")) or tuple(int(x) for x in a["net"].split("x")[:2])
    kw = dict(d=d, layers=layers, hp_floors=56, soft_policy=(a.get("w_soft_policy") or 0) > 0,
              aux_slots=AUX_SLOTS if a.get("aux_fights") else 0, enemy_bias=bool(a.get("enemy_map_bias")),
              enemy_gate=bool(a.get("enemy_tokens")))
    if a.get("intent_emb") is not None:
        kw["intent_emb"] = bool(a["intent_emb"])
    if a.get("select_many_bits") is not None:
        kw["mask_bits"] = bool(a["select_many_bits"])
    net = am.AmberNet(**kw)
    net.gate_key = bool(a.get("enemy_gate_key"))
    net.load_state_dict(ck["net"])
    am.input_options_from_ckpt(net, ck)   # --run-log-loopcount, --map-tokens
    net.sdpa = True
    flags = {k: True for k in ("consequences", "enemy_tokens") if a.get(k)}
    return net.eval(), flags


def capture(native, net, seed_base, runs, states, workers, games, cfg, timeout_s):
    """Out-of-combat search roots of up to `runs` runs (seeds seed_base ..), until `states` are captured."""
    drv = native.RunDriver(workers=workers, games=games, seed_base=seed_base, max_runs=runs, ascension=20,
                           keep_full=0.0, keep_fast=0.0, capture_rate=1.0, **cfg)
    bufs = ap._buffers(64)
    caps, t0 = [], time.time()
    drv.start()
    try:
        while len(caps) < states and drv.stats()["runs_done"] < runs:
            if time.time() - t0 > timeout_s:
                break
            got = drv.next_flat(64, 1, 20, ap.ROW_BUCKETS, ap.TOK_BUCKETS, ap.ACT_BUCKETS, bufs)
            if got is None:
                caps += drv.take_captures()
                continue
            tickets, rows, Rp, Tp, Ap = got
            lg, F, ehp, hpf, p, ph = ap.evaluate_flat(net, bufs, Rp, Tp, Ap)
            drv.submit(tickets, lg[:rows].contiguous().numpy(), F[:rows].numpy(), ehp[:rows].numpy(),
                       hpf[:rows].contiguous().numpy(), 0, p[:rows].contiguous().numpy(), ph[:rows].contiguous().numpy())
            caps += drv.take_captures()
    finally:
        drv.stop()
    caps += drv.take_captures()
    return caps[:states], time.time() - t0


def tv(a, b):
    return 0.5 * float(np.abs(np.asarray(a, np.float64) - np.asarray(b, np.float64)).sum())


def summarize(rows):
    """Means over rows of P(win) / E[HP] per reading and the gaps to tree."""
    if not rows:
        return {"n": 0}
    out = {"n": len(rows)}
    for key in ("pwin", "ehp"):
        t = np.array([r[key]["tree"] for r in rows])
        out[key] = {"net": round(float(np.mean([r[key]["net"] for r in rows])), 4), "tree": round(float(t.mean()), 4)}
        for m in ("policy", "pick"):
            x = np.array([r[key][m] for r in rows])
            d = x - t
            out[key][m] = round(float(x.mean()), 4)
            out[key][m + "_minus_tree"] = round(float(d.mean()), 4)
            out[key][m + "_abs_gap"] = round(float(np.abs(d).mean()), 4)
            out[key][m + "_abs_gap_p90"] = round(float(np.quantile(np.abs(d), 0.9)), 4)
    for m in ("policy", "pick"):
        out["tv_" + m] = round(float(np.mean([r["tv"][m] for r in rows])), 4)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--module-dir", required=True)
    p.add_argument("--ckpt", required=True)
    p.add_argument("--seed-base", type=int, required=True)
    p.add_argument("--runs", type=int, default=40, help="at most this many capture runs")
    p.add_argument("--states", type=int, default=500)
    p.add_argument("--capture-sims", type=int, default=32, help="full_sims of the capture runs (fast_sims / 4)")
    p.add_argument("--sims", type=int, default=64, help="probe search budget (the live run's full moves)")
    p.add_argument("--candidates", type=int, default=8)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--timeout", type=float, default=5400.0)
    p.add_argument("--out", default="")
    args = p.parse_args()
    torch.set_num_threads(args.threads)
    native = ap.native_module(args.module_dir)
    net, net_flags = load_net(args.ckpt)
    print(f"# net flags from the checkpoint: {net_flags}", flush=True)
    base = dict(ap.LIVE_SEARCH, **net_flags)
    cap_cfg = dict(base, full_sims=args.capture_sims, fast_sims=max(4, args.capture_sims // 4))
    caps, cap_s = capture(native, net, args.seed_base, args.runs, args.states, args.workers, 4, cap_cfg, args.timeout)
    print(f"# {len(caps)} states captured in {cap_s:.0f} s from seeds {args.seed_base}..", flush=True)
    t0 = time.time()
    res = ap.probe_states(native, net, [c["state"] for c in caps], workers=args.workers, games=4,
                          timeout_s=args.timeout, full_sims=args.sims, full_candidates=args.candidates, **net_flags)
    probe_s = time.time() - t0
    rows = []
    for r, c in zip(res, caps):
        if r["status"] != "searched":
            continue
        k = len(r["bits"])
        rows.append({"floor": int(r["floor"]), "k": k, "decision": ex.decision_kind(ap.row_of(r["sample"])),
                     "pwin": {"net": float(r["root_dist"][0]), "tree": float(r["search_pwin"]),
                              "policy": float(r["search_pwin_policy"]), "pick": float(r["search_pwin_pick"])},
                     "ehp": {"net": float(r["root_ehp"]), "tree": float(r["search_ehp"]),
                             "policy": float(r["search_ehp_policy"]), "pick": float(r["search_ehp_pick"])},
                     "tv": {"policy": tv(r["search_dist_policy"], r["search_dist"]),
                            "pick": tv(r["search_dist_pick"], r["search_dist"])}})
    buckets = {"k=2": lambda k: k == 2, "k=3-4": lambda k: 3 <= k <= 4, "k=5-8": lambda k: 5 <= k <= 8,
               "k>=9": lambda k: k >= 9}
    rep = {"ckpt": args.ckpt, "seed_base": args.seed_base, "states": len(caps), "searched": len(rows),
           "sims": args.sims, "candidates": args.candidates, "capture_s": round(cap_s), "probe_s": round(probe_s),
           "all": summarize(rows),
           "by_k": {b: summarize([r for r in rows if f(r["k"])]) for b, f in buckets.items()},
           "by_decision": {d: summarize([r for r in rows if r["decision"] == d])
                           for d in sorted({r["decision"] for r in rows})}}
    print(json.dumps(rep, indent=1))
    if args.out:
        json.dump({"report": rep, "rows": rows}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
