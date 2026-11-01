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
import gzip
import json
import math
import os
import random
import sys
import time

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppo_model import PolicyNet, batch_to, collate, featurize  # noqa: E402

SCHEMA = "heart1-ppo-traj-v1"
NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")


# ---------------------------------------------------------------- trajectories

def load_games(paths, trim_map=None):
    """Games with all their net decisions, in decision order. A game without its "game" line is dropped.

    With trim_map (the learner net's flag), each step's record is featurised when its game completes and only the
    packed features are kept ("feat"; record and logits are dropped), so host memory stays at a few KB per decision."""
    pending, games, seen = {}, [], set()
    for path in paths:
        with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
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
                    if trim_map is not None:
                        for s in steps:
                            s["feat"] = featurize(s.pop("record"), trim_map)
                            s.pop("logits", None)
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
    ap.add_argument("--max-grad-norm", type=float, default=1.0)
    ap.add_argument("--norm-adv", type=int, default=1, help="normalise advantages per update")
    ap.add_argument("--value-clip", type=float, default=0.0, help="PPO value clipping range (0 = off)")
    ap.add_argument("--amp", type=int, default=1, help="bf16 autocast on CUDA")
    ap.add_argument("--seed", type=int, default=0)


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

    def state(self):
        return {"net": self.net.state_dict(), "opt": self.opt.state_dict(), "iteration": self.iteration,
                "anchor": self.anchor.state_dict() if self.anchor is not None else None,
                "shape": shape_of(self.net), "args": vars(self.args)}

    def _forward(self, net, feats):
        batch = batch_to(collate(feats), self.device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=self.args.amp and self.device.type == "cuda"):
            logits, value = net(batch)
        return logits.float(), value.float()

    @torch.no_grad()
    def evaluate(self, feats, chunk=256):
        self.net.eval()
        vals, logits = [], []
        for i in range(0, len(feats), chunk):
            lg, v = self._forward(self.net, feats[i:i + chunk])
            vals.extend(v.tolist())
            logits.extend([lg[b, :feats[i + b]["n_choice"]].tolist() for b in range(lg.shape[0])])
        return vals, logits

    @torch.no_grad()
    def anchor_logp(self, feats, temps, chunk=256):
        out = []
        for i in range(0, len(feats), chunk):
            lg, _ = self._forward(self.anchor, feats[i:i + chunk])
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
        values, logits_now = self.evaluate(feats)
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
        anchor_lp = None
        if a.kl_coef > 0 and self.anchor is not None and not value_only:
            anchor_lp = self.anchor_logp(feats, temps)
            flat = []
            for chunk in anchor_lp:
                flat.extend(list(chunk))
            anchor_lp = flat
        prep = time.time() - t0

        self.net.train()
        idx = list(range(len(steps)))
        rng = random.Random(a.seed * 1000003 + self.iteration)
        stats = {"policy": 0.0, "value": 0.0, "entropy": 0.0, "kl_anchor": 0.0, "clipfrac": 0.0, "approx_kl": 0.0}
        nmb = 0
        t1 = time.time()
        for _ in range(a.epochs):
            rng.shuffle(idx)
            for i in range(0, len(idx), a.minibatch):
                mb = idx[i:i + a.minibatch]
                logits, value = self._forward(self.net, [feats[j] for j in mb])
                dev = logits.device
                t = temp_t[mb].to(dev)[:, None]
                logp_all = F.log_softmax(logits.float() / t, dim=-1)   # fp32 even under bf16 autocast
                pad = torch.isneginf(logits)
                logp_safe = logp_all.masked_fill(pad, 0.0)   # 0 * -inf would make NaN gradients
                pm = policy_mask[mb].to(dev)
                lp = logp_all.gather(1, chosen[mb].to(dev)[:, None]).squeeze(1)
                ratio = torch.exp(lp - old_logp[mb].to(dev))
                ad = adv_t[mb].to(dev)
                pg = -torch.min(ratio * ad, ratio.clamp(1 - a.clip, 1 + a.clip) * ad)
                denom = pm.sum().clamp_min(1)
                policy_loss = (pg * pm).sum() / denom
                p_all = logp_safe.exp().masked_fill(pad, 0.0)
                ent = -(p_all * logp_safe).sum(-1)
                entropy = (ent * pm).sum() / denom
                rt = ret_t[mb].to(dev)
                if a.value_clip > 0:
                    ov = old_v[mb].to(dev)
                    vc = ov + (value - ov).clamp(-a.value_clip, a.value_clip)
                    value_loss = 0.5 * torch.max((value - rt) ** 2, (vc - rt) ** 2).mean()
                else:
                    value_loss = 0.5 * ((value - rt) ** 2).mean()
                kl_anchor = torch.zeros((), device=dev)
                if anchor_lp is not None:
                    alp = torch.zeros_like(logp_all)
                    for r, j in enumerate(mb):
                        row = anchor_lp[j][:logp_all.shape[1]]
                        alp[r, :row.shape[0]] = row.to(dev)
                    alp = alp.masked_fill(pad | torch.isneginf(alp), 0.0)
                    kl_anchor = ((p_all * (logp_safe - alp)).sum(-1) * pm).sum() / denom
                if value_only:
                    loss = a.value_coef * value_loss
                else:
                    loss = policy_loss + a.value_coef * value_loss - a.entropy_coef * entropy + a.kl_coef * kl_anchor
                self.opt.zero_grad(set_to_none=True)
                loss.backward()
                if value_only:
                    # Value warm-up: only the value head and its norm move; the shared trunk (and so the
                    # policy) stays put.
                    for p in self.opt.param_groups[0]["params"]:
                        p.grad = None
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), a.max_grad_norm)
                self.opt.step()
                with torch.no_grad():
                    stats["policy"] += float(policy_loss); stats["value"] += float(value_loss)
                    stats["entropy"] += float(entropy); stats["kl_anchor"] += float(kl_anchor)
                    stats["clipfrac"] += float((((ratio - 1).abs() > a.clip) & pm).sum() / denom)
                    stats["approx_kl"] += float((((ratio - 1) - torch.log(ratio)) * pm).sum() / denom)
                nmb += 1
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        train_s = time.time() - t1
        self.iteration += 1
        out = {k: v / max(nmb, 1) for k, v in stats.items()}
        heart = sum(1 for g in games if g["outcome"].get("heart_kill")) / max(len(games), 1)
        out.update({"iteration": self.iteration, "games": len(games), "decisions": len(steps),
                    "policy_decisions": int(policy_mask.sum()), "minibatches": nmb, "prep_s": prep,
                    "train_s": train_s, "heart_rate": heart, "value_only": value_only,
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
