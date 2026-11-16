#!/usr/bin/env python3
"""Calibration check of the per-role offline metric on factory batch 1 (PLAN.md, Messung 1-2).

usage: python3 calib.py PACK.npz OUT.json NAME=CKPT [NAME=CKPT ...]
Validation split (T1 hash, split 1) of the factory pack, grouped by r_kind (root / tree / playout) x room
(all / playout rooms). g7f_E = the recorded prior; each NAME=CKPT is a train.py model.pt.
"""
import json, sys, os
import numpy as np

sys.path.insert(0, "/home/user/sts_ai/tools/rollout_prior")
import train as T  # noqa: E402

KINDS = {0: "root", 1: "tree", 2: "playout"}


def groups(P, roots):
    kind = P.r_kind[roots]
    out = {}
    for k, name in KINDS.items():
        m = kind == k
        out[name] = m
        out[name + "/playout_rooms"] = m & P.playout[roots]
    return out


def summarize(P, roots, sums):
    res = {}
    for g, m in groups(P, roots).items():
        n = int(m.sum())
        if not n:
            continue
        r = {"rows": n, "ce_visits": float(sums["ce_visits"][m].mean()),
             "unvisited_pick": float(sums["unvisited_pick"][m].mean())}
        for name in ("mean", "backed"):
            k = sums[f"regret_{name}_n"][m]
            r[f"q_regret_{name}"] = float(sums[f"regret_{name}"][m][k].mean()) if k.any() else None
            # per-row values for paired bootstrap against g7f_E
        res[g] = r
    return res


def main(pack, out, *models):
    import torch
    torch.set_num_threads(4)
    P = T.Pack(pack)
    val = P.rows("val")
    epos = np.concatenate([np.arange(P.e_ptr[r], P.e_ptr[r + 1]) for r in val])
    res = {"pack": os.path.abspath(pack), "val_rows": int(len(val)), "models": {}}
    base = T.root_logp_metrics(P, val, np.log(np.maximum(P.e_prior[epos].astype(np.float64), 1e-30)))
    res["models"]["g7f_E"] = summarize(P, val, base)
    print("g7f_E", json.dumps(res["models"]["g7f_E"]), flush=True)
    per_row = {"g7f_E": base["regret_backed"]}
    for spec in models:
        name, ck = spec.split("=", 1)
        c = torch.load(ck, map_location="cpu", weights_only=False)
        a = type("A", (), dict(c["args"]))()
        net = T.make_net(torch, a)
        net.load_state_dict(c["state"])
        scales = tuple(np.array(x, np.float32) for x in c["scales"])
        q = P.e_qb
        _, q01 = T.completed_q_targets(P, q, 1.0)
        lp = T.predict_logp(torch, net, P, val, scales, torch.device("cpu"), P.share, q01)
        s = T.root_logp_metrics(P, val, lp.astype(np.float64))
        res["models"][name] = summarize(P, val, s)
        per_row[name] = s["regret_backed"]
        print(name, json.dumps(res["models"][name]), flush=True)
    # paired difference model - g7f_E per group, seed bootstrap over runs
    rng = np.random.default_rng(20261116)
    seeds = P.r_seed[val]
    useed, inv = np.unique(seeds, return_inverse=True)
    ok = base["regret_backed_n"]
    res["paired"] = {}
    for name in per_row:
        if name == "g7f_E":
            continue
        d = per_row[name] - per_row["g7f_E"]
        res["paired"][name] = {}
        for g, m in groups(P, val).items():
            mm = m & ok
            if not mm.any():
                continue
            sd = np.bincount(inv[mm], d[mm], len(useed))
            sn = np.bincount(inv[mm], None, len(useed))
            bs = []
            for _ in range(1000):
                i = rng.integers(0, len(useed), len(useed))
                bs.append(sd[i].sum() / max(sn[i].sum(), 1))
            res["paired"][name][g] = {"d": float(sd.sum() / sn.sum()), "ci95": [float(np.quantile(bs, .025)),
                                                                            float(np.quantile(bs, .975))]}
        print(name, "- g7f_E", json.dumps(res["paired"][name]), flush=True)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
