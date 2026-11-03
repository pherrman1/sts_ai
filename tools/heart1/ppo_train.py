"""PPO + GAE learner for the heart1-size decision net on STS_OOC_HEART1_PPO trajectories (S0, PR 2).

One iteration: read the trajectory lines one_combat wrote (schema heart1-ppo-traj-v1), compute rewards and GAE
advantages with the current critic, run PPO epochs, save a resumable checkpoint and export the native .bin for the
next actors. The net is tools/heart1/ppo_model.PolicyNet (native forward mirror, every optional input).

    python3 tools/heart1/ppo_train.py update --state run/state.pt --init heart1.bin \
        --traj run/iter_0003/traj.jsonl --out-bin run/net_0004.bin [--value-only] [hyperparameters]

The first call with a fresh --state starts from --init (heart1.bin or a d256 student; extended zero-init); the
KL anchor (--kl-coef > 0) is that start net, kept frozen. Later calls resume optimiser, iteration and anchor.

Rewards (--reward):
  heart       1{Heart kill} at game end.
  original    floor/190 + 0.05 per key + 0.6 Heart (heart1's late reward without its deck-quality shaping).
  heart_pbrs  1{Heart} + potential-based shaping gamma*phi(s') - phi(s) with phi from each decision line's "phi"
              (a missing phi counts as 0, so the shaping still telescopes; phi at the terminal state is 0).
              No actor writes "phi" yet (one_combat's ppoStep exports no leaf value), so an update refuses
              heart_pbrs unless at least one decision line carries it: otherwise it would silently equal heart.
  heart_phi   as heart_pbrs, with phi computed in Python by --phi-model (ppo_phi.py) from each net decision's
              record while loading; every net decision must have one.
  heart_act   1{Heart} + --act-bonus per act cleared (final floor >= 17, 34, 51) + --key-bonus per key, at game
              end (changes the objective; screens still judge arms by Heart kills).
Decisions with one choice (source heart1_ppo_single) train the critic only; fallback lines (chain) are skipped.

Architecture arms (PREREG ppo_arch_screen_20261102; all off by default, and off means the code paths of before):
  --extra-blocks N    N identity-initialised blocks appended (ppo_model.construct); exported, so actors run them.
  --critic separate   the value comes from a copied trunk (critic_net); the policy trunk gets no value gradient.
  --aux-heads floor,act4 [--aux-weight 0.1]   zero-init heads on the pooled trunk: final floor/57 (MSE), Act 4
                      reached (BCE), from the game line; added to the full loss only (not to a value warm-up).
  --value-sparse K    value loss on each act's first decision plus K seeded random decisions per game.
  --inputs x3_deck    zero-init deck aggregates (ppo_model.deck_aggregates) on the fixed-observation token;
                      exported, so actors need a one_combat that reads x3_deck (heart1_policy.cpp deckAggregates).
--extra-blocks, --critic, --aux-heads and --inputs are structure: a fresh --init applies them to the start net; a resumed --state must already have
them (fork_learner / `ppo_cloud.py init --fork-dir` adds them to a running arm's checkpoint).

`bench` times one update on synthetic copies of real trajectory games (no learning signal needed):
    python3 tools/heart1/ppo_train.py bench --init heart1.bin --traj smoke.jsonl --games 512 1024 2048 --device cuda
Records are featurised once while loading (load_games); "load_featurize_s" and "feature_gb" extrapolate that cost
and the packed host memory to N games and are not part of "total_s" (critic pass "prep_s" + training "train_s").
"""
import argparse
import functools
import gzip
import json
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_phi  # noqa: E402
from ppo_model import (AUX_TARGETS, OPTIONAL_FIXEDVECS, FeatureStore, PolicyNet, batch_to, collate,  # noqa: E402
                       construct, featurize)

SCHEMA = "heart1-ppo-traj-v1"
NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")


# ---------------------------------------------------------------- trajectories

def _parse_line(line, trim_map=None, phi_model=None):
    """One trajectory line -> row; with trim_map, a net decision's record is featurised (worker-safe).

    Errors come back as {"type": "_error"} rows instead of raising in the worker, so the pool always drains and
    closes normally (terminating a pool mid-stream can deadlock); load_games raises them afterwards."""
    if not line.strip():
        return None
    try:
        row = json.loads(line)
        if phi_model is not None and row["type"] == "decision" and row["source"] in NET_SOURCES:
            row["phi_py"] = ppo_phi.value(phi_model, row, row["record"])
        if trim_map is not None and row["type"] == "decision":
            rec = row.pop("record", None)
            row.pop("logits", None)
            if row["source"] in NET_SOURCES:
                row["feat"] = featurize(rec, trim_map)
        return row
    except Exception as e:   # noqa: BLE001 - re-raised by the parent with the line number
        return {"type": "_error", "error": f"{type(e).__name__}: {e}"}


def seed_key(seed):
    """Sort key of a game seed (decimal strings in seed order; anything else after them, as text)."""
    s = str(seed)
    return (0, int(s)) if s.isdigit() else (1, s)


def load_games(paths, trim_map=None, workers=None, phi_model=None):
    """Games with all their net decisions, in decision order. A game without its "game" line is dropped.

    The games come back sorted by seed (steps by idx), whatever order the files list them in: `one_combat bestbench`
    writes each game when its thread finishes, so the file order depends on thread timing, and the learner's
    per-update shuffle permutes positions, not games. A seed may appear in one file only (the same games in two
    parts would be double-counted).

    With trim_map (the learner net's flag), each net decision's record is featurised while loading and only the
    packed features are kept ("feat"; record and logits are dropped), so host memory stays at a few KB per decision.
    With phi_model (ppo_phi.load), each net decision gets "phi_py" (its potential) before the record is dropped.
    Parsing and featurising run in `workers` processes (default min(8, CPUs); 1 = in-process); the result is the
    same either way."""
    if workers is None:
        workers = min(8, os.cpu_count() or 1)
    pool = None
    if workers > 1 and trim_map is not None:
        import multiprocessing as mp
        pool = mp.get_context("fork" if hasattr(os, "fork") else "spawn").Pool(workers)
    parse = functools.partial(_parse_line, trim_map=trim_map, phi_model=phi_model)
    # Parse every file completely before validating: raising while imap still streams a file and then terminating
    # the pool can deadlock (the task feeder holds the queue lock on a full pipe).
    parsed = []
    ok = False
    try:
        for path in paths:
            with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
                parsed.append((path, list(pool.imap(parse, f, chunksize=64) if pool else map(parse, f))))
        ok = True
    finally:
        if pool:
            if ok:
                pool.close()
            else:
                pool.terminate()
            pool.join()
    pending, games, seen = {}, [], {}   # seen: seed -> path of its game line
    for path, rows in parsed:
        for lineno, row in enumerate(rows, 1):
            if row is None:
                continue
            if row["type"] == "_error":
                raise ValueError(f"{path}:{lineno}: {row['error']}")
            key = (path, row["seed"])
            if row["type"] == "decision":
                pending.setdefault(key, []).append(row)
            elif row["type"] == "game":
                if row.get("schema") != SCHEMA:
                    raise ValueError(f"{path}: schema {row.get('schema')} is not {SCHEMA}")
                first = seen.get(row["seed"])
                if first == path:
                    raise ValueError(f"{path}: seed {row['seed']} has two game lines (reused seed?)")
                if first is not None:
                    raise ValueError(f"seed {row['seed']} has a game line in {first} and in {path} "
                                     f"(the same games twice?)")
                seen[row["seed"]] = path
                steps = sorted(pending.pop(key, []), key=lambda r: r["idx"])
                steps = [s for s in steps if s["source"] in NET_SOURCES]
                games.append({"seed": row["seed"], "outcome": row["outcome"], "info": row, "steps": steps})
    games.sort(key=lambda g: seed_key(g["seed"]))
    return games


ACT_FLOORS = (17, 34, 51)   # first floor after each act's boss: a final floor at or above it means the act was cleared


def terminal_reward(outcome, kind, act_bonus=0.1, key_bonus=0.05):
    heart = 1.0 if outcome.get("heart_kill") else 0.0
    if kind in ("heart", "heart_pbrs", "heart_phi"):
        return heart
    if kind == "heart_act":
        acts = sum(1 for f in ACT_FLOORS if outcome.get("floor", 0) >= f)
        return heart + act_bonus * acts + key_bonus * sum(outcome.get("keys", []))
    if kind == "original":
        return outcome.get("floor", 0) / 190.0 + 0.05 * sum(outcome.get("keys", [])) + 0.6 * heart
    raise ValueError(f"unknown reward {kind}")


def step_rewards(game, kind, gamma, act_bonus=0.1, key_bonus=0.05):
    """Per-step rewards: 0 except the last step's terminal reward, plus PBRS terms for heart_pbrs / heart_phi."""
    steps = game["steps"]
    n = len(steps)
    r = [0.0] * n
    if n == 0:
        return r
    if kind == "heart_pbrs":
        # missing phi = 0 keeps the sum telescoping; terminal potential 0 keeps the objective unchanged
        phi = [float(s.get("phi") or 0.0) for s in steps] + [0.0]
        for t in range(n):
            r[t] += gamma * phi[t + 1] - phi[t]
    elif kind == "heart_phi":
        missing = sum(1 for s in steps if "phi_py" not in s)
        if missing:
            raise ValueError(f"seed {game.get('seed')}: {missing} decisions without phi_py (load with --phi-model)")
        phi = [float(s["phi_py"]) for s in steps] + [0.0]
        for t in range(n):
            r[t] += gamma * phi[t + 1] - phi[t]
    r[-1] += terminal_reward(game["outcome"], kind, act_bonus, key_bonus)
    return r


def gae(rewards, values, gamma, lam):
    """Advantages and returns for one episode; the value after the last step is 0 (terminal)."""
    n = len(rewards)
    adv = [0.0] * n
    last = 0.0
    for t in reversed(range(n)):
        nxt = values[t + 1] if t + 1 < n else 0.0
        delta = rewards[t] + gamma * nxt - values[t]
        last = delta + gamma * lam * last
        adv[t] = last
    return adv, [a + v for a, v in zip(adv, values)]


# ---------------------------------------------------------------- learner

def default_args(ns=None):
    ap = argparse.ArgumentParser(add_help=False)
    add_hparams(ap)
    return ap.parse_args([], namespace=ns)


def add_hparams(ap):
    ap.add_argument("--reward", default="heart", choices=["heart", "original", "heart_pbrs", "heart_phi", "heart_act"])
    ap.add_argument("--phi-model", default="", help="heart_phi: ppo_phi model JSON (path relative to the repo root)")
    ap.add_argument("--phi-sha256", default="", help="heart_phi: required sha256 of --phi-model")
    ap.add_argument("--act-bonus", type=float, default=0.1, help="heart_act: reward per act cleared")
    ap.add_argument("--key-bonus", type=float, default=0.05, help="heart_act: reward per key")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--lam", type=float, default=0.97)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--minibatch", type=int, default=192, help="decisions per minibatch")
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--value-lr-mult", type=float, default=1.0, help="value-head learning-rate multiplier")
    ap.add_argument("--value-coef", type=float, default=0.5)
    ap.add_argument("--entropy-coef", type=float, default=0.002)
    ap.add_argument("--kl-coef", type=float, default=0.0, help="KL(pi || start net) penalty")
    ap.add_argument("--kl-decay-iters", type=int, default=0,
                    help="> 0: the KL coefficient falls linearly from --kl-coef at update 0 to 0 at this update")
    ap.add_argument("--max-grad-norm", type=float, default=1.0)
    ap.add_argument("--norm-adv", type=int, default=1, help="normalise advantages per update")
    ap.add_argument("--value-clip", type=float, default=0.0, help="PPO value clipping range (0 = off)")
    ap.add_argument("--amp", type=int, default=1, help="bf16 autocast on CUDA")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--compile", type=int, default=0,
                    help="1 = torch.compile the net (dynamic shapes) to fuse the fp32 RMSNorm and other elementwise "
                         "ops; same math up to rounding; first minibatches pay the compile time (0 = off)")
    ap.add_argument("--micro-batch", type=int, default=0,
                    help="memory only: run each minibatch's forward/backward in chunks of at most this many decisions "
                         "and accumulate the gradient before the one optimizer step (same loss and gradient up to "
                         "rounding; 0 = off, as does any value >= minibatch)")
    # Architecture arms (PREREG ppo_arch_screen_20261102). The first three change the net's structure: a fresh
    # start (--init) applies them to the start net, `ppo_cloud.py init --fork-dir` to a running arm's state
    # (fork_learner); a resumed state must already have the same structure.
    ap.add_argument("--extra-blocks", type=int, default=0, help="identity-initialised transformer blocks appended")
    ap.add_argument("--inputs", default="", help="comma list of optional zero-init inputs (x3_deck)")
    ap.add_argument("--critic", default="shared", choices=["shared", "separate"],
                    help="separate: the value comes from a copied trunk; the policy trunk gets no value gradient")
    ap.add_argument("--aux-heads", default="", help="comma list of auxiliary targets (floor, act4), zero-init heads")
    ap.add_argument("--aux-weight", type=float, default=0.1, help="loss weight of each auxiliary head")
    ap.add_argument("--value-sparse", type=int, default=0,
                    help="value loss only on each act's first decision plus N random decisions per game (0 = all)")
    ap.add_argument("--bucket", type=int, default=0,
                    help="length-bucketed minibatches: sort each window of BUCKET*minibatch shuffled decisions by "
                         "token count before cutting minibatches (less padding; changes minibatch composition; 0 = off)")


REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def phi_model_for(args):
    """The potential model of --reward heart_phi (None for every other reward); checks --phi-sha256."""
    if args.reward != "heart_phi":
        return None
    if not args.phi_model or not args.phi_sha256:
        sys.exit("--reward heart_phi needs --phi-model and --phi-sha256")
    path = args.phi_model if os.path.isabs(args.phi_model) else os.path.join(REPO, args.phi_model)
    return ppo_phi.load(path, args.phi_sha256)


def plan_minibatches(a, feats, iteration):
    """The update's minibatches as lists of decision indices into `feats` (epochs x shuffled cuts).

    Depends only on the hyperparameters, the decision count (and, with --bucket, each decision's token count)
    and the iteration: with load_games' seed order the same games give the same minibatches."""
    idx = list(range(len(feats)))
    rng = random.Random(a.seed * 1000003 + iteration)
    minibatches = []
    for _ in range(a.epochs):
        rng.shuffle(idx)
        order = idx
        if a.bucket > 0:
            w = a.bucket * a.minibatch
            order = [j for i in range(0, len(idx), w)
                     for j in sorted(idx[i:i + w], key=lambda j: feats[j]["n"])]
            cut = [order[i:i + a.minibatch] for i in range(0, len(order), a.minibatch)]
            rng.shuffle(cut)
            minibatches.extend(cut)
        else:
            minibatches.extend(order[i:i + a.minibatch] for i in range(0, len(order), a.minibatch))
    return minibatches


def aux_names(args):
    names = tuple(x for x in args.aux_heads.split(",") if x) if getattr(args, "aux_heads", "") else ()
    bad = [x for x in names if x not in AUX_TARGETS]
    if bad:
        sys.exit(f"--aux-heads {bad}: choose from {AUX_TARGETS}")
    return names


def input_names(args):
    names = tuple(x for x in getattr(args, "inputs", "").split(",") if x)
    bad = [x for x in names if x not in OPTIONAL_FIXEDVECS]
    if bad:
        sys.exit(f"--inputs {bad}: choose from {tuple(OPTIONAL_FIXEDVECS)}")
    return names


def structure_of(args):
    """The net structure the arch flags ask for (compared with a resumed state's)."""
    st = {"extra_blocks": getattr(args, "extra_blocks", 0), "critic": getattr(args, "critic", "shared"),
          "aux": list(aux_names(args))}
    if input_names(args):   # key only when used: older structures compare equal
        st["inputs"] = list(input_names(args))
    return st


def aux_targets(outcome, names):
    t = {"floor": min(max(float(outcome.get("floor", 0) or 0), 0.0), 57.0) / 57.0,
         "act4": 1.0 if int(outcome.get("act", 0) or 0) >= 4 else 0.0}
    return [t[n] for n in names]


def value_sparse_mask(games, k, seed, iteration):
    """--value-sparse k: per game, each act's first net decision plus k others drawn uniformly (seeded by the
    learner seed, the iteration and the game seed, so a rerun picks the same decisions)."""
    mask = []
    for g in games:
        acts = [s.get("act") for s in g["steps"]]
        keep = {t for t in range(len(acts)) if t == 0 or acts[t] != acts[t - 1]}
        rest = [t for t in range(len(acts)) if t not in keep]
        rng = random.Random(f"{seed}:{iteration}:{g['seed']}")
        keep.update(rng.sample(rest, min(k, len(rest))))
        mask.extend(t in keep for t in range(len(acts)))
    return mask


class Learner:
    def __init__(self, net, anchor, args, device):
        self.net, self.anchor, self.args, self.device = net.to(device), anchor, args, device
        if self.anchor is not None:
            self.anchor = self.anchor.to(device).eval()
            for p in self.anchor.parameters():
                p.requires_grad_(False)
        if getattr(net, "critic_net", None) is not None:   # the critic's whole trunk takes the value rate
            value_params = list(net.critic_net.parameters())
        else:
            value_params = list(net.value_head.parameters()) + list(net.value_head_norm.parameters())
        ids = {id(p) for p in value_params}
        self.opt = torch.optim.Adam([
            {"params": [p for p in net.parameters() if id(p) not in ids], "lr": args.lr},
            {"params": value_params, "lr": args.lr * args.value_lr_mult},
        ], eps=1e-6)
        self.iteration = 0
        self._compiled = {}

    def state(self):
        return {"net": self.net.state_dict(), "opt": self.opt.state_dict(), "iteration": self.iteration,
                "anchor": self.anchor.state_dict() if self.anchor is not None else None,
                "shape": shape_of(self.net), "args": vars(self.args)}

    def _batch(self, feats=None, store=None, idx=None):
        b = collate(feats) if store is None else store.batch(idx)
        if self.device.type == "cuda":   # pinned host memory lets the copy overlap with GPU work
            b["emb"] = {k: (x.pin_memory(), y.pin_memory()) for k, (x, y) in b["emb"].items()}
            b["fv"] = {k: (x.pin_memory(), y.pin_memory()) for k, (x, y) in b["fv"].items()}
        return b

    def _forward(self, net, feats=None, batch=None):
        if batch is None:
            batch = self._batch(feats)
        batch = batch_to(batch, self.device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=bool(self.args.amp) and self.device.type == "cuda"):
            out = self._callable(net)(batch)
        aux = out[2].float() if len(out) > 2 else None
        return out[0].float(), out[1].float(), aux

    def _callable(self, net):
        if not getattr(self.args, "compile", 0):
            return net
        if id(net) not in self._compiled:   # compiled wrapper shares the module's parameters
            self._compiled[id(net)] = torch.compile(net, dynamic=True)
        return self._compiled[id(net)]

    @torch.no_grad()
    def evaluate(self, feats, chunk=256, store=None):
        self.net.eval()
        store = store or FeatureStore(feats)
        N = len(store.n)
        vals, logits = [], []
        for i in range(0, N, chunk):
            lg, v, _ = self._forward(self.net, batch=self._batch(store=store, idx=range(i, min(i + chunk, N))))
            vals.extend(v.tolist())
            rows = lg.cpu().tolist()   # one host copy per chunk, not one per row
            logits.extend([rows[b][:store.n_choice[i + b]] for b in range(len(rows))])
        return vals, logits

    @torch.no_grad()
    def anchor_logp(self, feats, temps, chunk=256, store=None):
        out = []
        store = store or FeatureStore(feats)
        N = len(store.n)
        for i in range(0, N, chunk):
            lg, _, _ = self._forward(self.anchor, batch=self._batch(store=store, idx=range(i, min(i + chunk, N))))
            t = torch.tensor(temps[i:i + chunk], device=lg.device)[:, None]
            out.append(F.log_softmax(lg.float() / t, dim=-1).cpu())
        return out

    def update(self, games, value_only=False, log=print):
        a = self.args
        steps, feats = [], []
        for g in games:
            for s in g["steps"]:
                steps.append(s)
                feats.append(s["feat"] if "feat" in s else featurize(s["record"], self.net.trim_map))
        if not steps:
            raise ValueError("no net decisions in the trajectories")
        if a.reward == "heart_pbrs" and not any("phi" in s for s in steps):
            raise ValueError("--reward heart_pbrs: no decision line carries \"phi\" (the actor exports no "
                             "potential), so the shaping would be 0 and the reward silently equal to heart")
        t0 = time.time()
        store = FeatureStore(feats)
        values, logits_now = self.evaluate(feats, store=store)
        # Behaviour log-prob consistency (native vs torch, same weights only on the first iteration of a net).
        dlogp = []
        for s, lg in zip(steps, logits_now):
            if s["n"] > 1:
                t = s["temp"] if s["temp"] > 0 else 1.0
                z = [x / t for x in lg]
                m = max(z)
                lp = z[s["chosen"]] - m - math.log(sum(math.exp(x - m) for x in z))
                dlogp.append(abs(lp - s["logp"]))
        # Advantages per game.
        adv, ret = [], []
        k = 0
        for g in games:
            n = len(g["steps"])
            r = step_rewards(g, a.reward, a.gamma, a.act_bonus, a.key_bonus)
            ad, rt = gae(r, values[k:k + n], a.gamma, a.lam)
            adv.extend(ad); ret.extend(rt)
            k += n
        adv_t = torch.tensor(adv)
        policy_mask = torch.tensor([s["n"] > 1 for s in steps])
        if a.norm_adv and policy_mask.sum() > 1:
            m, sd = adv_t[policy_mask].mean(), adv_t[policy_mask].std().clamp_min(1e-8)
            adv_t = (adv_t - m) / sd
        ret_t, old_v = torch.tensor(ret), torch.tensor(values)
        old_logp = torch.tensor([float(s["logp"]) for s in steps])
        chosen = torch.tensor([int(s["chosen"]) for s in steps])
        if any(s["n"] > 1 and s["temp"] <= 0 for s in steps):
            raise ValueError("trajectory has greedy (temperature 0) decisions: their logp is not a sampling "
                             "probability, so PPO ratios are meaningless; collect with STS_OOC_HEART1_TEMPERATURE>0")
        temps = [float(s["temp"]) if s["temp"] > 0 else 1.0 for s in steps]
        temp_t = torch.tensor(temps)
        dev = self.device
        names_aux = getattr(self.net, "aux_names", ())
        aux_t = None
        if names_aux:
            aux_t = torch.tensor([aux_targets(g["outcome"], names_aux) for g in games for _ in g["steps"]]).to(dev)
        vmask = None
        if getattr(a, "value_sparse", 0) > 0:
            vmask = torch.tensor(value_sparse_mask(games, a.value_sparse, a.seed, self.iteration)).to(dev)
        anchor_lp = None
        kl_coef = a.kl_coef * (max(0.0, 1.0 - self.iteration / a.kl_decay_iters) if a.kl_decay_iters > 0 else 1.0)
        if kl_coef > 0 and self.anchor is not None and not value_only:
            rows = []
            for chunk in self.anchor_logp(feats, temps, store=store):
                rows.extend(list(chunk))
            # One padded (N, Cmax) tensor on the device; padding is -inf like a padded choice.
            cmax = max(r.shape[0] for r in rows)
            anchor_lp = torch.full((len(rows), cmax), float("-inf"))
            for j, r in enumerate(rows):
                anchor_lp[j, :r.shape[0]] = r
            anchor_lp = anchor_lp.to(dev)
        # Per-decision tensors live on the device for the whole update (no per-minibatch host copies).
        temp_t, policy_mask, chosen = temp_t.to(dev), policy_mask.to(dev), chosen.to(dev)
        old_logp, adv_t, ret_t, old_v = old_logp.to(dev), adv_t.to(dev), ret_t.to(dev), old_v.to(dev)
        prep = time.time() - t0

        self.net.train()
        minibatches = plan_minibatches(a, feats, self.iteration)
        names = ("policy", "value", "entropy", "kl_anchor", "clipfrac", "approx_kl", "aux")
        acc = torch.zeros(len(names), device=dev)   # accumulated on the device: one sync per update
        first = None
        nmb = 0
        t1 = time.time()
        micro = getattr(a, "micro_batch", 0)

        def chunks(idx):   # one chunk (the whole minibatch) unless --micro-batch splits it
            step = micro if 0 < micro < len(idx) else len(idx)
            return [idx[i:i + step] for i in range(0, len(idx), step)]

        def collate_mb(idx):
            return [(c, self._batch(store=store, idx=c)) for c in chunks(idx)]

        pool = ThreadPoolExecutor(max_workers=1)   # collates minibatch k+1 while the GPU runs minibatch k
        nxt = pool.submit(collate_mb, minibatches[0])
        for k, mb_full in enumerate(minibatches):
            parts = nxt.result()
            if k + 1 < len(minibatches):
                nxt = pool.submit(collate_mb, minibatches[k + 1])
            self.opt.zero_grad(set_to_none=True)
            # Every loss term is a sum over the minibatch's decisions divided by a minibatch-wide count, so chunk
            # sums with those counts add up to the full minibatch's loss (and gradient).
            denom = policy_mask[torch.tensor(mb_full, device=dev)].sum().clamp_min(1)
            n_full = len(mb_full)
            vden = vmask[torch.tensor(mb_full, device=dev)].sum().clamp_min(1) if vmask is not None else None
            row = None
            for mb_list, batch in parts:
                row_c = self._minibatch_loss(mb_list, batch, len(parts) == 1, denom, n_full, temp_t, policy_mask,
                                             chosen, old_logp, adv_t, ret_t, old_v, anchor_lp, kl_coef, value_only,
                                             aux_t, vmask, vden)
                row = row_c if row is None else row + row_c
            if value_only:
                # Value warm-up: only the value head and its norm move; the shared trunk (and so the
                # policy) stays put.
                for p in self.opt.param_groups[0]["params"]:
                    p.grad = None
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), a.max_grad_norm)
            self.opt.step()
            with torch.no_grad():
                acc += row
                if first is None:
                    first = row.clone()   # first minibatch: ratio is ~1 up to bf16/fp32 forward noise
            nmb += 1
        pool.shutdown()
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        train_s = time.time() - t1
        return self._finish_update(games, steps, names, acc, first, nmb, kl_coef, policy_mask, prep, train_s,
                                   value_only, dlogp, ret_t, old_v, log,
                                   int(vmask.sum()) if vmask is not None else len(steps))

    def _minibatch_loss(self, mb_list, batch, whole, denom, n_full, temp_t, policy_mask, chosen, old_logp, adv_t,
                        ret_t, old_v, anchor_lp, kl_coef, value_only, aux_t=None, vmask=None, vden=None):
        """Forward and backward of one minibatch (whole) or one chunk of it; returns its stats row."""
        a, dev = self.args, self.device
        mb = torch.tensor(mb_list, device=dev)
        logits, value, aux = self._forward(self.net, batch=batch)
        t = temp_t[mb][:, None]
        logp_all = F.log_softmax(logits.float() / t, dim=-1)   # fp32 even under bf16 autocast
        pad = torch.isneginf(logits)
        logp_safe = logp_all.masked_fill(pad, 0.0)   # 0 * -inf would make NaN gradients
        pm = policy_mask[mb]
        lp = logp_all.gather(1, chosen[mb][:, None]).squeeze(1)
        ratio = torch.exp(lp - old_logp[mb])
        ad = adv_t[mb]
        pg = -torch.min(ratio * ad, ratio.clamp(1 - a.clip, 1 + a.clip) * ad)
        if whole:   # the original expressions, bit for bit
            denom = pm.sum().clamp_min(1)
            vmean = torch.mean
        else:
            vmean = lambda x: x.sum() / n_full   # noqa: E731
        policy_loss = (pg * pm).sum() / denom
        p_all = logp_safe.exp().masked_fill(pad, 0.0)
        ent = -(p_all * logp_safe).sum(-1)
        entropy = (ent * pm).sum() / denom
        rt = ret_t[mb]
        if vmask is not None:   # --value-sparse: mean over the minibatch's selected decisions
            vm = vmask[mb].to(value.dtype)
            vmean = lambda x: (x * vm).sum() / vden   # noqa: E731
        if a.value_clip > 0:
            ov = old_v[mb]
            vc = ov + (value - ov).clamp(-a.value_clip, a.value_clip)
            value_loss = 0.5 * vmean(torch.max((value - rt) ** 2, (vc - rt) ** 2))
        else:
            value_loss = 0.5 * vmean((value - rt) ** 2)
        aux_loss = torch.zeros((), device=dev)
        if aux is not None:   # per head: MSE (floor) or BCE on a logit (act4), mean over the minibatch
            amean = torch.mean if whole else (lambda x: x.sum() / n_full)   # noqa: E731
            names_aux = self.net.aux_names
            tgt = aux_t[mb]
            for j, n in enumerate(names_aux):
                if n == "act4":
                    term = F.binary_cross_entropy_with_logits(aux[:, j], tgt[:, j], reduction="none")
                else:
                    term = (aux[:, j] - tgt[:, j]) ** 2
                aux_loss = aux_loss + amean(term)
        kl_anchor = torch.zeros((), device=dev)
        if anchor_lp is not None:
            alp = anchor_lp[mb][:, :logp_all.shape[1]]
            if alp.shape[1] < logp_all.shape[1]:
                alp = F.pad(alp, (0, logp_all.shape[1] - alp.shape[1]), value=float("-inf"))
            alp = alp.masked_fill(pad | torch.isneginf(alp), 0.0)
            kl_anchor = ((p_all * (logp_safe - alp)).sum(-1) * pm).sum() / denom
        if value_only:
            loss = a.value_coef * value_loss
        else:
            loss = policy_loss + a.value_coef * value_loss - a.entropy_coef * entropy + kl_coef * kl_anchor
            if aux is not None:
                loss = loss + a.aux_weight * aux_loss
        loss.backward()   # accumulates into .grad across the chunks of one minibatch
        with torch.no_grad():
            return torch.stack([policy_loss.detach().float(), value_loss.detach().float(),
                                entropy.detach().float(), kl_anchor.detach().float(),
                                ((((ratio - 1).abs() > a.clip) & pm).sum() / denom).float(),
                                ((((ratio - 1) - torch.log(ratio)) * pm).sum() / denom).float(),
                                aux_loss.detach().float()])

    def _finish_update(self, games, steps, names, acc, first, nmb, kl_coef, policy_mask, prep, train_s, value_only,
                       dlogp, ret_t, old_v, log, value_decisions=None):
        stats = dict(zip(names, acc.tolist()))
        if first is not None:
            f = first.tolist()
            stats_first = {"first_mb_approx_kl": f[5], "first_mb_clipfrac": f[4]}
        else:
            stats_first = {}
        self.iteration += 1
        out = {k: v / max(nmb, 1) for k, v in stats.items()}
        out.update(stats_first)
        heart = sum(1 for g in games if g["outcome"].get("heart_kill")) / max(len(games), 1)
        out.update({"iteration": self.iteration, "kl_coef": kl_coef, "games": len(games), "decisions": len(steps),
                    "policy_decisions": int(policy_mask.sum()), "value_decisions": value_decisions,
                    "minibatches": nmb, "prep_s": prep,
                    "train_s": train_s, "heart_rate": heart, "value_only": value_only,
                    "micro_batch": getattr(self.args, "micro_batch", 0),
                    "max_dlogp_behaviour": max(dlogp) if dlogp else 0.0,
                    "mean_return": float(ret_t.mean()), "mean_value": float(old_v.mean())})
        log(json.dumps(out))
        return out


def shape_of(net):
    shape = {"dim": net.dim, "heads": net.heads, "hidden": net.hidden, "layers": len(net.blocks),
             "trim_map": net.trim_map, "rows": {k: int(v.shape[0]) for k, v in net.tables.items()}}
    if net.extra_blocks or net.critic_mode != "shared" or net.aux_names or net.extra_inputs:
        # arch arms only: older states unchanged
        shape.update({"extra_blocks": net.extra_blocks, "critic": net.critic_mode, "aux": list(net.aux_names)})
        if net.extra_inputs:
            shape["inputs"] = list(net.extra_inputs)
    return shape


def shape_structure(shape):
    st = {"extra_blocks": shape.get("extra_blocks", 0), "critic": shape.get("critic", "shared"),
          "aux": list(shape.get("aux", []))}
    if shape.get("inputs"):
        st["inputs"] = list(shape["inputs"])
    return st


def net_from_shape(shape):
    st = shape_structure(shape)
    net = PolicyNet(shape["dim"], shape["heads"], shape["hidden"], shape["layers"] - st["extra_blocks"],
                    shape["rows"], shape["trim_map"])
    if st != shape_structure({}):   # weights come from the state dict
        net = construct(net, st["extra_blocks"], st["critic"], st["aux"], inputs=st.get("inputs", ()))
    return net


def make_learner(args, device):
    if args.state and os.path.exists(args.state):
        st = torch.load(args.state, map_location="cpu", weights_only=False)
        if shape_structure(st["shape"]) != structure_of(args):
            sys.exit(f"{args.state}: net structure {shape_structure(st['shape'])} but the flags ask for "
                     f"{structure_of(args)}; a running arm changes structure only through a fork "
                     f"(ppo_cloud.py init --fork-dir)")
        net = net_from_shape(st["shape"]); net.load_state_dict(st["net"])
        anchor = None
        if st.get("anchor") is not None:
            anchor = net_from_shape(st.get("anchor_shape", st["shape"])); anchor.load_state_dict(st["anchor"])
        learner = Learner(net, anchor, args, device)
        learner.opt.load_state_dict(st["opt"])
        for g, lr in zip(learner.opt.param_groups, (args.lr, args.lr * args.value_lr_mult)):
            g["lr"] = lr   # schedules set the rate per call
        learner.iteration = st["iteration"]
        return learner
    if not args.init:
        sys.exit("no --state to resume and no --init net")
    net = PolicyNet.from_bin(args.init)
    anchor = PolicyNet.from_bin(args.init)
    st = structure_of(args)
    if st != shape_structure({}):
        net = construct(net, st["extra_blocks"], st["critic"], st["aux"], seed=args.seed,
                        inputs=[k for k in st.get("inputs", ()) if k not in net.fixedvecs])
    return Learner(net, anchor, args, device)


def fork_learner(state_path, args, device=None):
    """A running arm's checkpoint with the arch flags of `args` applied (arch screen design B).

    The source state must have the plain structure. Net, anchor and iteration are kept; the arm's construction
    is applied to the net (construct(), seeded by args.seed); every parameter that exists in the source keeps
    its Adam moments and step, and new tensors (extra blocks, the critic copy, aux heads) start with none
    (Adam's zero moments). With no arch flag set the result is the source state itself, bit for bit."""
    device = device or torch.device("cpu")
    st = torch.load(state_path, map_location="cpu", weights_only=False)
    if shape_structure(st["shape"]) != shape_structure({}):
        sys.exit(f"{state_path}: already has structure {shape_structure(st['shape'])}; forks start from a plain arm")
    base = argparse.Namespace(**vars(args))
    base.extra_blocks, base.critic, base.aux_heads, base.inputs, base.state = 0, "shared", "", "", state_path
    src = make_learner(base, device)
    want = structure_of(args)
    if want == shape_structure({}):
        src.args = args
        return src
    net = construct(src.net, want["extra_blocks"], want["critic"], want["aux"], seed=args.seed,
                    inputs=want.get("inputs", ()))
    learner = Learner(net, src.anchor, args, device)
    learner.iteration = src.iteration
    old = dict(src.net.named_parameters())
    for name, p in learner.net.named_parameters():
        q = old.get(name)
        if q is not None and q.shape == p.shape and q in src.opt.state:
            learner.opt.state[p] = {k: v.clone() for k, v in src.opt.state[q].items()}
    return learner


def save(learner, path):
    tmp = path + ".tmp"
    st = learner.state()
    if learner.anchor is not None and shape_of(learner.anchor) != st["shape"]:
        st["anchor_shape"] = shape_of(learner.anchor)   # a constructed net keeps its plain start net as anchor
    torch.save(st, tmp)
    os.replace(tmp, path)


# ---------------------------------------------------------------- commands

def cmd_update(argv):
    ap = argparse.ArgumentParser(prog="ppo_train.py update")
    ap.add_argument("--state", required=True, help="checkpoint to resume and overwrite")
    ap.add_argument("--init", help="start net (.bin) when --state does not exist")
    ap.add_argument("--traj", nargs="+", required=True)
    ap.add_argument("--out-bin", required=True, help="native export of the updated net")
    ap.add_argument("--value-only", action="store_true", help="critic warm-up: no policy, entropy or KL terms")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--log", help="append the iteration's stats line here")
    ap.add_argument("--expect-games", type=int,
                    help="fail unless the trajectories hold exactly this many games (a file cut at a line boundary "
                         "loses its last games without any parse error)")
    add_hparams(ap)
    args = ap.parse_args(argv)
    torch.manual_seed(args.seed)
    learner = make_learner(args, torch.device(args.device))
    games = load_games(args.traj, learner.net.trim_map, phi_model=phi_model_for(args))
    if args.expect_games is not None and len(games) != args.expect_games:
        sys.exit(f"{len(games)} games in {' '.join(args.traj)}, expected {args.expect_games}")
    logf = open(args.log, "a") if args.log else None

    def log(line):
        print(line, flush=True)
        if logf:
            logf.write(line + "\n"); logf.flush()

    learner.update(games, value_only=args.value_only, log=log)
    learner.net.to("cpu").to_bin(args.out_bin)
    learner.net.to(args.device)
    save(learner, args.state)


def cmd_bench(argv):
    ap = argparse.ArgumentParser(prog="ppo_train.py bench")
    ap.add_argument("--init", required=True)
    ap.add_argument("--traj", nargs="+", required=True, help="real games, replicated to the requested count")
    ap.add_argument("--games", type=int, nargs="+", default=[512, 1024, 2048])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", help="append one JSON line per size")
    add_hparams(ap)
    args = ap.parse_args(argv)
    t0 = time.time()
    base = load_games(args.traj, PolicyNet.from_bin(args.init).trim_map)
    if not base:
        sys.exit("no games")
    feat_s = (time.time() - t0) / len(base)
    feat_bytes = sum(s["feat"]["emb"].nbytes + sum(a.nbytes + b.nbytes for a, b in s["feat"]["fv"].values())
                     for g in base for s in g["steps"]) / len(base)
    dev = torch.device(args.device)
    for n in args.games:
        games = [base[i % len(base)] for i in range(n)]
        learner = Learner(PolicyNet.from_bin(args.init), PolicyNet.from_bin(args.init) if args.kl_coef > 0 else None,
                          args, dev)
        t0 = time.time()
        stats = learner.update(games, log=lambda _: None)
        row = {"games": n, "decisions": stats["decisions"], "epochs": args.epochs, "minibatch": args.minibatch,
               "prep_s": round(stats["prep_s"], 2), "train_s": round(stats["train_s"], 2),
               "total_s": round(time.time() - t0, 2), "load_featurize_s": round(feat_s * n, 2),
               "feature_gb": round(feat_bytes * n / 2**30, 3), "device": str(dev),
               "gpu": torch.cuda.get_device_name(0) if dev.type == "cuda" else "",
               "max_mem_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2) if dev.type == "cuda" else 0}
        print(json.dumps(row), flush=True)
        if args.out:
            with open(args.out, "a") as f:
                f.write(json.dumps(row) + "\n")
        del learner
        if dev.type == "cuda":
            torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()


def cmd_selftest(argv):
    """GAE / reward arithmetic on hand-computed cases (no net needed)."""
    adv, ret = gae([0.0, 0.0, 1.0], [0.5, 0.5, 0.5], 1.0, 1.0)
    assert [round(x, 9) for x in adv] == [0.5, 0.5, 0.5] and [round(x, 9) for x in ret] == [1.0, 1.0, 1.0], (adv, ret)
    adv, _ = gae([0.0, 1.0], [0.2, 0.6], 1.0, 0.0)
    assert [round(x, 9) for x in adv] == [0.4, 0.4], adv
    g = {"steps": [{"phi": 0.2}, {"phi": 0.5}], "outcome": {"heart_kill": True, "floor": 57, "keys": [1, 1, 1]}}
    r = step_rewards(g, "heart_pbrs", 1.0)
    assert [round(x, 9) for x in r] == [0.3, 0.5], r   # 0.5-0.2 ; 0-0.5+1 -> sum = 1 - phi(s0)
    assert abs(terminal_reward(g["outcome"], "original") - (57 / 190 + 0.15 + 0.6)) < 1e-12
    g2 = {"steps": [{"phi_py": 0.1}, {"phi_py": 0.4}], "outcome": {"heart_kill": False, "floor": 34, "keys": [1, 0, 0]}}
    r = step_rewards(g2, "heart_phi", 1.0)
    assert [round(x, 9) for x in r] == [0.3, -0.4], r   # sum = 0 - phi(s0): the objective is unchanged
    try:
        step_rewards({"steps": [{}], "outcome": {}}, "heart_phi", 1.0)
        raise AssertionError("heart_phi without phi_py must raise")
    except ValueError:
        pass
    assert abs(terminal_reward(g2["outcome"], "heart_act") - (0.2 + 0.05)) < 1e-12   # acts 1, 2 cleared + 1 key
    assert abs(terminal_reward(g["outcome"], "heart_act", 0.1, 0.05) - (1 + 0.3 + 0.15)) < 1e-12
    assert step_rewards(g2, "heart_act", 1.0, 0.0, 0.0) == [0.0, 0.0]
    print("ppo_train selftest passed")


def cmd_score(argv):
    """score STATE.pt records.jsonl out.jsonl: the learner checkpoint's critic value per record ({"value": v}).

    The arch screen's critic secondary (PREREG ppo_arch_screen_20261102) reads the critic from state.pt, because a
    separate critic and the aux heads are not exported to the native .bin. The output has heart1score's "value"
    field, one line per record in input order, so the §747 teacher check (heart1_value_leaf_teacher_20261102
    gates.py) reads it unchanged. Records are JSON objects, or {"record": ...} lines."""
    ap = argparse.ArgumentParser(prog="ppo_train.py score")
    ap.add_argument("state")
    ap.add_argument("records")
    ap.add_argument("out")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch", type=int, default=256)
    a = ap.parse_args(argv)
    st = torch.load(a.state, map_location="cpu", weights_only=False)
    net = net_from_shape(st["shape"])
    net.load_state_dict(st["net"])
    dev = torch.device(a.device)
    net = net.to(dev).eval()
    opener = gzip.open if a.records.endswith(".gz") else open
    n = 0
    with torch.no_grad(), open(a.out + ".tmp", "w") as out:
        chunk = []

        def flush():
            out_ = net(batch_to(collate([featurize(r, net.trim_map) for r in chunk]), dev))
            for v in out_[1].float().cpu().tolist():
                out.write(json.dumps({"value": v}) + "\n")

        with opener(a.records, "rt") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                chunk.append(row.get("record", row))
                if len(chunk) == a.batch:
                    flush(); n += len(chunk); chunk = []
        if chunk:
            flush(); n += len(chunk)
    os.replace(a.out + ".tmp", a.out)
    print(f"{a.state}: {n} values (structure {shape_structure(st['shape'])}, iteration {st.get('iteration')})")


if __name__ == "__main__":
    cmds = {"update": cmd_update, "bench": cmd_bench, "selftest": cmd_selftest, "score": cmd_score}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ppo_train.py {update|bench|selftest|score} ...")
    cmds[sys.argv[1]](sys.argv[2:])
