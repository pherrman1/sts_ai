"""Per-game policy-gradient vectors of one PPO update batch (offline, CPU).

usage: gradnoise.py NET OUT TAG TRAJ [TRAJ ...]
Writes OUT/TAG.grads.f16 (n_games x P memmap), OUT/TAG.meta.json (per game: seed, heart, n decisions,
sum |A|, sum A, ...). Loss per game = sum over its policy decisions of the PPO clipped surrogate with the
learner's advantages (GAE gamma 1, lambda 0.97, net's value head, batch-normalised), no entropy, no value term:
the batch's policy gradient is (1/D) * sum of these vectors.
"""
import json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools", "heart1"))
import torch
import torch.nn.functional as F
import ppo_train
from ppo_train import PolicyNet, FeatureStore, Learner, load_games, step_rewards, gae

net_path, out, tag, trajs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
torch.set_num_threads(int(os.environ.get("THREADS", "4")))
a = ppo_train.default_args()
net = PolicyNet.from_bin(net_path)
L = Learner(net, None, a, torch.device("cpu"))
t0 = time.time()
games = load_games(trajs, net.trim_map, workers=4)
games = [g for g in games if g["steps"]]
feats = [s["feat"] for g in games for s in g["steps"]]
steps = [s for g in games for s in g["steps"]]
print(f"{len(games)} games, {len(feats)} decisions, load {time.time() - t0:.0f}s", flush=True)
values, logits = L.evaluate(feats)
adv, ret = [], []
k = 0
for g in games:
    n = len(g["steps"])
    r = step_rewards(g, a.reward, a.gamma)
    ad, rt = gae(r, values[k:k + n], a.gamma, a.lam)
    adv += ad; ret += rt; k += n
adv = np.array(adv); ret = np.array(ret); vals = np.array(values)
pm = np.array([s["n"] > 1 for s in steps])
m, sd = adv[pm].mean(), adv[pm].std(ddof=1)
advn = (adv - m) / sd
old_logp = np.array([float(s["logp"]) for s in steps])
chosen = np.array([int(s["chosen"]) for s in steps])
temps = np.array([float(s["temp"]) if s["temp"] > 0 else 1.0 for s in steps])
# behaviour/current log-prob gap (0 for on-policy data)
cur_lp = []
for s, lg in zip(steps, logits):
    z = np.array(lg) / (s["temp"] if s["temp"] > 0 else 1.0)
    z = z - z.max(); cur_lp.append(z[s["chosen"]] - np.log(np.exp(z).sum()))
cur_lp = np.array(cur_lp)
print(f"evaluate done {time.time() - t0:.0f}s; mean|dlogp| {np.abs(cur_lp - old_logp)[pm].mean():.4f}", flush=True)

params = [p for p in net.parameters()]
names = [n for n, _ in net.named_parameters()]
P = sum(p.numel() for p in params)
groups = []   # (name, lo, hi)
off = 0
for n, p in zip(names, params):
    grp = "tables" if n.startswith("tables.") else ("fixedvecs" if n.startswith("fixedvecs.") else
                                                   ("blocks" if n.startswith("blocks.") else "head"))
    groups.append((n, grp, off, off + p.numel())); off += p.numel()
G = np.lib.format.open_memmap(os.path.join(out, f"{tag}.grads.npy"), mode="w+", dtype=np.float16,
                              shape=(len(games), P))
meta = {"tag": tag, "net": net_path, "P": P, "groups": groups, "adv_mean": m, "adv_sd": sd,
        "decisions": len(feats), "policy_decisions": int(pm.sum()), "games": []}
net.train()
k = 0
t1 = time.time()
for gi, g in enumerate(games):
    n = len(g["steps"])
    idx = list(range(k, k + n))
    fs = FeatureStore(feats[k:k + n])
    batch = L._batch(store=fs, idx=range(n))
    lg, v, _ = L._forward(net, batch=batch)
    t = torch.tensor(temps[idx])[:, None]
    lp_all = F.log_softmax(lg / t, dim=-1)
    lp = lp_all.gather(1, torch.tensor(chosen[idx])[:, None]).squeeze(1)
    ratio = torch.exp(lp - torch.tensor(old_logp[idx], dtype=torch.float32))
    ad = torch.tensor(advn[idx], dtype=torch.float32)
    pmask = torch.tensor(pm[idx])
    pg = -torch.min(ratio * ad, ratio.clamp(1 - a.clip, 1 + a.clip) * ad)
    loss = (pg * pmask).sum()
    net.zero_grad(set_to_none=False)
    loss.backward()
    flat = torch.cat([(p.grad if p.grad is not None else torch.zeros_like(p)).reshape(-1) for p in params])
    G[gi] = flat.numpy().astype(np.float16)
    o = g["outcome"]
    meta["games"].append({"seed": g["seed"], "heart": int(bool(o.get("heart_kill"))), "floor": o.get("floor"),
                          "n": n, "np": int(pm[idx].sum()), "sumA": float(advn[idx][pm[idx]].sum()),
                          "sumA2": float((advn[idx][pm[idx]] ** 2).sum()), "v0": float(vals[k]),
                          "gnorm2": float((flat.double() ** 2).sum())})
    k += n
    if gi % 50 == 0:
        print(f"game {gi}/{len(games)} {time.time() - t1:.0f}s", flush=True)
G.flush()
meta["ret0"] = [float(ret[sum(len(x["steps"]) for x in games[:i])]) for i in range(0)]
meta["value_ev"] = float(1 - np.var(ret - vals) / np.var(ret))
json.dump(meta, open(os.path.join(out, f"{tag}.meta.json"), "w"))
print(f"done {time.time() - t0:.0f}s", flush=True)
