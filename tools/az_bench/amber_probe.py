#!/usr/bin/env python3
"""Search from given states with a frozen Amber net on the CPU (decision explainability, 2026-11-21).

RunDriver probe roots (az_run_driver.h RunConfig::probeRoots): each state's decision is searched once with the live
stage-1 run's search rules and full budget, noise-free (the top logits are Gumbel's candidates, the pick is the best
logit + sigma(completed Q), as Amber's noise-free moves); nothing is played. Per root action the result has the
net's logit and prior, the visits, the mean backed-up value Q, the completed Q, Gumbel's improved policy and the
search-backed P(win) / expected HP at the end of the floor (mean over the action's simulations of their leaves'
outcome / HP distributions).

  python3 tools/az_bench/amber_probe.py --module-dir build/linux-gcc-release --ckpt ckpt.pt --seeds 160000000:4
      searches the Neow decision of 4 fresh A20 runs (seed guard: seeds are not played, only their start state)
  python3 tools/az_bench/amber_probe.py --module-dir build/linux-gcc-release --live --ckpt ckpt.pt \
      --observation tests/fixtures/live_act1_boss_card_reward.json
      a live out-of-combat observation (az_bench_live: GameState.from_live) with each action's live action

Library use: probe_states(native, net, states, **flags) -> list of result dicts (RunDriver.take_probe_results).
"""

import argparse
import importlib
import json
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import explain as ex  # noqa: E402

OUTCOME_CLASSES, HP_CLASSES, FLOORS = 57, 256, 56
MAX_TOKENS, MAX_ACTIONS, CAT, FLOAT, ACT_FEAT = 212, 96, 4, 64, 8

# The live stage-1 run's search (wd_current.env 2026-11-21 15:21 CET) without its training-only parts (savescum,
# pick-rate exploration, sample keeping). search_ema_lambda / search_ema_hp only switch on the per-node
# distributions the probe's P(win) / HP read; they change training targets, not the selection.
LIVE_SEARCH = dict(full_sims=64, fast_sims=16, full_candidates=8, fast_candidates=4, c_visit=50.0, c_scale=0.1,
                   q_rescale=True, fast_noise=False, utility=3, merge_cards=True, chance_on_reveal=True,
                   cross_combat=True, sim_help=True, eval_cache=True, force_keys=True, force_rewards=True,
                   force_potions=True, rng_fix=True, ooc_canon=True, parallel_nodes=4, search_ema_lambda=0.5,
                   search_ema_hp=True)

ROW_BUCKETS = [1, 2, 4, 8, 16, 32, 64]
TOK_BUCKETS = [32, 40, 48, 56, 64, 80, 96, 128, MAX_TOKENS]
ACT_BUCKETS = [16, 32, 64, MAX_ACTIONS]


def native_module(module_dir, live=False):
    """az_bench_native, or az_bench_live (the same module with the live importer), from module_dir."""
    if module_dir and module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    return importlib.import_module("az_bench_live" if live else "az_bench_native")


def _buffers(R):
    T, A = TOK_BUCKETS[-1], ACT_BUCKETS[-1]
    return {"tok_type": np.zeros(R * T, np.int8), "ids": np.zeros(R * T * CAT, np.int16),
            "f": np.zeros(R * T * FLOAT, np.float16), "mask": np.zeros(R * T, np.uint8),
            "a_type": np.zeros(R * A, np.int16), "a_src": np.zeros(R * A, np.int16),
            "a_tgt": np.zeros(R * A, np.int16), "a_f": np.zeros(R * A * ACT_FEAT, np.float16),
            "a_mask": np.zeros(R * A, np.uint8)}


@torch.no_grad()
def evaluate_flat(net, bufs, Rp, Tp, Ap):
    """The net on a packed batch (next_flat's layout): logits [B, A], F, E[HP], per-floor HP, both softmaxes."""
    x = {"tok_type": torch.from_numpy(bufs["tok_type"][:Rp * Tp].astype(np.int64)).view(Rp, Tp),
         "ids": torch.from_numpy(bufs["ids"][:Rp * Tp * CAT].astype(np.int64)).view(Rp, Tp, CAT),
         "f": torch.from_numpy(bufs["f"][:Rp * Tp * FLOAT].astype(np.float32)).view(Rp, Tp, FLOAT),
         "mask": torch.from_numpy(bufs["mask"][:Rp * Tp].astype(bool)).view(Rp, Tp),
         "a_type": torch.from_numpy(bufs["a_type"][:Rp * Ap].astype(np.int64)).view(Rp, Ap),
         "a_src": torch.from_numpy(bufs["a_src"][:Rp * Ap].astype(np.int64)).view(Rp, Ap),
         "a_tgt": torch.from_numpy(bufs["a_tgt"][:Rp * Ap].astype(np.int64)).view(Rp, Ap),
         "a_f": torch.from_numpy(bufs["a_f"][:Rp * Ap * ACT_FEAT].astype(np.float32)).view(Rp, Ap, ACT_FEAT),
         "a_mask": torch.from_numpy(bufs["a_mask"][:Rp * Ap].astype(bool)).view(Rp, Ap)}
    lg, outcome, hp, hpf = net.forward_flat(x)[:4]
    p = torch.softmax(outcome.float(), -1)
    floors = torch.arange(OUTCOME_CLASSES, dtype=torch.float32)
    floors[0] = 57.0
    F = (p * floors).sum(-1) / 57.0
    ph = torch.softmax(hp.float(), -1)
    ehp = (ph * torch.arange(HP_CLASSES, dtype=torch.float32)).sum(-1)
    return lg.float(), F, ehp, hpf.float().clamp(0, 1), p, ph


def serve(drv, net, total, timeout_s=600.0, max_rows=64):
    """Answers the driver's requests with the net until `total` probe roots are done; returns their results."""
    bufs = _buffers(max(max_rows, ROW_BUCKETS[-1]))
    results, t0 = [], time.time()
    while drv.probes_done() < total:
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"probe search: {drv.probes_done()} of {total} roots after {timeout_s:.0f} s")
        got = drv.next_flat(max_rows, 1, 20, ROW_BUCKETS, TOK_BUCKETS, ACT_BUCKETS, bufs)
        if got is None:
            results += drv.take_probe_results()
            continue
        tickets, rows, Rp, Tp, Ap = got
        lg, F, ehp, hpf, p, ph = evaluate_flat(net, bufs, Rp, Tp, Ap)
        drv.submit(tickets, lg[:rows].contiguous().numpy(), F[:rows].numpy(), ehp[:rows].numpy(),
                   hpf[:rows].contiguous().numpy(), 0, p[:rows].contiguous().numpy(), ph[:rows].contiguous().numpy())
    results += drv.take_probe_results()
    return sorted(results, key=lambda r: r["probe"])


def probe_states(native, net, states, workers=1, games=4, search_seed=0, noise=False, timeout_s=600.0, **flags):
    """Searches each state's decision once (LIVE_SEARCH, overridden by flags); results in the states' order."""
    cfg = dict(LIVE_SEARCH)
    cfg.update(flags)
    drv = native.RunDriver(workers=workers, games=games, probe_roots=list(states), probe_noise=noise,
                           search_seed=search_seed, keep_full=0.0, keep_fast=0.0, ascension=20, **cfg)
    drv.start()
    try:
        return serve(drv, net, len(states), timeout_s)
    finally:
        drv.stop()


def row_of(sample):
    """A probe result's root sample as an explain.Row (the replay window's layout)."""
    return ex.Row(sample["tok_type"].astype(np.int64), sample["ids"].astype(np.int64), sample["f"].astype(np.float16),
                  sample["a_type"].astype(np.int64), sample["a_src"].astype(np.int64),
                  sample["a_tgt"].astype(np.int64), sample["a_f"].astype(np.float16))


def describe(result, vocab, state=None):
    """Per action, sorted by the search's root score: label, prior, logit, visits, Q, P(win), E[HP], live action."""
    if result["status"] != "searched":
        return {"status": result["status"], "floor": result["floor"], "pick_bits": int(result["pick_bits"])}
    r = row_of(result["sample"])
    lg = np.asarray(result["logit"], np.float64)
    prior = np.exp(lg - lg.max())
    prior /= prior.sum()
    out = []
    for i in range(len(result["bits"])):
        live = None
        if state is not None and getattr(state, "is_live", False):
            try:
                live = json.loads(state.lower_action(int(result["bits"][i])))
            except ValueError as e:
                live = {"unsupported": str(e)}
        out.append({"action": i, "label": ex.action_label(r, i, vocab) if i < len(r.a_type) else f"action {i}",
                    "bits": int(result["bits"][i]), "prior": float(prior[i]), "logit": float(lg[i]),
                    "visits": int(result["n"][i]), "q": float(result["q"][i]),
                    "q_completed": float(result["q_completed"][i]), "policy": float(result["policy"][i]),
                    "score": float(result["score"][i]), "pwin": float(result["pwin"][i]),
                    "ehp": float(result["ehp"][i]), "candidate": bool(result["candidate"][i]),
                    "picked": i == result["pick"], "live_action": live})
    out.sort(key=lambda d: (not d["picked"], -d["score"]))
    return {"status": "searched", "floor": result["floor"], "act": result["act"], "hp": result["hp"],
            "max_hp": result["max_hp"], "decision": ex.decision_kind(r), "root_pwin": float(result["root_dist"][0]),
            "root_ehp": float(result["root_ehp"]), "search_pwin": float(result["search_pwin"]),
            "search_ehp": float(result["search_ehp"]), "root_n": int(result["root_n"]),
            "sigma": float(result["sigma"]), "actions": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--live", action="store_true", help="az_bench_live (GameState.from_live)")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--seeds", default="", help="first:count fresh runs' start states (the Neow decision)")
    ap.add_argument("--ascension", type=int, default=20)
    ap.add_argument("--observation", action="append", default=[], help="live OOC observation JSON file (--live)")
    ap.add_argument("--sims", type=int, default=64)
    ap.add_argument("--noise", action="store_true", help="Gumbel noise as in self-play's full moves")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    native = native_module(args.module_dir, args.live)
    states = []
    if args.seeds:
        first, count = (int(v) for v in args.seeds.split(":"))
        states += [native.GameState.new_run(first + i, args.ascension, True) for i in range(count)]
    for path in args.observation:
        states.append(native.GameState.from_live(open(path).read()))
    if not states:
        raise SystemExit("no states: --seeds or --observation")
    net = ex.load_net(args.ckpt)
    vocab = ex.Vocab()
    t0 = time.time()
    res = probe_states(native, net, states, full_sims=args.sims, noise=args.noise)
    took = time.time() - t0
    rep = [describe(r, vocab, s) for r, s in zip(res, states)]
    for d in rep:
        if d["status"] != "searched":
            print(f"floor {d['floor']}: {d['status']}")
            continue
        print(f"floor {d['floor']} {d['decision']}: net P(win) {d['root_pwin']:.3f}, search {d['search_pwin']:.3f}, "
              f"E[HP] {d['search_ehp']:.1f} of {d['max_hp']}, {d['root_n']} visits")
        for a in d["actions"]:
            print(f"  {'*' if a['picked'] else ' '} {a['label'][:34]:34s} prior {a['prior']:.3f} N {a['visits']:3d} "
                  f"Q {a['q']:.3f} P(win) {a['pwin']:.3f} HP {a['ehp']:5.1f} pi {a['policy']:.3f}"
                  + (f"  -> {json.dumps(a['live_action'])[:60]}" if a["live_action"] is not None else ""))
    print(f"# {len(states)} states in {took:.1f} s")
    if args.out:
        json.dump(rep, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
