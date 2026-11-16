#!/usr/bin/env python3
"""Train a g7f_E-shaped policy MLP on G16 + mb4 search targets (issue #1053: rollout prior on Gumbel targets).

The net is the gen-6/7 factorized MLP (`docs/experiments/evidence/silver_az_mlp_gen6_20261014/arch_dev.py`, the
recipe that produced g6_E and g7f_E: h1 128 / h2 64, card 16, encounter and monster-id / incoming-damage embeddings
16, dropout 0.15, AdamW lr 1e-3 cosine, wd 1e-2, batch 1,024, 25 epochs, value head weight 0.1). It exports to
`combat_policy_mlp_v2`, the format of g7f_E, so the native prior call costs the same.

Data: a `tools/rollout_prior/pack_d2.py` pack. Splits are T1's (`tools/combat_net/train.py::split_of`, hash of the
run seed): 0 = gate holdout (never read here), 1 = validation, 2..9 = training.

Policy targets (`--target`):
  visits        visit shares (g7f_E's target type; with sequential halving the finalists' shares are equal)
  cq:S          completed-Q policy softmax(log prior + S * q01) (ADR-0043 / Gumbel MuZero; unvisited edges get
                v_mix; q01 = min-max over visited edges), the prior being the recorded root prior (g7f_E)
  cq:paper      the same with S = (50 + max visits) * 1, the search's own sigma (close to the argmax at 16k)
  `--q-source mean|backed` picks the mean Q or the max-backed Q (D2 records both).

Auxiliary heads (training only, not exported; issue #1053 "measure first"):
  --aux-q W     per-edge head on the edge's last hidden layer: q01 of each visited edge (MSE)
  --aux-sh W    per-root head on the state trunk: (hp_next - hp) / 100, turns_left / 10, potions used, win (BCE),
                endHp / 100 (MSE terms on rows that have them)

Metrics (validation; every multi-edge root; also per group: playout rooms = boss rooms + Act-4 elites, and per
playout encounter): CE to the visit shares, top-1 vs the played Gumbel pick, `q_regret` under mean and backed Q as
T1 (best finalist Q minus the Q of the argmax; finalists = visits >= half the max; rows whose argmax edge has a Q),
and the share of rows whose argmax edge is unvisited. `--baseline` scores the recorded root prior (g7f_E) instead.

usage:
  train.py fit PACK.npz OUT_DIR [--target visits|cq:S|cq:paper] [--q-source backed] [--aux-q W] [--aux-sh W]
               [--rooms playout] [--init CKPT] [--epochs 25] [--device cuda] ...
  train.py baseline PACK.npz OUT.json         # g7f_E (recorded prior) on the same validation rows
  train.py export CKPT.pt OUT.txt NAMES.json  # combat_policy_mlp_v2 text (names: one_combat silversynthreplay names)
  train.py eval PACK.npz OUT.json --model V=runs/V/model.pt --model g7f_E=prior [--rows val|all] [--device cuda]
                                              # offline test; per kind (root / tree / playout_state) on factory packs
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import silver_az_mlp as M  # noqa: E402

ENC_MAX = MON_MAX = 128
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INTENT_COLS = [1668, 1677, 1686, 1695, 1704]


def split_of(seeds):
    """T1's split (tools/combat_net/train.py): 0 = gate holdout, 1 = validation, 2..9 = training."""
    return (seeds.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(2 ** 32) % np.uint64(10)


class Pack(M.Data):
    def __init__(self, path, extra=False):
        super().__init__(path)
        if extra:
            # --extra-pack: a silver_az_mlp.py pack (e.g. g7f_E's pack-g7f.npz). Every root is a training root (split 2);
            # it has no room / encounter / Q / auxiliary columns, so it never enters validation or the aux heads.
            nan = np.full(self.n, np.nan, np.float32)
            self.r_room = np.zeros(self.n, np.int8); self.r_act = np.zeros(self.n, np.int8)
            self.r_enc = np.zeros(self.n, np.int64); self.r_gpick = np.full(self.n, -1, np.int64)
            self.encounters = []
            for k in ("r_hp", "r_hp_next", "r_turns_left", "r_pot_used", "r_won", "r_endhp"):
                setattr(self, k, nan)
            self.e_q = self.e_qb = np.full(len(self.e_vis), np.nan, np.float32)
            self.e_prior = np.ones(len(self.e_vis), np.float32)
        self.split = np.full(self.n, 2, np.int8) if extra else split_of(self.r_seed).astype(np.int8)
        self.playout = (self.r_room == 2) | ((self.r_act == 4) & (self.r_room == 1))
        self.encounters = [str(e) for e in self.encounters]
        st_root = np.repeat(np.arange(self.n), np.diff(self.st_ptr))
        mon = np.zeros((self.n, 10), np.int64)
        for k, c in enumerate(ID_COLS + INTENT_COLS):
            m = self.st_idx64 == c
            mon[st_root[m], k] = np.rint(self.st_val[m]).astype(np.int64) + (1 if k < 5 else 0)
        self.mon = np.clip(mon, 0, MON_MAX - 1)
        enc = np.zeros(self.n, np.int64)
        m = self.st_idx64 == 1
        enc[st_root[m]] = np.rint(self.st_val[m]).astype(np.int64)
        self.enc = np.clip(enc, 0, ENC_MAX - 1)
        del st_root

    def rows(self, split, rooms="all"):
        m = (self.split >= 2) if split == "train" else (self.split == 1)
        if rooms == "playout":
            m &= self.playout
        return np.flatnonzero(m)


def completed_q_targets(P, q, scale):
    """Per edge: softmax(log prior + sigma * q01) per root (tools/combat_net/train.py::completed_q_policy, vectorized).
    Roots without a visited edge keep their visit shares."""
    ptr, root = P.e_ptr, P.e_root
    vis = P.e_vis.astype(np.float64)
    visited = ~np.isnan(q) & (vis > 0)
    qv = np.where(visited, q, 0.0).astype(np.float64)
    p = P.e_prior.astype(np.float64)
    psum = np.add.reduceat(p, ptr[:-1])
    p = np.where(psum[root] > 0, p, 1.0 / P.r_nedge[root])
    nvis = np.add.reduceat(visited.astype(np.int64), ptr[:-1])
    vw = np.add.reduceat(vis * visited, ptr[:-1])
    v_hat = np.add.reduceat(vis * qv, ptr[:-1]) / np.maximum(vw, 1)
    pv = np.add.reduceat(p * visited, ptr[:-1])
    total = np.add.reduceat(vis, ptr[:-1])
    pq = np.add.reduceat(p * qv * visited, ptr[:-1])
    v_mix = np.where(pv > 0, (v_hat + total / np.maximum(pv, 1e-300) * pq) / (1 + total), v_hat)
    qc = np.where(visited, qv, v_mix[root])
    lo = np.minimum.reduceat(np.where(visited, qv, np.inf), ptr[:-1])
    hi = np.maximum.reduceat(np.where(visited, qv, -np.inf), ptr[:-1])
    span = hi - lo
    q01 = np.where(span[root] > 0, np.clip((qc - lo[root]) / np.where(span > 0, span, 1)[root], 0, 1), 0.5)
    vmax = np.maximum.reduceat(vis, ptr[:-1])
    sigma = (50.0 + vmax)[root] if scale is None else scale
    z = np.log(np.maximum(p, 1e-12)) + sigma * q01
    z = z - np.maximum.reduceat(z, ptr[:-1])[root]
    ez = np.exp(z)
    out = ez / np.add.reduceat(ez, ptr[:-1])[root]
    keep = nvis[root] == 0
    out[keep] = P.share[keep]
    return out.astype(np.float32), np.where(visited, q01, np.nan).astype(np.float32)


def make_net(torch, a):
    nn = torch.nn
    S, A, NCARD, NT = M.S, M.A, M.NCARD, M.NT
    fan = S + A + 16 + NT

    class Net(nn.Module):
        """arch_dev.py's factorized 2-layer net (no tower / third layer / dot), plus optional training-only heads."""

        def __init__(s):
            super().__init__()
            h1, h2 = a.h1, a.h2
            s.state = nn.EmbeddingBag(S, h1, mode="sum")
            s.act = nn.Linear(A, h1)
            s.card = nn.Embedding(NCARD, 16)
            s.cardproj = nn.Linear(16, h1, bias=False)
            s.tgt = nn.Linear(NT, h1, bias=False)
            s.hidden = nn.ModuleList([nn.Linear(h1, h2)])
            s.out = nn.Linear(h2, 1)
            s.v1 = nn.Linear(h1, 32); s.v2 = nn.Linear(32, 1)
            s.drop = nn.Dropout(a.dropout)
            s.monid = nn.Embedding(MON_MAX, 16); s.monint = nn.Embedding(MON_MAX, 16)
            nn.init.normal_(s.monid.weight, 0.0, 1.0); nn.init.normal_(s.monint.weight, 0.0, 1.0)
            s.monproj = nn.Linear(32, h1, bias=False)
            nn.init.normal_(s.monproj.weight, 0.0, (2.0 / fan) ** 0.5)
            s.enc = nn.Embedding(ENC_MAX, 16); nn.init.normal_(s.enc.weight, 0.0, 1.0)
            s.encproj = nn.Linear(16, h1, bias=False)
            nn.init.normal_(s.encproj.weight, 0.0, (2.0 / fan) ** 0.5)
            nn.init.normal_(s.state.weight, 0.0, (2.0 / fan) ** 0.5)
            for w in (s.act.weight, s.cardproj.weight, s.tgt.weight):
                nn.init.normal_(w, 0.0, (2.0 / fan) ** 0.5)
            nn.init.normal_(s.card.weight, 0.0, 1.0)
            for l in list(s.hidden) + [s.out, s.v1, s.v2]:
                nn.init.kaiming_normal_(l.weight, nonlinearity="relu"); nn.init.zeros_(l.bias)
            with torch.no_grad():
                s.out.weight.mul_(0.1)
            nn.init.zeros_(s.act.bias)
            if a.aux_q > 0:
                s.qhead = nn.Linear(h2, 1)
            if a.aux_sh > 0:
                s.sh1 = nn.Linear(h1, 64); s.sh2 = nn.Linear(64, 5)

        def forward(s, b):
            hs = s.state(b["idx"], b["off"], per_sample_weights=b["w"])
            mid, mint = b["mon"][:, :5], b["mon"][:, 5:]
            present = (mid > 0).float().unsqueeze(2)
            hs = hs + s.monproj(torch.cat([s.monid(mid), s.monint(mint)], 2) * present).sum(1)
            hs = hs + s.encproj(s.enc(b["enc"]))
            vin = torch.relu(hs + s.act.bias)
            ea = s.act(b["act"]) + s.cardproj(s.card(b["card"])) + s.tgt(b["tv"])
            x = s.drop(torch.relu(hs[b["eroot"]] + ea))
            x = torch.relu(s.hidden[0](x))
            out = {"logit": s.out(x).squeeze(1), "value": s.v2(torch.relu(s.v1(vin))).squeeze(1)}
            if a.aux_q > 0:
                out["q01"] = torch.sigmoid(s.qhead(x).squeeze(1))
            if a.aux_sh > 0:
                out["sh"] = s.sh2(torch.relu(s.sh1(vin)))
            return out

    return Net()


def group_log_softmax(torch, logit, eroot, nroot):
    m = torch.full((nroot,), -1e30, device=logit.device).index_reduce_(0, eroot, logit.detach(), "amax",
                                                                     include_self=True)
    ex = torch.exp(logit - m[eroot])
    z = torch.zeros(nroot, device=logit.device).index_add_(0, eroot, ex)
    return logit - m[eroot] - torch.log(z[eroot])


def batch(torch, P, roots, scales, dev, target, q01):
    b = P.batch(roots, scales, torch)
    epos = b.pop("epos")
    roots = np.asarray(roots)
    b["mon"] = torch.from_numpy(P.mon[roots]); b["enc"] = torch.from_numpy(P.enc[roots])
    b["target"] = torch.from_numpy(target[epos])
    if q01 is not None:
        b["q01"] = torch.from_numpy(q01[epos])
    sh = np.stack([(P.r_hp_next[roots] - P.r_hp[roots]) / 100.0, P.r_turns_left[roots] / 10.0, P.r_pot_used[roots],
                   P.r_won[roots], P.r_endhp[roots] / 100.0], 1).astype(np.float32)
    b["sh"] = torch.from_numpy(sh)
    b = {k: (v.to(dev, non_blocking=True) if torch.is_tensor(v) else v) for k, v in b.items()}
    return b, epos


def root_logp_metrics(P, roots, logp_edges):
    """Metrics from per-edge log-probs (pack edge order of `roots`). Returns sums for aggregation by group."""
    roots = np.asarray(roots)
    ne = P.r_nedge[roots]
    ptr = np.concatenate([[0], np.cumsum(ne)])
    epos = np.concatenate([np.arange(P.e_ptr[r], P.e_ptr[r + 1]) for r in roots]) if len(roots) else np.zeros(0, int)
    share = P.share[epos]
    ce = -np.add.reduceat(share * logp_edges, ptr[:-1])
    # argmax per root (first maximum)
    eroot = np.repeat(np.arange(len(roots)), ne)
    mx = np.maximum.reduceat(logp_edges, ptr[:-1])
    is_max = logp_edges >= mx[eroot]
    local = np.arange(len(logp_edges)) - ptr[eroot]
    first = np.minimum.reduceat(np.where(is_max, local, np.iinfo(np.int64).max), ptr[:-1])
    out = {"rows": len(roots), "ce_visits": ce, "gpick_hit": (first == P.r_gpick[roots]) & (P.r_gpick[roots] >= 0),
           "gpick_n": P.r_gpick[roots] >= 0}
    vis = P.e_vis[epos]
    vmax = np.maximum.reduceat(vis, ptr[:-1])
    for name, q in (("mean", P.e_q[epos]), ("backed", P.e_qb[epos])):
        fin = (vis * 2 >= vmax[eroot]) & (vis > 0) & ~np.isnan(q)
        best = np.maximum.reduceat(np.where(fin, q, -np.inf), ptr[:-1])
        qpick = q[ptr[:-1] + first]
        ok = np.isfinite(best) & ~np.isnan(qpick)
        out[f"regret_{name}"] = np.where(ok, best - np.nan_to_num(qpick), 0.0)
        out[f"regret_{name}_n"] = ok
    out["unvisited_pick"] = vis[ptr[:-1] + first] == 0
    return out


def summarize(P, roots, sums):
    """Aggregate root_logp_metrics over all rows, playout rooms and playout encounters."""
    roots = np.asarray(roots)
    groups = {"all": np.ones(len(roots), bool), "playout": P.playout[roots]}
    enc = P.r_enc[roots]
    for e in np.unique(enc[P.playout[roots]]):
        groups["enc:" + P.encounters[e]] = P.playout[roots] & (enc == e)
    if hasattr(P, "r_kind"):
        # prior-factory packs (pack_factory.py): roots, tree nodes and playout states, each labelled by a Gumbel search
        for k, name in enumerate(("root", "tree", "playout_state")):
            mk = P.r_kind[roots] == k
            groups["kind:" + name] = mk
            groups["kind:" + name + "|playout_room"] = mk & P.playout[roots]
    res = {}
    for g, m in groups.items():
        n = int(m.sum())
        if n == 0:
            continue
        r = {"rows": n, "ce_visits": float(sums["ce_visits"][m].mean()),
             "top1_gpick": float(sums["gpick_hit"][m].sum() / max(sums["gpick_n"][m].sum(), 1)),
             "unvisited_pick": float(sums["unvisited_pick"][m].mean())}
        for name in ("mean", "backed"):
            k = sums[f"regret_{name}_n"][m]
            r[f"q_regret_{name}"] = float(sums[f"regret_{name}"][m][k].mean()) if k.any() else None
        res[g] = r
    return res


def predict_logp(torch, net, P, roots, scales, dev, target, q01, bs=8192):
    net.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(roots), bs):
            b, _ = batch(torch, P, roots[i:i + bs], scales, dev, target, q01)
            o = net(b)
            out.append(group_log_softmax(torch, o["logit"], b["eroot"], b["nroot"]).cpu().numpy())
    net.train()
    return np.concatenate(out)


def cmd_baseline(a):
    P = Pack(a.pack)
    val = P.rows("val")
    epos = np.concatenate([np.arange(P.e_ptr[r], P.e_ptr[r + 1]) for r in val])
    logp = np.log(np.maximum(P.e_prior[epos].astype(np.float64), 1e-30))
    res = {"pack": os.path.abspath(a.pack), "model": "recorded root prior (g7f_E)",
           "val": summarize(P, val, root_logp_metrics(P, val, logp))}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res["val"]["all"]), json.dumps(res["val"]["playout"]))


def cmd_fit(a):
    import torch
    torch.set_num_threads(a.threads); torch.manual_seed(a.seed)
    dev = torch.device(a.device)
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    P = Pack(a.pack)
    train, val = P.rows("train", a.rooms), P.rows("val")
    if a.max_train_roots:
        train = np.sort(rng.choice(train, min(a.max_train_roots, len(train)), replace=False))
    q = P.e_qb if a.q_source == "backed" else P.e_q
    if a.target == "visits":
        target = P.share
        _, q01 = completed_q_targets(P, q, 1.0)
    elif a.target.startswith("cq:"):
        s = a.target[3:]
        target, q01 = completed_q_targets(P, q, None if s == "paper" else float(s))
    else:
        raise SystemExit("--target must be visits, cq:S or cq:paper")
    # packs[0] = the main pack (validation, metrics, scales); packs[1] = --extra-pack (training rows only).
    packs, targets, q01s, rows = [P], [target], [q01], [train]
    if a.extra_pack:
        X = Pack(a.extra_pack, extra=True)
        _, xq01 = completed_q_targets(X, X.e_qb, 1.0)
        packs.append(X); targets.append(X.share); q01s.append(xq01); rows.append(X.rows("train"))
    if a.teacher:
        # gen-6 D/E distillation (arch_dev.py --teacher --alpha): target = (1 - alpha) * target + alpha * softmax(T)
        for i, Q in enumerate(packs):
            tl = np.load(os.path.join(a.teacher, f"logp_{i}.npy"))
            if len(tl) != len(Q.e_vis):
                raise SystemExit(f"teacher logp_{i}.npy has {len(tl)} edges, pack has {len(Q.e_vis)}")
            tp = np.exp(tl.astype(np.float64))
            targets[i] = np.where(np.isnan(tp), targets[i], (1 - a.alpha) * targets[i] + a.alpha * tp).astype(np.float32)
    init = torch.load(a.init, map_location="cpu", weights_only=False) if a.init else None
    scales = tuple(np.array(x, np.float32) for x in init["scales"]) if init else P.fit_scales(train)
    net = make_net(torch, a).to(dev)
    if init:
        missing, unexpected = net.load_state_dict(init["state"], strict=False)
        if unexpected or any(not k.startswith(("qhead", "sh1", "sh2")) for k in missing):
            raise SystemExit(f"--init mismatch: missing {missing} unexpected {unexpected}")
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    pid_all = np.concatenate([np.full(len(r), i, np.int8) for i, r in enumerate(rows)])
    root_all = np.concatenate(rows)
    steps_per_ep = (len(root_all) + a.batch - 1) // a.batch
    rep = {"args": vars(a), "pack": os.path.abspath(a.pack), "rows": {"train": len(train), "val": len(val)},
           "params": int(sum(x.numel() for x in net.parameters())), "epochs": []}
    if a.extra_pack:
        rep["rows"]["train_extra"] = len(rows[1])
    print(f"loaded in {time.time() - t0:.0f}s: train {len(root_all)} val {len(val)} params {rep['params']}", flush=True)
    step = 0
    for ep in range(a.epochs):
        te = time.time(); perm = rng.permutation(len(root_all)); tot = {"ce": 0.0, "q": 0.0, "sh": 0.0}
        for i in range(0, len(perm), a.batch):
            lr = a.lr * 0.5 * (1 + np.cos(np.pi * min(step / (a.epochs * steps_per_ep), 1.0)))
            for g in opt.param_groups:
                g["lr"] = lr
            chunk = perm[i:i + a.batch]
            nb = len(chunk); ce_sum = 0.0; v_sum = 0.0; v_n = 0; loss = 0.0
            for pi, Q in enumerate(packs):
                sub = np.sort(root_all[chunk[pid_all[chunk] == pi]])
                if not len(sub):
                    continue
                b, _ = batch(torch, Q, sub, scales, dev, targets[pi], q01s[pi])
                o = net(b)
                logp = group_log_softmax(torch, o["logit"], b["eroot"], b["nroot"])
                ce_sum = ce_sum - (b["target"] * logp).sum()
                hv = b["has_val"]
                v_sum = v_sum + ((o["value"][hv] - b["val"][hv]) ** 2).sum(); v_n += int(hv.sum())
                w = b["nroot"] / nb
                if a.aux_q > 0:
                    mq = ~torch.isnan(b["q01"])
                    if mq.any():
                        lq = ((o["q01"][mq] - b["q01"][mq]) ** 2).mean()
                        loss = loss + a.aux_q * w * lq
                        tot["q"] += float(lq.detach()) * b["nroot"]
                if a.aux_sh > 0:
                    y, pr = b["sh"], o["sh"]
                    ls = 0.0
                    for j in range(5):
                        mj = ~torch.isnan(y[:, j])
                        if not mj.any():
                            continue
                        if j == 3:
                            ls = ls + torch.nn.functional.binary_cross_entropy_with_logits(pr[mj, j], y[mj, j])
                        else:
                            ls = ls + ((pr[mj, j] - y[mj, j]) ** 2).mean()
                    loss = loss + a.aux_sh * w * ls
                    tot["sh"] += float(ls.detach()) * b["nroot"]
            ce = ce_sum / nb
            loss = loss + ce + (a.value_weight * v_sum / v_n if v_n else 0.0)
            opt.zero_grad(); loss.backward(); opt.step(); step += 1
            tot["ce"] += float(ce.detach()) * nb
        lp = predict_logp(torch, net, P, val, scales, dev, target, q01)
        vm = summarize(P, val, root_logp_metrics(P, val, lp))
        row = {"epoch": ep, "train": {k: v / len(perm) for k, v in tot.items()}, "val_all": vm["all"],
               "val_playout": vm["playout"], "seconds": round(time.time() - te, 1), "lr": lr}
        rep["epochs"].append(row)
        print(json.dumps(row), flush=True)
    # Final checkpoint (cosine schedule to zero, as the g6_E / g7f_E recipe; no early stopping).
    lp = predict_logp(torch, net, P, val, scales, dev, target, q01)
    rep["val_final"] = summarize(P, val, root_logp_metrics(P, val, lp))
    rep["seconds"] = round(time.time() - t0)
    state = {k: x.detach().cpu().clone() for k, x in net.state_dict().items()}
    torch.save({"state": state, "args": vars(a), "scales": [x.tolist() for x in scales]}, f"{a.out}/model.pt")
    if a.dump_logp:
        # Teacher output for --teacher: per-edge log-probs of every root, in pack edge order (logp_<pack index>.npy).
        for pi, Q in enumerate(packs):
            np.save(f"{a.out}/logp_{pi}.npy",
                    predict_logp(torch, net, Q, np.arange(Q.n), scales, dev, targets[pi], q01s[pi]).astype(np.float32))
    json.dump(rep, open(f"{a.out}/train.json", "w"), indent=1)
    print("RESULT", json.dumps({"all": rep["val_final"]["all"], "playout": rep["val_final"]["playout"]}), flush=True)


def cmd_eval(a):
    """Offline test: score trained nets (and the recorded root prior, g7f_E) on one pack's rows, per group.
    On a prior-factory pack the groups include kind:root / kind:tree / kind:playout_state (root prior, tree prior and
    playout policy states), each against its own Gumbel label search."""
    import torch
    dev = torch.device(a.device)
    P = Pack(a.pack)
    rows = P.rows("val") if a.rows == "val" else np.arange(P.n)
    if a.max_rows and len(rows) > a.max_rows:
        rows = np.sort(np.random.default_rng(0).choice(rows, a.max_rows, replace=False))
    res = {"pack": os.path.abspath(a.pack), "rows": a.rows, "n": int(len(rows)), "models": {}}
    if hasattr(P, "r_kind"):
        res["n_by_kind"] = {k: int((P.r_kind[rows] == i).sum()) for i, k in enumerate(("root", "tree", "playout_state"))}
    for spec in a.model:
        name, path = spec.split("=", 1)
        if path == "prior":
            epos = np.concatenate([np.arange(P.e_ptr[r], P.e_ptr[r + 1]) for r in rows])
            logp = np.log(np.maximum(P.e_prior[epos].astype(np.float64), 1e-30))
            src = "recorded root prior (g7f_E)"
        else:
            ck = torch.load(path, map_location="cpu", weights_only=False)
            net = make_net(torch, argparse.Namespace(**ck["args"])).to(dev)
            net.load_state_dict(ck["state"])
            scales = tuple(np.array(x, np.float32) for x in ck["scales"])
            logp = predict_logp(torch, net, P, rows, scales, dev, P.share, None).astype(np.float64)
            src = os.path.abspath(path)
        res["models"][name] = {"source": src, "groups": summarize(P, rows, root_logp_metrics(P, rows, logp))}
        g = res["models"][name]["groups"]
        print(name, json.dumps({k: {m: g[k].get(m) for m in ("rows", "q_regret_backed", "q_regret_mean", "top1_gpick")}
                                for k in g if not k.startswith("enc:")}), flush=True)
    json.dump(res, open(a.out, "w"), indent=1)


def cmd_export(a):
    import torch
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    args = argparse.Namespace(**ck["args"])
    st = {k: v.double().numpy() for k, v in ck["state"].items()}
    ss, as_, ts = (np.array(x, np.float64) for x in ck["scales"])
    W = {"state_w": st["state.weight"] * ss[:, None], "action_w": st["act.weight"].T * as_[:, None],
         "card": st["card.weight"] @ st["cardproj.weight"].T, "target_w": st["tgt.weight"].T * ts[:, None],
         "b1": st["act.bias"], "w2": st["hidden.0.weight"], "b2": st["hidden.0.bias"], "w3": st["out.weight"][0],
         "b3": st["out.bias"]}
    extra = [("enc", st["enc.weight"] @ st["encproj.weight"].T),
             ("mon_id", st["monid.weight"] @ st["monproj.weight"][:, :16].T),
             ("mon_dmg", st["monint.weight"] @ st["monproj.weight"][:, 16:].T)]
    names = json.load(open(a.names))
    with open(a.out, "w") as f:
        f.write(f"combat_policy_mlp_v2\nh1 {args.h1}\nh2 {args.h2}\nnstate {M.S}\nnaction {M.A}\nncard {M.NCARD}\n"
                f"ntarget {M.NT}\n")
        for n in names:
            f.write(f"feat {n}\n")
        for key in ("state_w", "action_w", "card", "target_w", "b1", "w2", "b2", "w3", "b3"):
            f.write(key + "\n" + " ".join(f"{x:.9g}" for x in np.asarray(W[key], np.float32).ravel()) + "\n")
        for key, tab in extra:
            f.write(f"{key} {tab.shape[0]}\n" + " ".join(f"{x:.9g}" for x in np.asarray(tab, np.float32).ravel())
                    + "\n")
    print(f"exported {a.out}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit"); f.add_argument("pack"); f.add_argument("out")
    f.add_argument("--target", default="visits"); f.add_argument("--q-source", default="backed", choices=["mean", "backed"])
    f.add_argument("--aux-q", type=float, default=0.0); f.add_argument("--aux-sh", type=float, default=0.0)
    f.add_argument("--rooms", default="all", choices=["all", "playout"]); f.add_argument("--init")
    f.add_argument("--h1", type=int, default=128); f.add_argument("--h2", type=int, default=64)
    f.add_argument("--epochs", type=int, default=25); f.add_argument("--batch", type=int, default=1024)
    f.add_argument("--lr", type=float, default=1e-3); f.add_argument("--wd", type=float, default=1e-2)
    f.add_argument("--dropout", type=float, default=0.15); f.add_argument("--value-weight", type=float, default=0.1)
    f.add_argument("--seed", type=int, default=0); f.add_argument("--threads", type=int, default=4)
    f.add_argument("--device", default="cpu"); f.add_argument("--max-train-roots", type=int, default=0)
    f.add_argument("--extra-pack", help="silver_az_mlp.py pack whose every root is added to training (V-prime)")
    f.add_argument("--teacher", help="dir with a --dump-logp teacher's logp_<i>.npy per pack (gen-6 D/E distillation)")
    f.add_argument("--alpha", type=float, default=0.5, help="teacher weight in the target (with --teacher)")
    f.add_argument("--dump-logp", action="store_true", help="save per-edge log-probs of every root of every pack")
    b = sub.add_parser("baseline"); b.add_argument("pack"); b.add_argument("out")
    e = sub.add_parser("export"); e.add_argument("ckpt"); e.add_argument("out"); e.add_argument("names")
    v = sub.add_parser("eval"); v.add_argument("pack"); v.add_argument("out")
    v.add_argument("--model", action="append", required=True, help="NAME=CKPT.pt, or NAME=prior (recorded g7f_E)")
    v.add_argument("--rows", default="val", choices=["val", "all"], help="T1 validation split, or every row")
    v.add_argument("--max-rows", type=int, default=0); v.add_argument("--device", default="cpu")
    a = p.parse_args()
    {"fit": cmd_fit, "baseline": cmd_baseline, "export": cmd_export, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    main()
