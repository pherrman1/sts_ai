#!/usr/bin/env python3
"""Learned budget per decision on budget-ladder data (docs/experiments/evidence/budget_ladder_roots_20261112).

usage: budget_ladder.py DATA_DIR OUT_DIR [--init CKPT] [--no-net] [--epochs N] [--device cpu|cuda] [--workers N]
       budget_ladder.py --selftest

DATA_DIR is tensorize.py output of silverazgen rows with STS_AZGEN_BUDGET_LADDER (ladder_edge.npy, ladder_cpu.npy,
meta.json "ladderBudgets"). Budgets B = {0 (the root prior's top action), ladder budgets}.

Per usable root (multi-edge, root prior, every ladder pick matched, every scored edge with a finite max-backed Q):
  loss_b = max over visited edges of Q_ref - Q_ref(pick_b), Q_ref = the played 16k tree's max-backed Q (qb.npy);
  cpu_b  = the ladder search's thread CPU seconds (0 for b = 0).
Models, cross-fitted over 5 folds by run (fold = train.split_of(seed) % 5): M0 uniform (per-budget constants); M1
gradient-boosted trees on search_gain.py's root statistics; M2 the CombatNet trunk (init --init) with a head on
[CLS, statistics] predicting loss_b (Huber, scaled) and log cpu_b (MSE) for every b > 0 (loss only for b = 0).
Predicted losses are made non-increasing in the budget (cumulative minimum); predicted CPU is exp(log-CPU prediction)
times Duan's smearing factor from the training rows, so it estimates mean CPU.
Policy: b*(x) = argmin_b loss_hat_b + lam * cpu_hat_b, lam by bisection so that the mean predicted CPU equals the
target (predictions only, no realized outcome). Targets: the mean CPU of uniform 2k / 4k / 8k.
Contrast per root: the policy's realized loss minus the uniform frontier at the policy's realized mean CPU, i.e. the
same mix of the two lower-hull uniform budgets around that CPU for every root. Run-clustered bootstrap (10,000,
seed 20261112), CI level 1 - 0.05 / 3. Decision (PREREG): GAIN if M2's CI upper < 0 at some target, else
NOT_SHOWN. Writes OUT_DIR/result.json.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FOLDS = 5
TARGET_BUDGETS = (2000, 4000, 8000)
LEVEL = 1 - 0.05 / len(TARGET_BUDGETS)


def ladder_labels(A):
    """rows, loss (n x B), cpu (n x B), summary features (search_gain.FEATS), drop counts, budgets."""
    from search_gain import labels as gain_labels
    a = A.a
    budgets = [0] + list(A.meta["ladderBudgets"])
    rows, _, _, X, dropped = gain_labels(A)
    off = np.asarray(a["act_off"])
    prior = np.asarray(a["prior"])
    Q = np.asarray(a["qb"] if "qb" in a else a["q"])
    le, lc = np.asarray(a["ladder_edge"]), np.asarray(a["ladder_cpu"])
    L = len(budgets) - 1
    keep, loss, cpu = [], [], []
    dropped.update({"ladder_unmatched": 0, "ladder_pick_unvisited": 0})
    for i, r in enumerate(rows):
        s, e = off[r], off[r + 1]
        q = Q[s:e]
        picks = le[r, :L]
        if (picks < 0).any():
            dropped["ladder_unmatched"] += 1
            continue
        pt = int(np.nanargmax(prior[s:e]))
        sel = np.r_[pt, picks]
        if np.isnan(q[sel]).any():
            dropped["ladder_pick_unvisited"] += 1
            continue
        best = np.nanmax(q)
        keep.append(i)
        loss.append(best - q[sel])
        cpu.append(np.r_[0.0, lc[r, :L]])
    keep = np.asarray(keep, np.int64)
    return (rows[keep], np.asarray(loss, np.float64), np.asarray(cpu, np.float64), X[keep], dropped, budgets)


def lower_hull(c, l):
    """Indices of the lower convex hull of points (c, l), sorted by c."""
    o = np.argsort(c)
    h = []
    for i in o:
        while len(h) >= 2:
            a, b = h[-2], h[-1]
            if (l[b] - l[a]) * (c[i] - c[a]) >= (l[i] - l[a]) * (c[b] - c[a]):
                h.pop()
            else:
                break
        h.append(i)
    return h


def frontier_mix(cbar, ucpu, uloss):
    """(lo, hi, w): the hull budgets around mean CPU cbar and the weight of hi so the mix's mean CPU is cbar."""
    h = lower_hull(ucpu, uloss)
    if cbar <= ucpu[h[0]]:
        return h[0], h[0], 0.0
    if cbar >= ucpu[h[-1]]:
        return h[-1], h[-1], 0.0
    for a, b in zip(h, h[1:]):
        if ucpu[a] <= cbar <= ucpu[b]:
            return a, b, (cbar - ucpu[a]) / (ucpu[b] - ucpu[a])
    raise AssertionError


def choose(lhat, chat, target, iters=60):
    """Per-row argmin of lhat + lam * chat with lam set so mean chosen chat = target (bisection on log lam)."""
    def pick(lam):
        return np.argmin(lhat + lam * chat, 1)
    lo, hi = -12.0, 12.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        b = pick(np.exp(mid))
        if chat[np.arange(len(b)), b].mean() > target:
            lo = mid
        else:
            hi = mid
    return pick(np.exp(hi))


def contrast(choice, loss, cpu, runs, ucpu, uloss, rng, reps=10000):
    n = len(choice)
    pl, pc = loss[np.arange(n), choice], cpu[np.arange(n), choice]
    cbar = pc.mean()
    lo, hi, w = frontier_mix(cbar, ucpu, uloss)
    d = pl - ((1 - w) * loss[:, lo] + w * loss[:, hi])
    ur, inv = np.unique(runs, return_inverse=True)
    s = np.bincount(inv, d)
    k = np.bincount(inv)
    boots = np.empty(reps)
    for t in range(reps):
        m = rng.integers(0, len(ur), len(ur))
        boots[t] = s[m].sum() / k[m].sum()
    a = (1 - LEVEL) / 2
    return {"cpu": float(cbar), "loss": float(pl.mean()), "frontier": [int(lo), int(hi), float(w)],
            "delta": float(d.mean()), "ci": [float(np.quantile(boots, a)), float(np.quantile(boots, 1 - a))],
            "delta_per_run": float(d.mean() * n / len(ur)),
            "mix": [float(x) for x in np.bincount(choice, minlength=loss.shape[1]) / n]}


def fit_m1(X, loss, cpu, tr, te):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from search_gain import FEATS
    cat = [FEATS.index("encounter"), FEATS.index("room"), FEATS.index("act")]
    B = loss.shape[1]
    lh, ch = np.zeros((len(te), B)), np.zeros((len(te), B))
    for b in range(B):
        lh[:, b] = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, categorical_features=cat,
                                                 random_state=0).fit(X[tr], loss[tr, b]).predict(X[te])
        if b > 0:
            y = np.log(cpu[tr, b] + 1e-4)
            m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, categorical_features=cat,
                                              random_state=0).fit(X[tr], y)
            ch[:, b] = np.exp(m.predict(X[te])) * smear(y, m.predict(X[tr]))
    return monotone(lh), ch


def smear(y, yhat):
    """Duan's smearing factor: E[cpu] = exp(log-cpu prediction) * mean(exp(training residual))."""
    return float(np.mean(np.exp(y - yhat)))


def monotone(lh):
    """More simulations never lose in expectation: the predicted loss is made non-increasing in the budget."""
    return np.minimum.accumulate(lh, axis=1)


def fit_m2(A, rows, X, loss, cpu, tr, te, args):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import model as M
    from search_gain import featurize
    from train import bucket_batches
    B = loss.shape[1]
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
    Fx = featurize(X, mu, sd, 0)
    caps = A.meta["caps"]
    base = M.CombatNet(d=128, layers=4, g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                       a_len=caps["A_LEN"])
    if args.init:
        base.load_state_dict(torch.load(args.init, map_location="cpu"), strict=False)
    holder = {}
    base.norm.register_forward_hook(lambda m, i, o: holder.__setitem__("cls", o[:, 0]))
    head = nn.Sequential(nn.Linear(128 + Fx.shape[1], 128), nn.GELU(), nn.Linear(128, 128), nn.GELU(),
                         nn.Linear(128, 2 * B))
    dev = args.device
    base.to(dev)
    head.to(dev)
    lscale = float(np.percentile(np.abs(loss[tr]), 90)) or 1.0
    lt = torch.from_numpy((loss / lscale).astype(np.float32))
    ct = torch.from_numpy(np.log(cpu + 1e-4).astype(np.float32))
    opt = torch.optim.AdamW([{"params": base.parameters(), "lr": args.lr}, {"params": head.parameters(), "lr": 1e-3}],
                            weight_decay=0.01)
    steps = max(1, int(args.epochs * len(tr) / args.batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[args.lr, 1e-3], total_steps=steps, pct_start=0.05)
    amp = dev.startswith("cuda")
    rng = np.random.default_rng(args.seed)
    ncards = np.diff(np.asarray(A.a["card_off"]))[rows]

    def fwd(sel):
        b = {k: v.to(dev) for k, v in M.collate(A, rows[sel]).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            base(b)
            out = head(torch.cat([holder["cls"].float(), torch.from_numpy(Fx[sel]).to(dev)], -1))
        return out.float()

    step = 0
    while step < steps:
        for bt in bucket_batches(tr, ncards, args.batch, rng):
            if step >= steps:
                break
            sel = np.sort(bt)
            out = fwd(sel)
            l_loss = F.smooth_l1_loss(out[:, :B], lt[sel].to(dev))
            c_loss = F.mse_loss(out[:, B + 1:], ct[sel, 1:].to(dev))
            loss_t = l_loss + 0.5 * c_loss
            opt.zero_grad()
            loss_t.backward()
            torch.nn.utils.clip_grad_norm_(list(base.parameters()) + list(head.parameters()), 1.0)
            opt.step()
            sched.step()
            step += 1
    base.eval()
    head.eval()

    def predict(idx_rows):
        out_all = np.zeros((len(idx_rows), 2 * B))
        order = np.argsort(rows[idx_rows], kind="stable")
        with torch.no_grad():
            for s in range(0, len(idx_rows), 512):
                idx = order[s:s + 512]
                out_all[idx] = fwd(idx_rows[idx]).cpu().numpy()
        return out_all

    sm = tr if len(tr) <= 20000 else np.sort(rng.choice(tr, 20000, replace=False))
    o_tr = predict(sm)
    out = predict(te)
    lh, ch = out[:, :B] * lscale, np.zeros((len(te), B))
    for b in range(1, B):
        ch[:, b] = np.exp(out[:, B + b]) * smear(np.log(cpu[sm, b] + 1e-4), o_tr[:, B + b])
    return monotone(lh), ch


def analyze(A, args):
    from train import split_of
    rows, loss, cpu, X, dropped, budgets = ladder_labels(A)
    seeds = np.asarray(A.a["seed"])[rows]
    fold = (split_of(seeds) % FOLDS).astype(int)
    if args.smoke_folds:   # pipeline smoke on one run only: folds by root (never for the PREREG analysis)
        fold = np.arange(len(rows)) % FOLDS
    rng = np.random.default_rng(20261112)
    ucpu, uloss = cpu.mean(0), loss.mean(0)
    res = {"roots": int(len(rows)), "runs": int(len(np.unique(seeds))), "dropped": dropped, "budgets": budgets,
           "uniform": {str(b): {"loss": float(uloss[i]), "cpu": float(ucpu[i])} for i, b in enumerate(budgets)},
           "hull": [budgets[i] for i in lower_hull(ucpu, uloss)], "level": LEVEL}
    models = {"M1": fit_m1} if args.no_net else {"M1": fit_m1, "M2": None}
    for name in models:
        lh, ch = np.zeros_like(loss), np.zeros_like(cpu)
        t0 = time.time()
        for f in range(FOLDS):
            tr, te = np.nonzero(fold != f)[0], np.nonzero(fold == f)[0]
            if name == "M1":
                lh[te], ch[te] = fit_m1(X, loss, cpu, tr, te)
            else:
                lh[te], ch[te] = fit_m2(A, rows, X, loss, cpu, tr, te, args)
        res[name] = {"fit_sec": round(time.time() - t0, 1), "targets": {}}
        for tb in TARGET_BUDGETS:
            target = ucpu[budgets.index(tb)]
            choice = choose(lh, ch, target)
            res[name]["targets"][str(tb)] = contrast(choice, loss, cpu, seeds, ucpu, uloss, rng)
        # oracle: realized loss and cpu, same lambda search (upper bound)
    res["oracle"] = {str(tb): contrast(choose(loss, cpu, ucpu[budgets.index(tb)]), loss, cpu, seeds, ucpu, uloss, rng,
                                       reps=1000) for tb in TARGET_BUDGETS}
    key = "M2" if "M2" in res else "M1"
    gain = [tb for tb, r in res[key]["targets"].items() if r["ci"][1] < 0]
    res["decision"] = {"model": key, "GAIN_at": gain, "verdict": "GAIN" if gain else "NOT_SHOWN"}
    return res


def selftest():
    c = np.array([0, 1, 2, 4.]); l = np.array([10, 5, 4, 3.9])
    assert lower_hull(c, l) == [0, 1, 2, 3] or lower_hull(c, l) == [0, 1, 3]
    lo, hi, w = frontier_mix(1.5, c, l)
    assert (lo, hi) == (1, 2) and abs(w - 0.5) < 1e-12
    rng = np.random.default_rng(0)
    n = 4000
    loss = np.c_[rng.exponential(3, n), rng.exponential(1, n), np.zeros(n)]
    cpu = np.c_[np.zeros(n), np.full(n, 1.0), np.full(n, 2.0)]
    runs = np.arange(n) // 20
    ch = choose(loss, cpu, 1.0)
    assert abs(cpu[np.arange(n), ch].mean() - 1.0) < 0.05
    r = contrast(ch, loss, cpu, runs, cpu.mean(0), loss.mean(0), rng, reps=200)
    assert r["delta"] < 0 and r["ci"][1] < 0          # an oracle-like policy beats the uniform mix
    r0 = contrast(np.full(n, 1), loss, cpu, runs, cpu.mean(0), loss.mean(0), rng, reps=200)
    assert abs(r0["delta"]) < 1e-9                       # a uniform arm on the hull has zero contrast
    print("selftest ok")
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--init", default="")
    ap.add_argument("--no-net", action="store_true")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=20261112)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke-folds", action="store_true", help="folds by root, for a one-run pipeline smoke only")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    import model as M
    os.makedirs(args.out, exist_ok=True)
    res = analyze(M.Arrays(args.data), args)
    json.dump(res, open(os.path.join(args.out, "result.json"), "w"), indent=1)
    print(json.dumps(res["decision"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
