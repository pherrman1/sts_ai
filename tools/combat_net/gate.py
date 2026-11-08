#!/usr/bin/env python3
"""Offline gate of the combat net, stage 2 (PREREG: docs/experiments/evidence/combat_net_stage2_20261108/PREREG.md).

usage: gate.py MODEL_DIR D1_DATA_DIR OUT.json [--ref MODEL_DIR] [--device cpu|cuda] [--boot 10000]

MODEL_DIR holds model.pt and eval.json from train.py (its config gives the architecture). Reads the D1 gate holdout
(split 0, see train.split_of) for the checks and the D1 training split (2..9) for the G2 baseline; never reads split 1
or another data set's rows.

  G1  policy cross-entropy to the Gumbel teacher's target (the root's visit shares) on multi-edge holdout roots with a
      root prior on every kept edge: net minus the g7f_E root prior (renormalized over the kept edges, floored at
      1e-12 as in searchGumbelRoot). Pass: run-clustered 95% CI hi < 0.
  G2  value NLL of the 21-class end-HP label: net minus the baseline, the empirical class distribution per
      (encounter name, HP decile) of the D1 training split, decile = min(9, floor(10 * hp / maxHp)) at the root, +1
      Laplace over the 21 classes; an unseen cell falls back to the encounter's distribution, an unseen encounter to
      the global one (same +1). Pass: run-clustered 95% CI hi < 0.
  G3  sanity, not gated: death-class reliability (10 bins, rows, mean predicted, observed) and ECE.

Descriptive: top-1 agreement with the Gumbel pick (`gumbelChoice`) for the net, the prior argmax and, with --ref, a
reference net (e.g. the D0-only ablation), each paired against the net with run-clustered CIs; the same by room.
Bootstrap: 10,000 resamples of runs, seed 20261108.
"""

import argparse
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M  # noqa: E402
from train import split_of  # noqa: E402


def load_net(model_dir, caps, device):
    cfg = json.load(open(os.path.join(model_dir, "eval.json")))["config"]
    net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=caps["G_LEN"], m_num=caps["M_NUM"],
                      q_len=caps["Q_LEN"], a_len=caps["A_LEN"], aux=not cfg["no_aux"], value=not cfg["no_value"])
    net.load_state_dict(torch.load(os.path.join(model_dir, "model.pt"), map_location=device))
    return net.to(device).eval()


@torch.no_grad()
def forward_all(net, A, idx, device, batch=512):
    """Per row: log-softmax over its kept edges (list of arrays) and value log-probs (21)."""
    logp, vlogp = [], []
    for s in range(0, len(idx), batch):
        part = np.sort(idx[s:s + batch])
        b = {k: v.to(device) for k, v in M.collate(A, part).items()}
        logits, vlog, _ = net(b)
        lp = torch.log_softmax(logits, -1).cpu().numpy()
        n = b["act_mask"].sum(-1).cpu().numpy()
        logp += [lp[i, :n[i]] for i in range(len(part))]
        vlogp.append(torch.log_softmax(vlog, -1).cpu().numpy())
    return logp, np.concatenate(vlogp)


def cluster_ci(diff, clusters, boot, seed, level=0.95):
    """Mean of `diff` with a run-clustered bootstrap CI."""
    uniq, inv = np.unique(clusters, return_inverse=True)
    s = np.bincount(inv, weights=diff)
    c = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(uniq), np.full(len(uniq), 1.0 / len(uniq)), size=boot)
    means = (w @ s) / (w @ c)
    a = (1 - level) / 2
    return {"mean": float(s.sum() / c.sum()), "ci": [float(np.quantile(means, a)), float(np.quantile(means, 1 - a))],
            "rows": int(len(diff)), "runs": int(len(uniq))}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--ref", default="")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--boot", type=int, default=10000)
    args = ap.parse_args(argv)
    A = M.Arrays(args.data)
    a = A.a
    caps = A.meta["caps"]
    names = A.meta["encounters"]
    seeds = np.asarray(a["seed"])
    split = split_of(seeds)
    hold = np.nonzero(split == 0)[0]
    train = np.nonzero(split >= 2)[0]
    ao = np.asarray(a["act_off"])
    policy, prior = np.asarray(a["policy"]), np.asarray(a["prior"])
    gumbel = np.asarray(a["gumbelChoice"])
    multi = np.asarray(a["multi"]) > 0
    room = np.asarray(a["elite_boss"])
    out = {"model": os.path.abspath(args.model), "data": os.path.abspath(args.data), "holdoutRows": int(len(hold)),
           "holdoutRuns": int(len(np.unique(seeds[hold])))}

    net = load_net(args.model, caps, args.device)
    logp, vlogp = forward_all(net, A, hold, args.device)
    ref = None
    if args.ref:
        ref, _ = forward_all(load_net(args.ref, caps, args.device), A, hold, args.device)

    # G1 and the top-1 description
    ce_d, rows, top = [], [], {"net": [], "prior": [], "ref": []}
    for k, r in enumerate(hold):
        if not multi[r]:
            continue
        t = policy[ao[r]:ao[r + 1]]
        p = prior[ao[r]:ao[r + 1]]
        if np.isnan(p).any() or gumbel[r] < 0:
            continue
        p = np.maximum(p / max(p.sum(), 1e-12), 1e-12)
        ce_d.append(float(-(t * logp[k]).sum() + (t * np.log(p)).sum()))
        rows.append(r)
        top["net"].append(float(np.argmax(logp[k]) == gumbel[r]))
        top["prior"].append(float(np.argmax(p) == gumbel[r]))
        if ref is not None:
            top["ref"].append(float(np.argmax(ref[k]) == gumbel[r]))
    rows = np.asarray(rows, dtype=np.int64)
    if len(rows) == 0:
        out["G1"] = {"pass": False, "note": "no eligible holdout roots"}
    else:
        g1 = cluster_ci(np.asarray(ce_d), seeds[rows], args.boot, 20261108)
        out["G1"] = {"policyCE_net_minus_prior": g1, "pass": g1["ci"][1] < 0}
        desc = {"top1_net": float(np.mean(top["net"])), "top1_prior": float(np.mean(top["prior"])),
                "net_minus_prior": cluster_ci(np.asarray(top["net"]) - np.asarray(top["prior"]), seeds[rows],
                                              args.boot, 20261108)}
        if ref is not None:
            desc["top1_ref"] = float(np.mean(top["ref"]))
            desc["net_minus_ref"] = cluster_ci(np.asarray(top["net"]) - np.asarray(top["ref"]), seeds[rows],
                                               args.boot, 20261108)
        desc["by_room"] = {}
        for code, nm in enumerate(("monster", "elite", "boss", "other")):
            sel = room[rows] == code
            if sel.sum():
                desc["by_room"][nm] = {"rows": int(sel.sum()), "top1_net": float(np.mean(np.asarray(top["net"])[sel])),
                                       "top1_prior": float(np.mean(np.asarray(top["prior"])[sel]))}
        out["top1"] = desc

    # G2 baseline from the training split
    won, end = np.asarray(a["won"]), np.asarray(a["endFrac"])
    vc = M.value_class(torch.from_numpy(won.astype(np.int64)), torch.from_numpy(np.array(end))).numpy()
    hp, mx = np.asarray(a["hp"]).astype(float), np.maximum(1, np.asarray(a["maxHp"]).astype(float))
    dec = np.minimum(9, np.floor(10 * hp / mx)).astype(int)
    enc = np.asarray(a["encounter"])
    K = M.VALUE_BINS + 1
    cell, encd, glob = {}, {}, np.ones(K)
    for r in train:
        key = (names[enc[r]], dec[r])
        cell.setdefault(key, np.ones(K))[vc[r]] += 1
        encd.setdefault(names[enc[r]], np.ones(K))[vc[r]] += 1
        glob[vc[r]] += 1
    fallback = {"cell": 0, "encounter": 0, "global": 0}
    base_nll = np.empty(len(hold))
    for k, r in enumerate(hold):
        key = (names[enc[r]], dec[r])
        if key in cell:
            d = cell[key]; fallback["cell"] += 1
        elif names[enc[r]] in encd:
            d = encd[names[enc[r]]]; fallback["encounter"] += 1
        else:
            d = glob; fallback["global"] += 1
        base_nll[k] = -np.log(d[vc[r]] / d.sum())
    net_nll = -vlogp[np.arange(len(hold)), vc[hold]]
    g2 = cluster_ci(net_nll - base_nll, seeds[hold], args.boot, 20261108)
    out["G2"] = {"valueNLL_net_minus_baseline": g2, "net": float(net_nll.mean()), "baseline": float(base_nll.mean()),
                 "baselineCells": len(cell), "fallback": fallback, "pass": g2["ci"][1] < 0}

    # G3 sanity
    pd = np.exp(vlogp[:, 0])
    died = (won[hold] == 0).astype(float)
    bins = np.minimum((pd * 10).astype(int), 9)
    table = [{"bin": b, "rows": int((bins == b).sum()), "pred": float(pd[bins == b].mean()),
              "obs": float(died[bins == b].mean())} for b in range(10) if (bins == b).any()]
    ece = sum(t["rows"] * abs(t["pred"] - t["obs"]) for t in table) / max(1, len(pd))
    out["G3_sanity"] = {"ece": float(ece), "deathRate": float(died.mean()), "reliability": table}
    out["verdict"] = "STAGE3_GO" if out["G1"]["pass"] and out["G2"]["pass"] else "NO_GO"
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps({"verdict": out["verdict"], "G1": out["G1"].get("policyCE_net_minus_prior"),
                      "G2": out["G2"]["valueNLL_net_minus_baseline"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
