#!/usr/bin/env python3
"""Offline prior v2 for the synthetic Silver root prior (follows ledger §397/§399).

Differences from the §397 prior (tools/silver_synth_gates.py):
- features: root state ++ action block ++ (sampled post-action state - root
  state), using the "after" rows that `one_combat silversynthfeatures` writes;
- objective: per-root softmax cross-entropy against the 10k visit shares
  (listwise), instead of pointwise cross-entropy per action;
- more boosting rounds, a wider weight grid and a 2,000-sim replay budget.

Same corpus, folds (train 0-2, val 3, test 4), teacher and replay harness as
§397, so v1, v2, plain and the visit-share oracle are compared on the same
test roots.

  train FEATURES OUT
  tasks FEATURES CORPUS OUT val|test [V1_MODEL]
  report OUT
"""
import glob
import gzip
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from silver_synth_gates import TEST, VAL, boot_mean, edge_rows, fold, load, root_id, teacher, visit_shares  # noqa: E402

PARAMS = dict(num_leaves=63, learning_rate=0.05, min_data_in_leaf=100, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4, seed=1)
ROUNDS = 6000
WEIGHTS = [200, 400, 800, 1600, 3200]
BUDGETS = [256, 1000, 2000]
REPLAY_SEEDS = [11, 12]
VARIANTS = ("natural", "perturbed")


def v2_rows(X, metas, n_state):
    """Edge rows with afterstate deltas; groups are contiguous per root."""
    E, acts, owner, roots = edge_rows(X, metas)
    after, cur = {}, None
    for i, m in enumerate(metas):
        if m["k"] == "state":
            cur = i
        elif m["k"] == "after":
            after[(cur, m["e"])] = i
    idx = []
    for a, o in zip(acts, owner):
        idx.append(after[(o, metas[a]["e"])])
    D = X[idx][:, :n_state] - X[owner][:, :n_state]
    return sp.hstack([E, D], format="csr"), acts, owner, roots


def groups_of(owner):
    starts = np.flatnonzero(np.r_[True, owner[1:] != owner[:-1]])
    return starts, np.diff(np.r_[starts, len(owner)])


def group_softmax(z, starts):
    m = np.maximum.reduceat(z, starts)
    sizes = np.diff(np.r_[starts, len(z)])
    e = np.exp(z - np.repeat(m, sizes))
    s = np.add.reduceat(e, starts)
    return e / np.repeat(s, sizes)


def softmax_objective(starts):
    def fobj(preds, data):
        y = data.get_label()
        p = group_softmax(preds, starts)
        return p - y, np.maximum(p * (1 - p), 1e-6)
    return fobj


def softmax_eval(starts):
    def feval(preds, data):
        y = data.get_label()
        p = group_softmax(preds, starts)
        return "group_xent", float(-(y * np.log(np.maximum(p, 1e-12))).sum() / len(starts)), False
    return feval


def select(metas, acts, owner, roots, folds):
    return np.array([k for k, o in enumerate(owner) if len(roots[o]) >= 2
                     and metas[o]["variant"] in VARIANTS and fold(metas[o]) in folds], dtype=np.int64)


def cmd_train(features_dir, out):
    os.makedirs(out, exist_ok=True)
    X, metas, n_state = load(features_dir)
    F, acts, owner, roots = v2_rows(X, metas, n_state)
    share = visit_shares(metas, roots)
    y = np.array([share[a] for a in acts])
    tr, va = select(metas, acts, owner, roots, (0, 1, 2)), select(metas, acts, owner, roots, (VAL,))
    st_tr, _ = groups_of(owner[tr])
    st_va, _ = groups_of(owner[va])
    dtr = lgb.Dataset(F[tr], y[tr], free_raw_data=False)
    dva = lgb.Dataset(F[va], y[va], reference=dtr, free_raw_data=False)
    params = dict(PARAMS, objective=softmax_objective(st_tr), metric="None")
    val_obj = softmax_eval(st_va)
    model = lgb.train(params, dtr, num_boost_round=ROUNDS, valid_sets=[dva],
                      feval=lambda p, d: val_obj(p, d) if d is dva else ("group_xent", 0.0, False),
                      callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(200)])
    model.save_model(os.path.join(out, "prior-v2.txt"))
    report = {"rows": int(F.shape[0]), "width": int(F.shape[1]), "train": len(tr), "val": len(va),
              "trainRoots": len(st_tr), "valRoots": len(st_va), "iters": model.best_iteration,
              "valGroupXent": model.best_score["valid_0"]["group_xent"]}
    # Reference: visit-share entropy (the floor) on val.
    yv = y[va]
    report["valEntropyFloor"] = float(-(yv * np.log(np.maximum(yv, 1e-12))).sum() / len(st_va))
    json.dump(report, open(os.path.join(out, "train-v2.json"), "w"), indent=2)
    print(json.dumps(report))


def cmd_tasks(features_dir, corpus_dir, out, split, v1_model=None):
    X, metas, n_state = load(features_dir)
    F, acts, owner, roots = v2_rows(X, metas, n_state)
    E = F[:, :X.shape[1]]
    want_fold = {"val": VAL, "test": TEST}[split]
    chosen = [r for r, a in roots.items() if len(a) >= 2 and metas[r]["variant"] == "natural"
              and metas[r]["second"] and fold(metas[r]) == want_fold]
    if split == "val":
        chosen = chosen[:: max(1, len(chosen) // 1000)][:1000]
    pos = {a: k for k, a in enumerate(acts)}
    rows = np.array([pos[a] for r in chosen for a in roots[r]])
    v2 = lgb.Booster(model_file=os.path.join(out, "prior-v2.txt"))
    z2 = dict(zip(rows, v2.predict(F[rows], raw_score=True)))
    z1 = None
    if v1_model:
        v1 = lgb.Booster(model_file=v1_model)
        z1 = dict(zip(rows, v1.predict(E[rows])))
    share = visit_shares(metas, roots)
    priors = {}
    for r in chosen:
        z = np.array([z2[pos[a]] for a in roots[r]])
        p2 = np.exp(z - z.max())
        info = {"v2": (p2 / p2.sum()).tolist(), "oracle": [share[a] for a in roots[r]],
                "bits": [metas[a]["bits"] for a in roots[r]], "teacher": teacher(metas, roots[r])}
        if z1 is not None:
            p1 = np.array([z1[pos[a]] for a in roots[r]])
            info["v1"] = (p1 / p1.sum()).tolist()
        priors[root_id(metas[r])] = info
    json.dump({"|".join(map(str, k)): v for k, v in priors.items()},
              open(os.path.join(out, f"roots-{split}.json"), "w"))
    arms = [("plain", None, 0)]
    if split == "val":
        arms += [(f"v2-w{w}", "v2", w) for w in WEIGHTS]
    else:
        w = json.load(open(os.path.join(out, "weight-v2.json")))["weight"]
        # Picked weight first; v2-w400 is a secondary arm (same weight as v1).
        arms += [(f"v2-w{w}", "v2", w), ("v2-w400", "v2", 400), ("v1-w400", "v1", 400),
                 (f"oracle-w{w}", "oracle", w), ("oracle-w400", "oracle", 400)]
        arms = list(dict.fromkeys(arms))
    with open(os.path.join(out, f"tasks-{split}.jsonl"), "w") as f:
        for path in sorted(glob.glob(os.path.join(corpus_dir, "natural-*.jsonl.gz"))):
            for line in gzip.open(path, "rt"):
                if '"kind":"root"' not in line:
                    continue
                row = json.loads(line)
                rid = (row["variant"], row["seed"], row["fight"], row["decision"])
                if rid not in priors:
                    continue
                pr = priors[rid]
                for name, source, w in arms:
                    f.write(json.dumps({"id": ["|".join(map(str, rid)), name], "wire": row["wire"],
                                        "bits": pr["bits"], "prior": pr[source] if source else None,
                                        "weight": w, "budgets": BUDGETS, "seeds": REPLAY_SEEDS}) + "\n")
    print(split, "roots", len(priors), "arms", [a[0] for a in arms])


def regrets(out, split):
    roots = json.load(open(os.path.join(out, f"roots-{split}.json")))
    reg, dropped = {}, 0
    for path in glob.glob(os.path.join(out, f"replay-{split}-*.jsonl")):
        for line in open(path):
            if not line.startswith("{"):
                continue
            r = json.loads(line)
            rid, name = r["id"]
            if not r["ok"]:
                dropped += 1
                continue
            info = roots[rid]
            T = np.array(info["teacher"])
            for run in r["runs"]:
                c = info["bits"].index(run["chosen"])
                reg.setdefault(name, {}).setdefault(run["budget"], {})[(rid, run["seed"])] = T.max() - T[c]
    return reg, dropped


def cmd_pickweight(out):
    reg, dropped = regrets(out, "val")
    means = {b: {n: float(np.mean(list(reg[n][b].values()))) for n in reg} for b in BUDGETS}
    # Pick on the 1,000-sim budget (closest to the online 2k use), ties to the smaller weight.
    best = min(WEIGHTS, key=lambda w: (round(means[1000][f"v2-w{w}"], 9), w))
    json.dump({"weight": best, "valMeans": means, "dropped": dropped},
              open(os.path.join(out, "weight-v2.json"), "w"), indent=2)
    print(json.dumps({"weight": best, "valMeans": means}, indent=2))


def cmd_report(out):
    reg, dropped = regrets(out, "test")
    common = None
    for n in reg:
        for b in BUDGETS:
            k = set(reg[n][b])
            common = k if common is None else common & k
    common = sorted(common)
    seeds = np.array([int(k[0].split("|")[1]) for k in common])
    rng = np.random.default_rng(13)
    res = {"runs": len(common), "dropped": dropped}
    for b in BUDGETS:
        base = np.array([reg["plain"][b][k] for k in common])
        res[b] = {"plain": float(base.mean())}
        for n in reg:
            if n == "plain":
                continue
            r = np.array([reg[n][b][k] for k in common])
            res[b][n] = {"regret": float(r.mean()), "minusPlain": boot_mean(r - base, seeds, rng)}
        orc = [n for n in reg if n.startswith("oracle")]
        best_oracle = min(orc, key=lambda n: res[b][n]["regret"])
        gap = res[b]["plain"] - res[b][best_oracle]["regret"]
        for n in reg:
            if n.startswith(("v1", "v2")):
                res[b][n]["shareOfOracleGain"] = (res[b]["plain"] - res[b][n]["regret"]) / gap if gap > 0 else None
        v1 = np.array([reg["v1-w400"][b][k] for k in common])
        for n in reg:
            if n.startswith("v2"):
                v2 = np.array([reg[n][b][k] for k in common])
                res[b][n]["minusV1"] = boot_mean(v2 - v1, seeds, rng)
    json.dump(res, open(os.path.join(out, "report-v2.json"), "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"train": cmd_train, "tasks": cmd_tasks, "pickweight": cmd_pickweight, "report": cmd_report}[cmd](*args)
