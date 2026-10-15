#!/usr/bin/env python3
"""Seed-grouped cross-validation of learned-stop model variants.

Reads STS_SILVER_STOP_TRACE CSVs and evaluates each model variant out of fold
(folds group whole source seeds). For every variant it simulates the stopping
policy (stop at the first strict lock or risk < threshold) over a threshold
grid and reports the simulation saving against flat 10k at fixed action
disagreement budgets, next to #199 and lock-only. Decisions with one legal
action are excluded, as production commits them unsearched.

  silver_learned_stop_cv.py TRACE... [--folds 5] [--out cv.json]
"""
import argparse
import json
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import silver_learned_stop as sls  # noqa: E402

F = sls.FEATURES
IDX = {name: i for i, name in enumerate(F)}
BUDGETS = [0.0025, 0.005, 0.0075, 0.01]
THRESHOLDS = sorted(set(np.round(np.concatenate([np.geomspace(1e-4, 0.3, 80)]), 6)))


def arrays(decisions):
    """Stack per-decision checkpoint rows: X[d, c, f], leader-wrong[d, c], seed[d], fresh[d]."""
    X = np.array([[r[1] for r in d["rows"]] for d in decisions])
    wrong = np.array([[int(r[2] != d["final"]) for r in d["rows"]] for d in decisions])
    seeds = np.array([d["seed"] for d in decisions])
    fresh = np.array([d["fresh"] for d in decisions])
    return X, wrong, seeds, fresh


def simulate(risk, X, wrong, thr):
    """risk[d, c]; returns used sims[d], error[d] for one threshold."""
    ck = np.array(sls.CHECKPOINTS)
    stop = (X[:, :, IDX["lock"]] > 0) | (risk < thr)
    stop[:, -1] = True
    first = stop.argmax(axis=1)
    rows = np.arange(len(X))
    return ck[first], wrong[rows, first]


def rule_199(X, wrong, fresh):
    ok = (fresh == 0) & (X[:, 1, IDX["legal_actions"]] > 1) & (X[:, 1, IDX["gap_share"]] >= sls.TOP_GAP_199)
    used = np.where(ok, 500, sls.BMAX)
    err = np.where(ok, wrong[:, 1], 0)
    return used, err


def frontier(risk, X, wrong, fresh):
    pts = []
    for thr in THRESHOLDS:
        used, err = simulate(risk, X, wrong, thr)
        pts.append((thr, 1 - used.sum() / (sls.BMAX * len(X)), err.mean(),
                    1 - used[fresh == 1].sum() / (sls.BMAX * max(1, (fresh == 1).sum())), err[fresh == 1].mean()))
    out = {}
    for b in BUDGETS:
        ok = [p for p in pts if p[2] <= b]
        best = max(ok, key=lambda p: p[1]) if ok else None
        out[str(b)] = None if best is None else {
            "threshold": best[0], "saving": best[1], "disagreement": best[2],
            "freshSaving": best[3], "freshDisagreement": best[4]}
    return out


def make_variants(n_features=len(F)):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    mono = [0] * len(F)
    for name, sign in (("top_share", -1), ("gap_share", -1), ("entropy", 1), ("leader_streak", -1),
                       ("rho", -1), ("lock", -1), ("second_share", 1)):
        mono[IDX[name]] = sign
    return {
        "gbt_v1": lambda: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                                         random_state=0),
        "gbt_small": lambda: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                                                            min_samples_leaf=200, l2_regularization=1.0,
                                                            random_state=0),
        "gbt_mono": lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                           min_samples_leaf=200, l2_regularization=1.0,
                                                           monotonic_cst=mono[:n_features], random_state=0),
        "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("trace", nargs="+")
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--variants", default="")
    p.add_argument("--features", choices=["base", "all"], default="all",
                   help="base: the 18 v1 features; all: plus the 4 trend features")
    p.add_argument("--out")
    args = p.parse_args()
    decisions = [d for d in sls.load_traces(args.trace).values() if d["rows"][0][1][IDX["legal_actions"]] > 1]
    X, wrong, seeds, fresh = arrays(decisions)
    Xfit = X if args.features == "all" else X[:, :, :len(sls.BASE_FEATURES)]
    useeds = np.unique(seeds)
    fold_of_seed = {s: i % args.folds for i, s in enumerate(np.random.default_rng(0).permutation(useeds))}
    fold = np.array([fold_of_seed[s] for s in seeds])
    report = {"decisions": int(len(X)), "seeds": int(len(useeds)), "folds": args.folds, "features": args.features,
              "freshDecisions": int(fresh.sum())}
    used, err = rule_199(X, wrong, fresh)
    report["rule_199"] = {"saving": 1 - used.sum() / (sls.BMAX * len(X)), "disagreement": float(err.mean())}
    lock = np.ones(X.shape[:2])  # risk 1 everywhere: only locks stop
    report["lock_only"] = frontier(lock, X, wrong, fresh)["0.01"]
    variants = make_variants(Xfit.shape[2])
    chosen = [v for v in args.variants.split(",") if v] or list(variants)
    for name in chosen:
        risk = np.ones(X.shape[:2])
        for f in range(args.folds):
            tr, te = fold != f, fold == f
            Xtr = Xfit[tr][:, :-1].reshape(-1, Xfit.shape[2])
            ytr = wrong[tr][:, :-1].reshape(-1)
            model = variants[name]().fit(Xtr, ytr)
            Xte = Xfit[te][:, :-1].reshape(-1, Xfit.shape[2])
            risk[te, :-1] = model.predict_proba(Xte)[:, 1].reshape(-1, X.shape[1] - 1)
        report[name] = frontier(risk, X, wrong, fresh)
        print(name, json.dumps(report[name]), flush=True)
    text = json.dumps(report, indent=1, default=float)
    if args.out:
        open(args.out, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
