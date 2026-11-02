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
Decisions with one choice (source heart1_ppo_single) train the critic only; fallback lines (chain) are skipped.

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
from ppo_model import FeatureStore, PolicyNet, batch_to, collate, featurize  # noqa: E402

SCHEMA = "heart1-ppo-traj-v1"
NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")


# ---------------------------------------------------------------- trajectories

def _parse_line(line, trim_map=None):
    """One trajectory line -> row; with trim_map, a net decision's record is featurised (worker-safe).

    Errors come back as {"type": "_error"} rows instead of raising in the worker, so the pool always drains and
    closes normally (terminating a pool mid-stream can deadlock); load_games raises them afterwards."""
    if not line.strip():
        return None
    try:
        row = json.loads(line)
        if trim_map is not None and row["type"] == "decision":
            rec = row.pop("record", None)
            row.pop("logits", None)
            if row["source"] in NET_SOURCES:
                row["feat"] = featurize(rec, trim_map)
        return row
    except Exception as e:   # noqa: BLE001 - re-raised by the parent with the line number
        return {"type": "_error", "error": f"{type(e).__name__}: {e}"}


def load_games(paths, trim_map=None, workers=None):
    """Games with all their net decisions, in decision order. A game without its "game" line is dropped.

    With trim_map (the learner net's flag), each net decision's record is featurised while loading and only the
    packed features are kept ("feat"; record and logits are dropped), so host memory stays at a few KB per decision.
    Parsing and featurising run in `workers` processes (default min(8, CPUs); 1 = in-process); the result is the
    same either way."""
    if workers is None:
        workers = min(8, os.cpu_count() or 1)
    pool = None
    if workers > 1 and trim_map is not None:
        import multiprocessing as mp
        pool = mp.get_context("fork" if hasattr(os, "fork") else "spawn").Pool(workers)
    parse = functools.partial(_parse_line, trim_map=trim_map)
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
    pending, games, seen = {}, [], set()
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
                if key in seen:
                    raise ValueError(f"{path}: seed {row['seed']} has two game lines (reused seed?)")
                seen.add(key)
                steps = sorted(pending.pop(key, []), key=lambda r: r["idx"])
                steps = [s for s in steps if s["source"] in NET_SOURCES]
                games.append({"seed": row["seed"], "outcome": row["outcome"], "info": row, "steps": steps})
    return games


def terminal_reward(outcome, kind):
    heart = 1.0 if outcome.get("heart_kill") else 0.0
    if kind in ("heart", "heart_pbrs"):
        return heart
    if kind == "original":
        return outcome.get("floor", 0) / 190.0 + 0.05 * sum(outcome.get("keys", [])) + 0.6 * heart
    raise ValueError(f"unknown reward {kind}")


def step_rewards(game, kind, gamma):
    """Per-step rewards: 0 except the last step's terminal reward, plus PBRS terms for heart_pbrs."""
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
    r[-1] += terminal_reward(game["outcome"], kind)
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
    ap.add_argument("--reward", default="heart", choices=["heart", "original", "heart_pbrs"])
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
    ap.add_argument("--bucket", type=int, default=0,
                    help="length-bucketed minibatches: sort each window of BUCKET*minibatch shuffled decisions by "
                         "token count before cutting minibatches (less padding; changes minibatch composition; 0 = off)")


class Learner:
    def __init__(self, net, anchor, args, device):
        self.net, self.anchor, self.args, self.device = net.to(device), anchor, args, device
        if self.anchor is not None:
            self.anchor = self.anchor.to(device).eval()
            for p in self.anchor.parameters():
                p.requires_grad_(False)
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
            logits, value = self._callable(net)(batch)
        return logits.float(), value.float()

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
            lg, v = self._forward(self.net, batch=self._batch(store=store, idx=range(i, min(i + chunk, N))))
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
            lg, _ = self._forward(self.anchor, batch=self._batch(store=store, idx=range(i, min(i + chunk, N))))
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
            r = step_rewards(g, a.reward, a.gamma)
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
        idx = list(range(len(steps)))
        rng = random.Random(a.seed * 1000003 + self.iteration)
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
        names = ("policy", "value", "entropy", "kl_anchor", "clipfrac", "approx_kl")
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
            row = None
            for mb_list, batch in parts:
                row_c = self._minibatch_loss(mb_list, batch, len(parts) == 1, denom, n_full, temp_t, policy_mask,
                                             chosen, old_logp, adv_t, ret_t, old_v, anchor_lp, kl_coef, value_only)
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
                                   value_only, dlogp, ret_t, old_v, log)

    def _minibatch_loss(self, mb_list, batch, whole, denom, n_full, temp_t, policy_mask, chosen, old_logp, adv_t,
                        ret_t, old_v, anchor_lp, kl_coef, value_only):
        """Forward and backward of one minibatch (whole) or one chunk of it; returns its stats row."""
        a, dev = self.args, self.device
        mb = torch.tensor(mb_list, device=dev)
        logits, value = self._forward(self.net, batch=batch)
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
        if a.value_clip > 0:
            ov = old_v[mb]
            vc = ov + (value - ov).clamp(-a.value_clip, a.value_clip)
            value_loss = 0.5 * vmean(torch.max((value - rt) ** 2, (vc - rt) ** 2))
        else:
            value_loss = 0.5 * vmean((value - rt) ** 2)
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
        loss.backward()   # accumulates into .grad across the chunks of one minibatch
        with torch.no_grad():
            return torch.stack([policy_loss.detach().float(), value_loss.detach().float(),
                                entropy.detach().float(), kl_anchor.detach().float(),
                                ((((ratio - 1).abs() > a.clip) & pm).sum() / denom).float(),
                                ((((ratio - 1) - torch.log(ratio)) * pm).sum() / denom).float()])

    def _finish_update(self, games, steps, names, acc, first, nmb, kl_coef, policy_mask, prep, train_s, value_only,
                       dlogp, ret_t, old_v, log):
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
                    "policy_decisions": int(policy_mask.sum()), "minibatches": nmb, "prep_s": prep,
                    "train_s": train_s, "heart_rate": heart, "value_only": value_only,
                    "micro_batch": getattr(self.args, "micro_batch", 0),
                    "max_dlogp_behaviour": max(dlogp) if dlogp else 0.0,
                    "mean_return": float(ret_t.mean()), "mean_value": float(old_v.mean())})
        log(json.dumps(out))
        return out


def shape_of(net):
    return {"dim": net.dim, "heads": net.heads, "hidden": net.hidden, "layers": len(net.blocks),
            "trim_map": net.trim_map, "rows": {k: int(v.shape[0]) for k, v in net.tables.items()}}


def net_from_shape(shape):
    return PolicyNet(shape["dim"], shape["heads"], shape["hidden"], shape["layers"], shape["rows"], shape["trim_map"])


def make_learner(args, device):
    if args.state and os.path.exists(args.state):
        st = torch.load(args.state, map_location="cpu", weights_only=False)
        net = net_from_shape(st["shape"]); net.load_state_dict(st["net"])
        anchor = None
        if st.get("anchor") is not None:
            anchor = net_from_shape(st["shape"]); anchor.load_state_dict(st["anchor"])
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
    return Learner(net, anchor, args, device)


def save(learner, path):
    tmp = path + ".tmp"
    torch.save(learner.state(), tmp)
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
    add_hparams(ap)
    args = ap.parse_args(argv)
    torch.manual_seed(args.seed)
    learner = make_learner(args, torch.device(args.device))
    games = load_games(args.traj, learner.net.trim_map)
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
    print("ppo_train selftest passed")


if __name__ == "__main__":
    cmds = {"update": cmd_update, "bench": cmd_bench, "selftest": cmd_selftest}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ppo_train.py {update|bench|selftest} ...")
    cmds[sys.argv[1]](sys.argv[2:])
