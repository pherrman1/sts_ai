#!/usr/bin/env python3
"""Search-gain model (learned sim budget per decision, offline step 1, 2026-11-12).

usage: search_gain.py DATA_DIR OUT_DIR [--init CKPT] [--epochs N] [--batch B] [--lr LR] [--device cpu|cuda]
                      [--workers N] [--max-steps N] [--eval-rows N] [--seed S]

Question: does a model that sees a combat root's full state predict how much the 16k Gumbel search (G16 + mb4,
the D2 teacher) gains over playing the search prior's top action at that root? If it does, a budget model can
spend simulations where they matter; if even the full state cannot rank roots by search gain, a learned per-decision
budget has nothing to learn from the state.

Label per multi-edge Gumbel root with a root prior (tensorize.py arrays of D2):
  g    = Q(gumbelChoice) - Q(argmax prior), Q = max-backed Q (qb.npy; q.npy if absent), in Silver fight-score units;
  flip = gumbelChoice != argmax prior.
Rows whose prior top edge was never visited (NaN Q) are dropped and counted.

Models (all fit on the training runs, split_of >= 2, as train.py; scored on the validation runs, split_of == 1;
the gate holdout split_of == 0 is never read):
  B0  summary baseline: gradient-boosted trees (sklearn HistGradientBoosting; ridge if sklearn is missing) on root
      statistics a search already has for free: legal edges, prior entropy, top prior, top-2 prior gap, act, room
      class, HP share, encounter;
  NET the combat net's transformer trunk over the full state (cards, monsters, intents, statuses, queues, potions,
      relics), initialised from --init when given, with a gain head on [CLS, the B0 statistics] that predicts g
      (Huber) and flip (BCE).
Metrics on the validation runs: Pearson / Spearman of predicted vs realized g, flip AUC, and the allocation curve:
the share of the total realized gain inside the top x% of roots ranked by each model (x = 5, 10, 20, 30, 50),
next to the oracle (rank by realized g) and random (= x%). The oracle uses one noisy search per root, so it is an
upper bound that no model can reach. All roots count as equal cost (D2 does not record per-root CPU).

Writes OUT_DIR/result.json, OUT_DIR/gain_head.pt (NET) and OUT_DIR/log.jsonl. `--selftest` checks the label and
metric code on synthetic data.
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M  # noqa: E402
from train import split_of, bucket_batches  # noqa: E402

FEATS = ["edges", "prior_entropy", "prior_top", "prior_gap", "act", "room", "hp_share", "encounter"]
TOPS = (5, 10, 20, 30, 50)


def labels(A):
    """Per usable root: row index, g, flip and the summary features (FEATS order)."""
    a = A.a
    off = np.asarray(a["act_off"])
    prior, ch, multi = np.asarray(a["prior"]), np.asarray(a["gumbelChoice"]), np.asarray(a["multi"])
    Q = np.asarray(a["qb"] if "qb" in a else a["q"])
    hp, mhp = np.asarray(a["hp"], np.float64), np.asarray(a["maxHp"], np.float64)
    act, room, enc = np.asarray(a["act"]), np.asarray(a["elite_boss"]), np.asarray(a["encounter"])
    rows, g, flip, X = [], [], [], []
    dropped = {"no_choice": 0, "no_prior": 0, "prior_top_unvisited": 0}
    for r in np.nonzero(multi)[0]:
        c = int(ch[r])
        if c < 0:
            dropped["no_choice"] += 1
            continue
        s, e = off[r], off[r + 1]
        p = prior[s:e].astype(np.float64)
        if np.isnan(p).any() or p.sum() <= 0:
            dropped["no_prior"] += 1
            continue
        p = p / p.sum()
        pi = int(np.argmax(p))
        q = Q[s:e]
        if np.isnan(q[c]) or np.isnan(q[pi]):
            dropped["prior_top_unvisited"] += 1
            continue
        ps = np.sort(p)[::-1]
        rows.append(r)
        g.append(float(q[c] - q[pi]))
        flip.append(c != pi)
        X.append([e - s, float(-(p[p > 0] * np.log(p[p > 0])).sum()), ps[0], ps[0] - (ps[1] if len(ps) > 1 else 0),
                  act[r], room[r], hp[r] / max(1.0, mhp[r]), enc[r]])
    return (np.asarray(rows, np.int64), np.asarray(g, np.float64), np.asarray(flip, bool),
            np.asarray(X, np.float64).reshape(-1, len(FEATS)), dropped)


def rankdata(x):
    o = np.argsort(x, kind="stable")
    r = np.empty(len(x), np.float64)
    r[o] = np.arange(len(x))
    # average ties
    xs = x[o]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[o[i:j + 1]] = (i + j) / 2
        i = j + 1
    return r


def auc(score, y):
    y = np.asarray(y, bool)
    if y.all() or (~y).all():
        return None
    r = rankdata(np.asarray(score, np.float64))
    n1, n0 = y.sum(), (~y).sum()
    return float((r[y].sum() - n1 * (n1 - 1) / 2) / (n1 * n0))


def capture(pred, g, tops=TOPS):
    """Share of the total realized gain in the top x% of roots by `pred` (ties broken by index)."""
    tot = g.sum()
    o = np.argsort(-pred, kind="stable")
    cs = np.cumsum(g[o])
    return {str(t): float(cs[max(1, int(round(len(g) * t / 100))) - 1] / tot) for t in tops}


def metrics(pred, g, flip, pflip=None):
    out = {"n": int(len(g)), "pearson": float(np.corrcoef(pred, g)[0, 1]),
           "spearman": float(np.corrcoef(rankdata(pred), rankdata(g))[0, 1]), "capture": capture(pred, g),
           "flip_auc": auc(pred if pflip is None else pflip, flip)}
    return out


def fit_b0(X, g, flip, tr):
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        cat = [FEATS.index("encounter"), FEATS.index("room"), FEATS.index("act")]
        reg = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300, learning_rate=0.05,
                                            categorical_features=cat, random_state=0).fit(X[tr], g[tr])
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, categorical_features=cat,
                                             random_state=0).fit(X[tr], flip[tr])
        return "hgbt", (lambda Z: reg.predict(Z)), (lambda Z: clf.predict_proba(Z)[:, 1])
    except ImportError:
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        Z = np.c_[np.ones(len(tr)), (X[tr] - mu) / sd]
        w = np.linalg.solve(Z.T @ Z + 1.0 * np.eye(Z.shape[1]), Z.T @ g[tr])
        f = lambda Y: np.c_[np.ones(len(Y)), (Y - mu) / sd] @ w
        return "ridge", f, f


class GainNet(nn.Module):
    def __init__(self, base, nfeat, d):
        super().__init__()
        self.base = base
        self.cls = None
        base.norm.register_forward_hook(lambda m, i, o: setattr(self, "cls", o[:, 0]))
        self.head = nn.Sequential(nn.Linear(d + nfeat, d), nn.GELU(), nn.Linear(d, d), nn.GELU(), nn.Linear(d, 2))

    def forward(self, b, x):
        self.base(b)
        out = self.head(torch.cat([self.cls.float(), x], -1))
        return out[:, 0], out[:, 1]


def featurize(X, mu, sd, n_enc):
    """Standardized numeric features plus one-hot act / room (encounter stays in the trunk's monster tokens)."""
    num = (X[:, :4] - mu[:4]) / sd[:4]
    hp = (X[:, 6:7] - mu[6]) / sd[6]
    a = np.eye(5)[np.clip(X[:, 4].astype(int), 0, 4)]
    rm = np.eye(4)[np.clip(X[:, 5].astype(int), 0, 3)]
    return np.c_[num, hp, a, rm].astype(np.float32)


@torch.no_grad()
def predict_net(net, A, rows, F_, batch, device, amp):
    net.eval()
    order = np.argsort(rows, kind="stable")
    pg, pf = np.zeros(len(rows)), np.zeros(len(rows))
    for s in range(0, len(rows), batch):
        sel = order[s:s + batch]
        b = {k: v.to(device) for k, v in M.collate(A, rows[sel]).items()}
        # collate sorts its rows; sel is sorted by row already (order sorts rows), so features line up
        x = torch.from_numpy(F_[sel]).to(device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            g, f = net(b, x)
        pg[sel], pf[sel] = g.float().cpu().numpy(), torch.sigmoid(f.float()).cpu().numpy()
    net.train()
    return pg, pf


def selftest():
    rng = np.random.default_rng(0)
    g = rng.exponential(1, 1000)
    assert abs(capture(g, g)["50"] - 1) > 0 and capture(g, g)["50"] > 0.8
    assert abs(capture(rng.random(1000), g)["50"] - 0.5) < 0.1
    y = rng.random(1000) < 0.5
    assert abs(auc(y + rng.normal(0, 1e-3, 1000), y) - 1) < 1e-9
    assert abs(auc(rng.random(1000), y) - 0.5) < 0.06
    assert np.allclose(rankdata(np.array([3., 1, 1, 2])), [3, 0.5, 0.5, 2])
    print("selftest ok")
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--init", default="")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--head-lr", type=float, default=1e-3)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--eval-every", type=int, default=2000)
    ap.add_argument("--eval-rows", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=20261112)
    ap.add_argument("--no-net", action="store_true", help="baseline only")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    A = M.Arrays(args.data)
    t0 = time.time()
    rows, g, flip, X, dropped = labels(A)
    seeds = np.asarray(A.a["seed"])[rows]
    sp = split_of(seeds)
    tr, va = np.nonzero(sp >= 2)[0], np.nonzero(sp == 1)[0]
    res = {"rows": int(len(rows)), "dropped": dropped, "train_roots": int(len(tr)), "val_roots": int(len(va)),
           "train_runs": int(len(np.unique(seeds[tr]))), "val_runs": int(len(np.unique(seeds[va]))),
           "gate_rows_untouched": int((sp == 0).sum()),
           "label": {"mean_g": float(g.mean()), "flip_rate": float(flip.mean()),
                     "g_pct_50_90_99": [float(v) for v in np.percentile(g, [50, 90, 99])],
                     "neg_share": float((g < 0).mean()),
                     "by_room": {str(k): {"n": int((X[:, 5] == k).sum()), "mean_g": float(g[X[:, 5] == k].mean()),
                                          "flip": float(flip[X[:, 5] == k].mean())}
                                 for k in range(4) if (X[:, 5] == k).any()}},
           "label_sec": round(time.time() - t0, 1)}
    gv, fv = g[va], flip[va]
    res["oracle"] = {"capture": capture(gv, gv)}
    res["random"] = {"capture": {str(t): t / 100 for t in TOPS}}
    kind, f_reg, f_clf = fit_b0(X, g, flip, tr)
    res["B0"] = {"model": kind, **metrics(f_reg(X[va]), gv, fv, f_clf(X[va]))}
    # by room on the validation runs: does the ranking work inside a room class, not only across rooms?
    res["B0"]["within_room_spearman"] = {}
    print(json.dumps({"labels": res["label"], "B0": res["B0"]}), flush=True)
    if not args.no_net:
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        F_ = featurize(X, mu, sd, len(A.meta["encounters"]))
        caps = A.meta["caps"]
        base = M.CombatNet(d=args.d, layers=args.layers, g_len=caps["G_LEN"], m_num=caps["M_NUM"],
                           q_len=caps["Q_LEN"], a_len=caps["A_LEN"])
        if args.init:
            base.load_state_dict(torch.load(args.init, map_location="cpu"), strict=False)
        net = GainNet(base, F_.shape[1], args.d).to(args.device)
        gscale = float(np.percentile(np.abs(g[tr]), 90)) or 1.0
        opt = torch.optim.AdamW([{"params": net.base.parameters(), "lr": args.lr},
                                 {"params": net.head.parameters(), "lr": args.head_lr}], weight_decay=0.01)
        steps = int(args.epochs * len(tr) / args.batch)
        if args.max_steps:
            steps = min(steps, args.max_steps)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[args.lr, args.head_lr], total_steps=max(1, steps),
                                                    pct_start=0.05)
        amp = args.device.startswith("cuda")
        ncards = np.diff(np.asarray(A.a["card_off"]))[rows]
        ev = va if len(va) <= args.eval_rows else np.sort(rng.choice(va, args.eval_rows, replace=False))
        log = open(os.path.join(args.out, "log.jsonl"), "w")
        gt = torch.from_numpy((g / gscale).astype(np.float32))
        ft = torch.from_numpy(flip.astype(np.float32))

        class DS(torch.utils.data.Dataset):
            def __init__(self, batches):
                self.batches = batches

            def __len__(self):
                return len(self.batches)

            def __getitem__(self, i):
                sel = np.sort(self.batches[i])   # sorted local indices -> sorted rows, matching collate's order
                b = M.collate(A, rows[sel])
                b["_x"] = torch.from_numpy(F_[sel])
                b["_g"], b["_f"] = gt[sel], ft[sel]
                return b

        def stream():
            while True:
                dl = torch.utils.data.DataLoader(DS(bucket_batches(tr, ncards, args.batch, rng)), batch_size=None,
                                                 num_workers=args.workers, pin_memory=amp,
                                                 prefetch_factor=4 if args.workers else None)
                yield from dl

        it = stream()
        t1 = time.time()
        for step in range(steps):
            b = {k: v.to(args.device, non_blocking=True) for k, v in next(it).items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                pg, pf = net(b, b["_x"])
            loss = F.smooth_l1_loss(pg.float(), b["_g"]) + 0.5 * F.binary_cross_entropy_with_logits(pf.float(), b["_f"])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            if (step + 1) % args.eval_every == 0 or step + 1 == steps:
                p, q = predict_net(net, A, rows[ev], F_[ev], 512, args.device, amp)
                m = metrics(p, g[ev], flip[ev], q)
                rec = {"step": step + 1, "sec": round(time.time() - t1, 1), "loss": float(loss.detach()), **m}
                log.write(json.dumps(rec) + "\n")
                log.flush()
                print(json.dumps({k: rec[k] for k in ("step", "sec", "loss", "spearman", "flip_auc")}
                                 | {"cap10": m["capture"]["10"]}), flush=True)
        torch.save(net.state_dict(), os.path.join(args.out, "gain_net.pt"))
        p, q = predict_net(net, A, rows[va], F_[va], 512, args.device, amp)
        res["NET"] = {"init": args.init, "steps": steps, "gscale": gscale, "train_sec": round(time.time() - t1, 1),
                      **metrics(p * gscale, gv, fv, q)}
        np.save(os.path.join(args.out, "val_pred.npy"), np.c_[rows[va], gv, fv, p * gscale, q, f_reg(X[va])])
    # within-room Spearman for both models (ranking inside a room class)
    for k in range(4):
        m = X[va, 5] == k
        if m.sum() < 50:
            continue
        res["B0"]["within_room_spearman"][str(k)] = float(np.corrcoef(rankdata(f_reg(X[va][m])), rankdata(gv[m]))[0, 1])
        if "NET" in res:
            res["NET"].setdefault("within_room_spearman", {})[str(k)] = float(
                np.corrcoef(rankdata(p[m]), rankdata(gv[m]))[0, 1])
    json.dump(res, open(os.path.join(args.out, "result.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("B0", "NET", "oracle") if k in res}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
