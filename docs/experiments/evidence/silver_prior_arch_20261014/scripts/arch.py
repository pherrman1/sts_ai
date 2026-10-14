#!/usr/bin/env python3
"""Silver prior architecture sweep (offline). Reuses tools/silver_az_mlp.py Data/metrics.
Generalized factorized net: optional state tower (per node), optional 3rd layer, card dim,
optional dot (two-tower) head; recipe knobs: lr, wd, dropout, batch, schedule, distillation."""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, "/home/user/sts_ai/tools")
import silver_az_mlp as M
import torch
nn = torch.nn
ENC_MAX = 128
ENC = None
MON = None   # per root: 5 slot ids and 5 intents (raw state columns), clipped to MON_MAX
MON_MAX = 128
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INTENT_COLS = [1668, 1677, 1686, 1695, 1704]


def monster_ids(data):
    out = np.zeros((data.n, 10), np.int64)          # 0 = empty slot / missing
    st_root = np.repeat(np.arange(data.n), np.diff(data.st_ptr))
    for k, c in enumerate(ID_COLS + INTENT_COLS):
        m = data.st_idx64 == c
        out[st_root[m], k] = np.rint(data.st_val[m]).astype(np.int64) + (1 if k < 5 else 0)
    return np.clip(out, 0, MON_MAX - 1)


def encounter_ids(data):
    """Raw `encounter` state feature (column 1) per root, clipped to the embedding table."""
    e = np.zeros(data.n, np.int64)
    st_root = np.repeat(np.arange(data.n), np.diff(data.st_ptr))
    m = data.st_idx64 == 1
    e[st_root[m]] = np.rint(data.st_val[m]).astype(np.int64)
    return np.clip(e, 0, ENC_MAX - 1)


def batch(data, roots, scales):
    b = data.batch(roots, scales, torch)
    if ENC is not None:
        b["enc"] = torch.from_numpy(ENC[np.asarray(roots)])
    if MON is not None:
        b["mon"] = torch.from_numpy(MON[np.asarray(roots)])
    return b


class Net(nn.Module):
    def __init__(s, a):
        super().__init__()
        s.a = a
        h1 = a.h1
        if a.tower:
            s.state = nn.EmbeddingBag(M.S, a.tower, mode="sum")
            s.tbias = nn.Parameter(torch.zeros(a.tower))
            s.tproj = nn.Linear(a.tower, h1, bias=False)
        else:
            s.state = nn.EmbeddingBag(M.S, h1, mode="sum")
        s.act = nn.Linear(M.A, h1)
        s.card = nn.Embedding(M.NCARD, a.card_dim)
        s.cardproj = nn.Linear(a.card_dim, h1, bias=False)
        s.tgt = nn.Linear(M.NT, h1, bias=False)
        dims = [h1] + [d for d in (a.h2, a.h3) if d]
        s.hidden = nn.ModuleList(nn.Linear(dims[i], dims[i + 1]) for i in range(len(dims) - 1))
        s.out = nn.Linear(dims[-1], 1)
        if a.dot:
            s.du = nn.Linear(h1, a.dot)          # from the node's state vector
            s.dv = nn.Linear(h1, a.dot, bias=False)  # from the edge's pre-activation minus state
            nn.init.zeros_(s.dv.weight)              # start as the plain net (first dot try diverged)
        vin = a.tower if a.tower else h1
        s.v1 = nn.Linear(vin, 32); s.v2 = nn.Linear(32, 1)
        s.drop = nn.Dropout(a.dropout)
        if getattr(a, "mon_emb", 0):
            s.monid = nn.Embedding(MON_MAX, a.mon_emb); s.monint = nn.Embedding(MON_MAX, a.mon_emb)
            nn.init.normal_(s.monid.weight, 0.0, 1.0); nn.init.normal_(s.monint.weight, 0.0, 1.0)
            s.monproj = nn.Linear(2 * a.mon_emb, a.tower or h1, bias=False)
            nn.init.normal_(s.monproj.weight, 0.0, (2.0 / (M.S + M.A + a.card_dim + M.NT)) ** 0.5)
        if getattr(a, "enc_emb", 0):
            s.enc = nn.Embedding(ENC_MAX, a.enc_emb); nn.init.normal_(s.enc.weight, 0.0, 1.0)
            s.encproj = nn.Linear(a.enc_emb, a.tower or h1, bias=False)
            nn.init.normal_(s.encproj.weight, 0.0, (2.0 / (M.S + M.A + a.card_dim + M.NT)) ** 0.5)
        fan1 = (a.tower and M.S) or (M.S + M.A + a.card_dim + M.NT)
        nn.init.normal_(s.state.weight, 0.0, (2.0 / (M.S + M.A + a.card_dim + M.NT)) ** 0.5)
        for w in (s.act.weight, s.cardproj.weight, s.tgt.weight):
            nn.init.normal_(w, 0.0, (2.0 / (M.S + M.A + a.card_dim + M.NT)) ** 0.5)
        nn.init.normal_(s.card.weight, 0.0, 1.0)
        for l in list(s.hidden) + [s.out, s.v1, s.v2]:
            nn.init.kaiming_normal_(l.weight, nonlinearity="relu"); nn.init.zeros_(l.bias)
        if a.tower:
            nn.init.normal_(s.state.weight, 0.0, (2.0 / 48) ** 0.5 * 0.5)
            nn.init.kaiming_normal_(s.tproj.weight, nonlinearity="relu")
        with torch.no_grad():
            s.out.weight.mul_(0.1)
        nn.init.zeros_(s.act.bias)

    def forward(s, b):
        hs = s.state(b["idx"], b["off"], per_sample_weights=b["w"])
        if getattr(s.a, "mon_emb", 0):
            mid, mint = b["mon"][:, :5], b["mon"][:, 5:]
            present = (mid > 0).float().unsqueeze(2)
            e = torch.cat([s.monid(mid), s.monint(mint)], 2) * present      # roots x 5 x 2D
            hs = hs + s.monproj(e).sum(1)
        if getattr(s.a, "enc_emb", 0):
            hs = hs + s.encproj(s.enc(b["enc"]))
        if s.a.tower:
            t = torch.relu(hs + s.tbias)
            vin = t
            hs = s.tproj(s.drop(t))
        else:
            vin = torch.relu(hs + s.act.bias)
        ea = s.act(b["act"]) + s.cardproj(s.card(b["card"])) + s.tgt(b["tv"])
        x = torch.relu(hs[b["eroot"]] + ea)
        x = s.drop(x)
        for i, l in enumerate(s.hidden):
            x = torch.relu(l(x))
            if i < len(s.hidden) - 1:
                x = s.drop(x)
        logit = s.out(x).squeeze(1)
        if s.a.dot:
            logit = logit + (s.du(hs)[b["eroot"]] * s.dv(ea)).sum(1)
        value = s.v2(torch.relu(s.v1(vin))).squeeze(1)
        return logit, value


def evaluate(net, data, roots, scales, bs=8192, want_logp=False):
    net.eval()
    logps, shares, lens = [], [], []
    with torch.no_grad():
        for i in range(0, len(roots), bs):
            b = batch(data, roots[i:i + bs], scales)
            logit, _ = net(b)
            logps.append(M.group_log_softmax(torch, logit, b["eroot"], b["nroot"]).numpy())
            shares.append(b["share"].numpy()); lens.append(data.r_nedge[roots[i:i + bs]])
    net.train()
    lens = np.concatenate(lens); lp = np.concatenate(logps)
    res = M.root_metrics(lp, np.concatenate(shares), np.concatenate([[0], np.cumsum(lens)]))
    return (res, lp) if want_logp else res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name"); p.add_argument("--pack", default="/root/arch/pack-g4.npz")
    p.add_argument("--h1", type=int, default=128); p.add_argument("--h2", type=int, default=64)
    p.add_argument("--h3", type=int, default=0); p.add_argument("--tower", type=int, default=0)
    p.add_argument("--card-dim", type=int, default=16); p.add_argument("--dot", type=int, default=0)
    p.add_argument("--enc-emb", type=int, default=0)
    p.add_argument("--mon-emb", type=int, default=0, help="embed monster id and intent per slot")
    p.add_argument("--epochs", type=int, default=40); p.add_argument("--patience", type=int, default=8)
    p.add_argument("--batch", type=int, default=1024); p.add_argument("--lr", type=float, default=5e-4)
    p.add_argument("--wd", type=float, default=1e-2); p.add_argument("--dropout", type=float, default=0.35)
    p.add_argument("--sched", default="halve", choices=["halve", "cosine"])
    p.add_argument("--value-weight", type=float, default=0.1); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--teacher", help="npy of teacher log-probs per edge (pack order)")
    p.add_argument("--alpha", type=float, default=0.5, help="weight of teacher in the target")
    p.add_argument("--threads", type=int, default=4); p.add_argument("--test", action="store_true")
    p.add_argument("--dump-logp", action="store_true", help="save per-edge log-probs for all roots")
    a = p.parse_args()
    torch.set_num_threads(a.threads); torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    out = f"/root/arch/runs/{a.name}"; os.makedirs(out, exist_ok=True)
    t0 = time.time()
    data = M.Data(a.pack)
    train = data.roots(M.TRAIN); val = data.roots((M.VAL,))
    scales = data.fit_scales(train)
    global ENC, MON
    if a.mon_emb:
        MON = monster_ids(data); print("monster ids", np.unique(MON[:, :5]).size, "intents", np.unique(MON[:, 5:]).size, flush=True)
    if a.enc_emb:
        ENC = encounter_ids(data); print("encounters", np.unique(ENC).size, "max", ENC.max(), flush=True)
    teacher = np.load(a.teacher) if a.teacher else None
    net = Net(a)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    steps_per_ep = (len(train) + a.batch - 1) // a.batch
    rep = {"args": vars(a), "params": int(sum(x.numel() for x in net.parameters())), "epochs": []}
    print(f"loaded in {time.time()-t0:.0f}s params {rep['params']}", flush=True)
    best, best_state, since, step = np.inf, None, 0, 0
    for ep in range(a.epochs):
        te = time.time(); perm = rng.permutation(train); tot = 0.0
        for i in range(0, len(perm), a.batch):
            if a.sched == "cosine":
                lr = a.lr * 0.5 * (1 + np.cos(np.pi * min(step / (a.epochs * steps_per_ep), 1.0)))
                for g in opt.param_groups: g["lr"] = lr
            b = batch(data, perm[i:i + a.batch], scales)
            logit, v = net(b)
            logp = M.group_log_softmax(torch, logit, b["eroot"], b["nroot"])
            tgt = b["share"]
            if teacher is not None:
                tgt = (1 - a.alpha) * tgt + a.alpha * torch.from_numpy(np.exp(teacher[b["epos"]]).astype(np.float32))
            ce = -(tgt * logp).sum() / b["nroot"]
            hv = b["has_val"]
            mse = ((v[hv] - b["val"][hv]) ** 2).mean() if hv.any() else torch.zeros(())
            loss = ce + a.value_weight * mse
            opt.zero_grad(); loss.backward(); opt.step(); step += 1
            tot += float(ce.detach()) * b["nroot"]
        vm = evaluate(net, data, val, scales)
        row = {"epoch": ep, "train_ce": tot / len(perm), "val": vm, "seconds": time.time() - te,
               "lr": opt.param_groups[0]["lr"]}
        rep["epochs"].append(row); print(json.dumps(row), flush=True)
        if vm["ce"] < best - 1e-4:
            best, since = vm["ce"], 0
            best_state = {k: x.clone() for k, x in net.state_dict().items()}; rep["best_epoch"] = ep
        else:
            since += 1
            if since >= a.patience: break
            if a.sched == "halve":
                for g in opt.param_groups: g["lr"] *= 0.5
    net.load_state_dict(best_state)
    rep["val_best"] = evaluate(net, data, val, scales)
    if a.test:
        rep["test_fold4_orig"] = evaluate(net, data, data.roots((M.TEST,), data.tags[0]), scales)
        rep["test_fold4_all"] = evaluate(net, data, data.roots((M.TEST,)), scales)
    if a.dump_logp:
        allr = np.arange(data.n)
        _, lp = evaluate(net, data, allr, scales, want_logp=True)
        np.save(f"{out}/logp.npy", lp.astype(np.float32))
    rep["seconds"] = time.time() - t0
    torch.save({"state": best_state, "args": vars(a), "scales": [x.tolist() for x in scales]}, f"{out}/model.pt")
    json.dump(rep, open(f"{out}/train.json", "w"), indent=1)
    print("RESULT", a.name, json.dumps(rep["val_best"]), flush=True)


if __name__ == "__main__":
    main()
