#!/usr/bin/env python3
"""Silver AlphaZero-style loop with a factorized MLP tree prior: trainer (generation 1).

Design: /mnt/project-files/silver-az-mlp/PLAN.md (§2.1 model, §2.4 training, §2.5 monitors).
The model is the native `combat_policy_mlp_v1` prior (CombatValueNet::predictPolicyMlp):

    h1    = relu(Ws x_state + Wa x_action + C[aCardId + 1] + Wt x_target + b1)
    h2    = relu(W2 h1 + b2)
    logit = w3 . h2 + b3,   prior = softmax over the node's edges

x_state is the sparse 1,766-wide combat state block, x_action the 22 action features
(raw aCardId is dropped; the card enters through a 16-d embedding, C = E @ Wc), and
x_target the 9 slot features of the targeted monster (zero when the action targets
none). Inputs are divided by their per-column RMS on the training roots; the scales
and the embedding projection are folded into the exported weights. An auxiliary value
head on the state trunk (weight 0.1, not exported, not used in search) predicts
won * (53 + endHp) / 100 of the root's fight.

Data: `one_combat silversynthfeatures` rows of the §397 corpus and the §404 5x corpus
(action rows carry "tgt", the targeted slot). Seed folds as §397/§404: fold = seed % 5,
train 0-2, validation (early stopping) 3, test 4. Monitor 1 is cross-entropy and top-1
vs the 10k visit shares on test fold 4 of the original corpus (the §404 table: v1 GBM
55.3% / 1.230, v2-6x 61.2% / 1.144, encoder-6x 61.7% / 1.124). Every metric uses roots
with two or more actions.

usage:
  silver_az_mlp.py featurize ONE_COMBAT OUT_DIR TAG=CORPUS_DIR [TAG=CORPUS_DIR ...]
  silver_az_mlp.py pack      FEAT_DIR OUT.npz TAG=CORPUS_DIR [TAG=CORPUS_DIR ...]
  silver_az_mlp.py train     PACK.npz OUT_DIR [--h1 128 --h2 64 --epochs 40 --patience 4 --seed 0
                                               --wd 1e-2 --dropout 0.35 --lr-decay --no-test
                                               --init CKPT.pt --gbm-ref LIGHTGBM_MODEL.txt]

Training defaults are generation 1's (AdamW lr 5e-4, batch 1,024 roots, early stopping on
fold 3 with patience 4). The plan's recipe (wd 1e-4, no dropout) overfit; wd 1e-2 and
dropout 0.35 were picked on fold 3 (docs/experiments/evidence/silver_az_mlp_gen1_20261013).
  silver_az_mlp.py export    CKPT.pt OUT.txt NAMES.json
  silver_az_mlp.py parity    MODEL.txt FEATURE_PREFIX CPP_LOGITS.txt OUT.json
"""
import argparse
import concurrent.futures
import glob
import gzip
import json
import os
import subprocess
import sys
import time

import numpy as np

S, A, NCARD, NT, MON_OFF = 1766, 22, 372, 9, 1766 - 8 - 5 - 44 - 5 * 9   # MON_OFF checked against names
CARD_COL = 4                       # aCardId in the action block
TEST, VAL, TRAIN = 4, 3, (0, 1, 2)
REFERENCE = {"v1_gbm": {"top1": 0.553, "ce": 1.230}, "v2_6x": {"top1": 0.612, "ce": 1.144},
             "encoder_6x": {"top1": 0.617, "ce": 1.124}}


def corpus_args(items):
    out = []
    for item in items:
        tag, path = item.split("=", 1)
        out.append((tag, path))
    return out


def units(corpus_dir):
    """Finished generator units (a .done next to the .jsonl.gz), sorted."""
    paths = sorted(glob.glob(os.path.join(corpus_dir, "**", "*.jsonl.gz"), recursive=True))
    return [p for p in paths if os.path.exists(p[: -len(".jsonl.gz")] + ".done")]


def unit_prefix(out_dir, tag, path):
    return os.path.join(out_dir, f"{tag}-{os.path.basename(os.path.dirname(path))}-"
                                 f"{os.path.basename(path)[: -len('.jsonl.gz')]}")


def cmd_featurize(binary, out_dir, corpora):
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(p, unit_prefix(out_dir, tag, p)) for tag, d in corpus_args(corpora) for p in units(d)]

    def run(job):
        path, prefix = job
        if os.path.exists(prefix + ".summary.json"):
            return prefix, "kept"
        with gzip.open(path, "rb") as src:
            r = subprocess.run([binary, "silversynthfeatures", prefix], input=src.read(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise RuntimeError(f"{path}: rc {r.returncode}: {r.stderr.decode()[-500:]}")
        return prefix, "ok"

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        for i, (prefix, status) in enumerate(ex.map(run, jobs)):
            if i % 25 == 0:
                print(f"{i + 1}/{len(jobs)} {status} {prefix} {time.time() - t0:.0f}s", flush=True)
    print(f"featurized {len(jobs)} units in {time.time() - t0:.0f}s", flush=True)


def fight_values(corpus_dirs):
    """(variant, seed, fight) -> won * (53 + endHp) / 100 from the corpus fight rows."""
    vals = {}
    for _, d in corpus_dirs:
        for path in units(d):
            with gzip.open(path, "rt") as f:
                for line in f:
                    if '"kind":"fight"' not in line:
                        continue
                    r = json.loads(line)
                    vals[(r["variant"], r["seed"], r["fight"])] = (53.0 + r["endHp"]) / 100.0 if r["won"] else 0.0
    return vals


def cmd_pack(feat_dir, out_path, corpora):
    corpora = corpus_args(corpora)
    tags = [t for t, _ in corpora]
    values = fight_values(corpora)
    st_idx, st_val, st_ptr = [], [], [0]
    r_src, r_seed, r_fight, r_var, r_val, r_nedge = [], [], [], [], [], []
    e_act, e_tgt, e_vis = [], [], []
    missing_value = 0
    for tag, d in corpora:
        for path in units(d):
            prefix = unit_prefix(feat_dir, tag, path)
            nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
            ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
            idx = np.fromfile(prefix + ".idx", dtype=np.uint16)
            val = np.fromfile(prefix + ".val", dtype=np.float32)
            cur = None
            acts, tgts, vis = [], [], []

            def flush():
                nonlocal missing_value
                if cur is None or len(acts) < 2:
                    return
                m, row = cur
                sl = slice(ptr[row], ptr[row + 1])
                st_idx.append(idx[sl].astype(np.int16)); st_val.append(val[sl])
                st_ptr.append(st_ptr[-1] + int(nnz[row]))
                r_src.append(tags.index(tag)); r_seed.append(m["seed"]); r_fight.append(m["fight"])
                r_var.append(0 if m["variant"] == "natural" else 1)
                v = values.get((m["variant"], m["seed"], m["fight"]))
                if v is None:
                    missing_value += 1
                r_val.append(np.nan if v is None else v)
                r_nedge.append(len(acts))
                for a_row in acts:
                    a = np.zeros(A, np.float32)
                    s2 = slice(ptr[a_row], ptr[a_row + 1])
                    a[idx[s2].astype(np.int64) - S] = val[s2]
                    e_act.append(a)
                e_tgt.extend(tgts); e_vis.extend(vis)

            with open(prefix + ".meta.jsonl") as f:
                for i, line in enumerate(f):
                    if '"k":"state"' in line:
                        flush()
                        cur, acts, tgts, vis = (json.loads(line), i), [], [], []
                    elif '"k":"act"' in line:
                        if cur is None:
                            continue
                        m = json.loads(line)
                        acts.append(i); tgts.append(m["tgt"]); vis.append(m["visits"])
                    elif '"k":"leaf"' in line:
                        flush()
                        cur = None
            flush()
            cur = None
        print(f"packed {tag}: roots so far {len(r_seed)}", flush=True)
    np.savez(out_path, st_idx=np.concatenate(st_idx), st_val=np.concatenate(st_val),
             st_ptr=np.array(st_ptr, np.int64), r_src=np.array(r_src, np.int8),
             r_seed=np.array(r_seed, np.int64), r_fight=np.array(r_fight, np.int32),
             r_var=np.array(r_var, np.int8), r_val=np.array(r_val, np.float32),
             r_nedge=np.array(r_nedge, np.int32), e_act=np.stack(e_act), e_tgt=np.array(e_tgt, np.int8),
             e_vis=np.array(e_vis, np.float32), tags=np.array(tags))
    print(json.dumps({"roots": len(r_seed), "edges": len(e_tgt), "missingValue": missing_value,
                      "roots_by_source": {t: int(np.sum(np.array(r_src) == i)) for i, t in enumerate(tags)}}))


class Data:
    """Packed multi-action roots plus per-edge arrays; scaled inputs for training."""

    def __init__(self, path):
        z = np.load(path)
        for k in z.files:
            setattr(self, k, z[k])
        self.tags = [str(t) for t in self.tags]
        self.n = len(self.r_seed)
        self.e_ptr = np.concatenate([[0], np.cumsum(self.r_nedge, dtype=np.int64)])
        self.e_root = np.repeat(np.arange(self.n), self.r_nedge)
        self.fold = (self.r_seed % 5).astype(np.int8)
        vsum = np.add.reduceat(self.e_vis, self.e_ptr[:-1])
        self.share = (self.e_vis / np.maximum(vsum[self.e_root], 1)).astype(np.float32)
        st_idx = self.st_idx.astype(np.int64)
        st_root = np.repeat(np.arange(self.n), np.diff(self.st_ptr))
        # Target slot features gathered from the state block (no target -> zeros).
        mon = np.zeros((self.n, 5 * NT), np.float32)
        sel = (st_idx >= MON_OFF) & (st_idx < MON_OFF + 5 * NT)
        mon[st_root[sel], st_idx[sel] - MON_OFF] = self.st_val[sel]
        tgt_vals = np.zeros((len(self.e_tgt), NT), np.float32)
        has = np.flatnonzero(self.e_tgt >= 0)
        cols = self.e_tgt[has].astype(np.int64)[:, None] * NT + np.arange(NT)[None, :]
        tgt_vals[has] = mon[self.e_root[has][:, None], cols]
        del mon
        self.e_tvals = tgt_vals
        self.st_idx64 = st_idx

    def roots(self, folds, source=None):
        m = np.isin(self.fold, folds)
        if source is not None:
            m &= self.r_src == self.tags.index(source)
        return np.flatnonzero(m)

    def fit_scales(self, train_roots):
        tr = np.zeros(self.n, bool); tr[train_roots] = True
        st_root = np.repeat(np.arange(self.n), np.diff(self.st_ptr))
        m = tr[st_root]
        sq = np.bincount(self.st_idx64[m], weights=self.st_val[m].astype(np.float64) ** 2, minlength=S)
        sq /= tr.sum()
        s_scale = np.where(sq > 0, 1.0 / np.sqrt(np.maximum(sq, 1e-12)), 0.0).astype(np.float32)
        em = tr[self.e_root]
        a_sq = (self.e_act[em].astype(np.float64) ** 2).mean(0)
        a_scale = np.where(a_sq > 0, 1.0 / np.sqrt(np.maximum(a_sq, 1e-12)), 0.0).astype(np.float32)
        a_scale[CARD_COL] = 0.0            # the card id enters through the embedding only
        tm = em & (self.e_tgt >= 0)
        t_sq = (self.e_tvals[tm].astype(np.float64) ** 2).mean(0)
        t_scale = np.where(t_sq > 0, 1.0 / np.sqrt(np.maximum(t_sq, 1e-12)), 0.0).astype(np.float32)
        return s_scale, a_scale, t_scale

    def batch(self, roots, scales, torch):
        s_scale, a_scale, t_scale = scales
        roots = np.asarray(roots)
        lens = np.diff(self.st_ptr)[roots]
        starts = self.st_ptr[roots]
        pos = np.repeat(starts - np.concatenate([[0], np.cumsum(lens)[:-1]]), lens) + np.arange(lens.sum())
        idx = self.st_idx64[pos]
        val = self.st_val[pos] * s_scale[idx]
        offs = np.concatenate([[0], np.cumsum(lens)[:-1]])
        ne = self.r_nedge[roots]
        epos = np.repeat(self.e_ptr[roots] - np.concatenate([[0], np.cumsum(ne)[:-1]]), ne) + np.arange(ne.sum())
        eroot = np.repeat(np.arange(len(roots)), ne)
        card = self.e_act[epos, CARD_COL].astype(np.int64) + 1     # aCardId -1 (no card) -> row 0
        card[(card < 0) | (card >= NCARD)] = 0
        T = torch.from_numpy
        return dict(idx=T(idx), off=T(offs.astype(np.int64)), w=T(val.astype(np.float32)),
                    act=T(self.e_act[epos] * a_scale), card=T(card), tv=T(self.e_tvals[epos] * t_scale),
                    eroot=T(eroot.astype(np.int64)), share=T(self.share[epos]),
                    val=T(np.nan_to_num(self.r_val[roots], nan=0.0)), has_val=T(~np.isnan(self.r_val[roots])),
                    nroot=len(roots), epos=epos)


def make_net(torch, h1, h2, dropout=0.0):
    nn = torch.nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.state = nn.EmbeddingBag(S, h1, mode="sum")
            self.act = nn.Linear(A, h1)                    # its bias is b1
            self.card = nn.Embedding(NCARD, 16)
            self.cardproj = nn.Linear(16, h1, bias=False)
            self.tgt = nn.Linear(NT, h1, bias=False)
            self.l2 = nn.Linear(h1, h2)
            self.out = nn.Linear(h2, 1)
            self.v1 = nn.Linear(h1, 32)
            self.v2 = nn.Linear(32, 1)
            self.drop = nn.Dropout(dropout)               # training only; identity in export
            # He-normal over the first layer's full input width; zero biases; output x0.1.
            fan1 = S + A + 16 + NT
            for w in (self.state.weight, self.act.weight, self.cardproj.weight, self.tgt.weight):
                nn.init.normal_(w, 0.0, (2.0 / fan1) ** 0.5)
            nn.init.normal_(self.card.weight, 0.0, 1.0)
            for layer in (self.l2, self.out, self.v1, self.v2):
                nn.init.kaiming_normal_(layer.weight, nonlinearity="relu")
            with torch.no_grad():
                self.out.weight.mul_(0.1)
            for b in (self.act.bias, self.l2.bias, self.out.bias, self.v1.bias, self.v2.bias):
                nn.init.zeros_(b)

        def forward(self, b):
            hs = self.state(b["idx"], b["off"], per_sample_weights=b["w"])
            pre = hs[b["eroot"]] + self.act(b["act"]) + self.cardproj(self.card(b["card"])) + self.tgt(b["tv"])
            logit = self.out(torch.relu(self.l2(self.drop(torch.relu(pre))))).squeeze(1)
            value = self.v2(torch.relu(self.v1(torch.relu(hs + self.act.bias)))).squeeze(1)
            return logit, value

    return Net()


def group_log_softmax(torch, logit, eroot, nroot):
    m = torch.full((nroot,), -1e30).index_reduce_(0, eroot, logit.detach(), "amax", include_self=True)
    ex = torch.exp(logit - m[eroot])
    z = torch.zeros(nroot).index_add_(0, eroot, ex)
    return logit - m[eroot] - torch.log(z[eroot])


def root_metrics(logp, share, e_ptr):
    """CE and top-1 vs the label's argmax (first maximum, as the §404 tables)."""
    ce = -np.add.reduceat(share * logp, e_ptr[:-1])
    top = 0
    for i in range(len(e_ptr) - 1):
        sl = slice(e_ptr[i], e_ptr[i + 1])
        top += int(np.argmax(logp[sl]) == np.argmax(share[sl]))
    return {"roots": len(e_ptr) - 1, "ce": float(ce.mean()), "top1": top / (len(e_ptr) - 1)}


def evaluate(torch, net, data, roots, scales, bs=4096):
    net.eval()
    logps, shares, vals, vpred, lens = [], [], [], [], []
    with torch.no_grad():
        for i in range(0, len(roots), bs):
            b = data.batch(roots[i:i + bs], scales, torch)
            logit, v = net(b)
            logps.append(group_log_softmax(torch, logit, b["eroot"], b["nroot"]).numpy())
            shares.append(b["share"].numpy()); lens.append(data.r_nedge[roots[i:i + bs]])
            hv = b["has_val"].numpy()
            vals.append(b["val"].numpy()[hv]); vpred.append(v.numpy()[hv])
    net.train()
    lens = np.concatenate(lens)
    res = root_metrics(np.concatenate(logps), np.concatenate(shares),
                       np.concatenate([[0], np.cumsum(lens)]))
    vals, vpred = np.concatenate(vals), np.concatenate(vpred)
    res["value_mse"] = float(np.mean((vals - vpred) ** 2))
    res["value_var"] = float(np.var(vals))
    return res


def gbm_reference(model_path, data, roots):
    """v1 GBM (LightGBM text) on the same roots: sigmoid(margin) normalized, as in the game."""
    import lightgbm as lgb
    import scipy.sparse as sp
    booster = lgb.Booster(model_file=model_path)
    lens = np.diff(data.st_ptr)[roots]
    ne = data.r_nedge[roots]
    rows, cols, vals = [], [], []
    epos = np.concatenate([np.arange(data.e_ptr[r], data.e_ptr[r + 1]) for r in roots])
    erow = np.repeat(np.arange(len(roots)), ne)
    ecount = 0
    for k, r in enumerate(roots):
        sl = slice(data.st_ptr[r], data.st_ptr[r + 1])
        for j in range(ne[k]):
            rows.append(np.full(lens[k], ecount + j)); cols.append(data.st_idx64[sl]); vals.append(data.st_val[sl])
        ecount += ne[k]
    act = data.e_act[epos]
    ar, ac = np.nonzero(act)
    rows.append(ar); cols.append(ac + S); vals.append(act[ar, ac])
    X = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                      shape=(len(epos), S + A), dtype=np.float32)
    margin = booster.predict(X, raw_score=True)
    p = 1 / (1 + np.exp(-margin))
    z = np.add.reduceat(p, np.concatenate([[0], np.cumsum(ne)[:-1]]))
    logp = np.log(p / z[erow])
    del erow
    return root_metrics(logp, data.share[epos], np.concatenate([[0], np.cumsum(ne)]))


def cmd_train(pack, out_dir, args):
    import torch
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    data = Data(pack)
    train = data.roots(TRAIN); val = data.roots((VAL,))
    test_orig = data.roots((TEST,), data.tags[0]); test_all = data.roots((TEST,))
    scales = data.fit_scales(train)
    print(f"loaded {data.n} roots in {time.time() - t0:.0f}s: train {len(train)} val {len(val)} "
          f"test(orig) {len(test_orig)} test(all) {len(test_all)}", flush=True)
    net = make_net(torch, args.h1, args.h2, args.dropout)
    if args.init:
        net.load_state_dict(torch.load(args.init)["state"])
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.wd)
    report = {"args": vars(args), "pack": os.path.abspath(pack), "tags": data.tags,
              "roots": {"train": len(train), "val": len(val), "test_orig": len(test_orig),
                        "test_all": len(test_all)}, "reference_fold4_orig": REFERENCE, "epochs": []}
    if args.gbm_ref and not args.no_test:
        report["gbm_ref_fold4_orig"] = gbm_reference(args.gbm_ref, data, test_orig)
        print("v1 GBM fold-4 (orig):", report["gbm_ref_fold4_orig"], flush=True)
    report["init_fold4_orig"] = evaluate(torch, net, data, test_orig, scales)
    best, best_state, since = np.inf, None, 0
    for ep in range(args.epochs):
        te = time.time()
        perm = rng.permutation(train)
        tot = 0.0
        for i in range(0, len(perm), args.batch):
            b = data.batch(perm[i:i + args.batch], scales, torch)
            logit, v = net(b)
            logp = group_log_softmax(torch, logit, b["eroot"], b["nroot"])
            ce = -(b["share"] * logp).sum() / b["nroot"]
            hv = b["has_val"]
            mse = ((v[hv] - b["val"][hv]) ** 2).mean() if hv.any() else torch.zeros(())
            loss = ce + args.value_weight * mse
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(ce.detach()) * b["nroot"]
        vm = evaluate(torch, net, data, val, scales)
        row = {"epoch": ep, "train_ce": tot / len(perm), "val": vm, "seconds": time.time() - te}
        report["epochs"].append(row)
        print(json.dumps(row), flush=True)
        if vm["ce"] < best - 1e-4:
            best, since = vm["ce"], 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
            report["best_epoch"] = ep
        else:
            since += 1
            if since >= args.patience:
                break
            if args.lr_decay:              # halve the learning rate when validation stalls
                for g in opt.param_groups:
                    g["lr"] *= 0.5
    net.load_state_dict(best_state)
    report["val_best"] = evaluate(torch, net, data, val, scales)
    if not args.no_test:
        report["test_fold4_orig"] = evaluate(torch, net, data, test_orig, scales)
        report["test_fold4_all"] = evaluate(torch, net, data, test_all, scales)
        report["kill_rule_ce_vs_v1"] = {"mlp_ce": report["test_fold4_orig"]["ce"],
                                        "v1_ce": REFERENCE["v1_gbm"]["ce"],
                                        "pass": report["test_fold4_orig"]["ce"] <= REFERENCE["v1_gbm"]["ce"]}
    report["params"] = int(sum(p.numel() for p in net.parameters()))
    report["seconds"] = time.time() - t0
    torch.save({"state": best_state, "h1": args.h1, "h2": args.h2,
                "scales": [s.tolist() for s in scales]}, os.path.join(out_dir, "model.pt"))
    json.dump(report, open(os.path.join(out_dir, "train.json"), "w"), indent=1)
    print(json.dumps({k: report[k] for k in ("val_best", "test_fold4_orig", "test_fold4_all", "kill_rule_ce_vs_v1")
                      if k in report}, indent=1))


def exported_weights(ckpt):
    """Native layout (float64 numpy): folded scales, card table = embedding @ projection."""
    st = {k: v.double().numpy() for k, v in ckpt["state"].items()}
    s_scale, a_scale, t_scale = (np.array(s, np.float64) for s in ckpt["scales"])
    return {
        "state_w": st["state.weight"] * s_scale[:, None],             # S x H1
        "action_w": st["act.weight"].T * a_scale[:, None],             # A x H1
        "card": st["card.weight"] @ st["cardproj.weight"].T,           # NCARD x H1
        "target_w": st["tgt.weight"].T * t_scale[:, None],             # NT x H1
        "b1": st["act.bias"], "w2": st["l2.weight"], "b2": st["l2.bias"],
        "w3": st["out.weight"][0], "b3": st["out.bias"],
    }


def cmd_export(ckpt_path, out_path, names_path):
    import torch
    ckpt = torch.load(ckpt_path)
    names = json.load(open(names_path))
    assert len(names) == S + A and names[MON_OFF] == "m0Id" and names[S + CARD_COL] == "aCardId", "layout"
    W = exported_weights(ckpt)
    with open(out_path, "w") as f:
        f.write(f"combat_policy_mlp_v1\nh1 {ckpt['h1']}\nh2 {ckpt['h2']}\nnstate {S}\nnaction {A}\n"
                f"ncard {NCARD}\nntarget {NT}\n")
        for n in names:
            f.write(f"feat {n}\n")
        for key in ("state_w", "action_w", "card", "target_w", "b1", "w2", "b2", "w3", "b3"):
            f.write(key + "\n" + " ".join(f"{x:.9g}" for x in np.asarray(W[key], np.float32).ravel()) + "\n")
    print(f"wrote {out_path}")


def load_exported(path):
    with open(path) as f:
        tok = f.read().split()
    assert tok[0] == "combat_policy_mlp_v1"
    h1, h2 = int(tok[2]), int(tok[4])
    i = 13 + 2 * (S + A)
    shapes = {"state_w": (S, h1), "action_w": (A, h1), "card": (NCARD, h1), "target_w": (NT, h1),
              "b1": (h1,), "w2": (h2, h1), "b2": (h2,), "w3": (h2,), "b3": (1,)}
    W = {}
    for key, shape in shapes.items():
        assert tok[i] == key, (tok[i], key)
        n = int(np.prod(shape))
        W[key] = np.array(tok[i + 1:i + 1 + n], np.float64).reshape(shape)
        i += 1 + n
    return W


def reference_logits(W, state, actions, targets):
    """float64 reference of CombatValueNet::predictPolicyMlp for one root."""
    base = W["b1"] + state @ W["state_w"]
    out = []
    for a, t in zip(actions, targets):
        h = base + a @ W["action_w"]
        card = int(a[CARD_COL]) + 1
        h = h + W["card"][card if 0 <= card < NCARD else 0]
        if t >= 0:
            h = h + state[MON_OFF + t * NT: MON_OFF + (t + 1) * NT] @ W["target_w"]
        h2 = np.maximum(W["w2"] @ np.maximum(h, 0) + W["b2"], 0)
        out.append(float(W["w3"] @ h2 + W["b3"][0]))
    return out


def cmd_parity(model_path, prefix, cpp_path, out_path):
    W = load_exported(model_path)
    nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
    ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
    idx = np.fromfile(prefix + ".idx", dtype=np.uint16).astype(np.int64)
    val = np.fromfile(prefix + ".val", dtype=np.float32).astype(np.float64)
    ref, roots, cur = [], 0, None

    def flush():
        nonlocal roots
        if cur is not None and cur[1]:
            ref.extend(reference_logits(W, cur[0], cur[1], cur[2])); roots += 1

    with open(prefix + ".meta.jsonl") as f:
        for r, line in enumerate(f):
            sl = slice(ptr[r], ptr[r + 1])
            if '"k":"state"' in line:
                flush()
                s = np.zeros(S); s[idx[sl]] = val[sl]
                cur = (s, [], [])
            elif '"k":"act"' in line and cur is not None:
                a = np.zeros(A); a[idx[sl] - S] = val[sl]
                cur[1].append(a); cur[2].append(json.loads(line)["tgt"])
            elif '"k":"leaf"' in line:
                flush(); cur = None
    flush()
    cpp = np.loadtxt(cpp_path)
    ref = np.array(ref)
    assert len(cpp) == len(ref), (len(cpp), len(ref))
    diff = np.abs(cpp - ref)
    res = {"roots": roots, "edges": len(ref), "max_abs_diff": float(diff.max()),
           "mean_abs_diff": float(diff.mean()), "logit_abs_max": float(np.abs(ref).max()),
           "pass": bool(diff.max() < 1e-3)}
    json.dump(res, open(out_path, "w"), indent=1)
    print(json.dumps(res))
    if not res["pass"]:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("featurize"); f.add_argument("binary"); f.add_argument("out"); f.add_argument("corpora", nargs="+")
    k = sub.add_parser("pack"); k.add_argument("feat"); k.add_argument("out"); k.add_argument("corpora", nargs="+")
    t = sub.add_parser("train"); t.add_argument("pack"); t.add_argument("out")
    t.add_argument("--h1", type=int, default=128); t.add_argument("--h2", type=int, default=64)
    t.add_argument("--epochs", type=int, default=40); t.add_argument("--patience", type=int, default=4)
    t.add_argument("--batch", type=int, default=1024); t.add_argument("--lr", type=float, default=5e-4)
    t.add_argument("--wd", type=float, default=1e-2); t.add_argument("--value-weight", type=float, default=0.1)
    t.add_argument("--seed", type=int, default=0); t.add_argument("--init"); t.add_argument("--gbm-ref")
    t.add_argument("--dropout", type=float, default=0.35); t.add_argument("--lr-decay", action="store_true")
    t.add_argument("--no-test", action="store_true", help="validation only (hyperparameter sweeps)")
    e = sub.add_parser("export"); e.add_argument("ckpt"); e.add_argument("out"); e.add_argument("names")
    q = sub.add_parser("parity"); q.add_argument("model"); q.add_argument("prefix"); q.add_argument("cpp")
    q.add_argument("out")
    a = p.parse_args()
    if a.cmd == "featurize":
        cmd_featurize(a.binary, a.out, a.corpora)
    elif a.cmd == "pack":
        cmd_pack(a.feat, a.out, a.corpora)
    elif a.cmd == "train":
        cmd_train(a.pack, a.out, a)
    elif a.cmd == "export":
        cmd_export(a.ckpt, a.out, a.names)
    elif a.cmd == "parity":
        cmd_parity(a.model, a.prefix, a.cpp, a.out)


if __name__ == "__main__":
    main()
