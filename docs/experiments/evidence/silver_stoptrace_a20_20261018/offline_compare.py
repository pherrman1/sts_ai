#!/usr/bin/env python3
"""Step 2 of PLAN.md: old stop model vs a retrained one on held-out A20 stop traces.

usage: offline_compare.py OUT_JSON TRACE_ROOT [...]   (extracted worker tars; *.trace.csv.gz found recursively)

Seeds sorted by run seed: first 384 train, last 128 held out (with fewer seeds: first 3/4 train). The retrained
model is tools/silver_learned_stop.py's recipe (GBT v1 + trend features) on the training seeds. Its threshold is
chosen from 5-fold seed-grouped out-of-fold risks on the training seeds: the largest-saving threshold whose
disagreement is <= the old model's disagreement (threshold 0.0323) on the same training seeds. Held-out: both
policies simulated (stop at the first strict lock or risk < threshold), saving vs flat 10k and disagreement with
the 10k leader, seed-cluster bootstrap 95% intervals of new - old (2,000 draws). Verdict per PLAN.md:
RETRAIN_BETTER if the saving interval > 0 and the disagreement upper bound <= +0.25 pp, else OLD_STAYS.
"""
import glob
import gzip
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools"))
import silver_learned_stop as sls  # noqa: E402
import silver_learned_stop_cv as cv  # noqa: E402

OLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "silver_learned_stop", "v2", "training",
                   "model.json.gz")
OLD_THR = 0.0323
N_TRAIN, N_HOLD = 384, 128
DIS_MARGIN = 0.0025


def gbt():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0)


def fit(X, wrong):
    clf = gbt()
    clf.fit(X[:, :-1].reshape(-1, X.shape[2]), wrong[:, :-1].ravel())
    return clf


def risk_of(clf, X):
    return clf.predict_proba(X.reshape(-1, X.shape[2]))[:, 1].reshape(X.shape[0], X.shape[1])


def old_risk(model, X):
    """Vectorized sls.risk over X[d, c, f] (same tree walk: go left when x <= threshold)."""
    flat = X.reshape(-1, X.shape[2])
    raw = np.full(len(flat), model["baseline"])
    for tree in model["trees"]:
        leaf = np.array([n["leaf"] for n in tree]); feat = np.array([n["feature"] for n in tree])
        thr = np.array([n["threshold"] for n in tree]); left = np.array([n["left"] for n in tree])
        right = np.array([n["right"] for n in tree]); val = np.array([n["value"] for n in tree])
        node = np.zeros(len(flat), dtype=int)
        while True:
            active = ~leaf[node]
            if not active.any():
                break
            a = np.where(active)[0]; nd = node[a]
            go_left = flat[a, feat[nd]] <= thr[nd]
            node[a] = np.where(go_left, left[nd], right[nd])
        raw += val[node]
    return (1.0 / (1.0 + np.exp(-raw))).reshape(X.shape[0], X.shape[1])


def stats(used, err):
    return 1 - used.sum() / (sls.BMAX * len(used)), err.mean()


def main(argv):
    out, roots = argv[1], argv[2:]
    paths = sorted(p for r in roots for p in glob.glob(os.path.join(r, "**", "*.trace.csv.gz"), recursive=True))
    decisions = [d for d in sls.load_traces(paths).values()
                 if d["rows"][0][1][sls.FEATURES.index("legal_actions")] > 1]
    X, wrong, seeds, fresh = cv.arrays(decisions)
    useeds = sorted(set(seeds))
    n_train = N_TRAIN if len(useeds) >= N_TRAIN + N_HOLD else (3 * len(useeds)) // 4
    tr_seeds, ho_seeds = set(useeds[:n_train]), set(useeds[n_train:])
    tr = np.array([s in tr_seeds for s in seeds]); ho = ~tr
    old = json.load(gzip.open(OLD, "rt"))
    assert old["features"] == sls.FEATURES, "old model feature list differs"
    r_old = old_risk(old, X)
    for i in range(0, len(X), max(1, len(X) // 200)):
        for c in range(X.shape[1]):
            assert abs(r_old[i, c] - sls.risk(old, list(X[i, c]))) < 1e-9, "vectorized old risk differs"
    _, d_old_tr = stats(*cv.simulate(r_old[tr], X[tr], wrong[tr], OLD_THR))
    # Out-of-fold risks on the training seeds for the threshold choice.
    tr_list = sorted(tr_seeds); fold = {s: i % 5 for i, s in enumerate(tr_list)}
    oof = np.zeros(X.shape[:2]); tri = np.where(tr)[0]
    for k in range(5):
        fit_i = np.array([i for i in tri if fold[seeds[i]] != k], dtype=int)
        val_i = np.array([i for i in tri if fold[seeds[i]] == k], dtype=int)
        if len(val_i) == 0 or len(fit_i) == 0:
            continue
        oof[val_i] = risk_of(fit(X[fit_i], wrong[fit_i]), X[val_i])
    best = None
    for thr in cv.THRESHOLDS:
        s, d = stats(*cv.simulate(oof[tr], X[tr], wrong[tr], thr))
        if d <= d_old_tr and (best is None or s > best[1]):
            best = (float(thr), s, d)
    thr_new = best[0] if best else min(cv.THRESHOLDS)
    r_new = risk_of(fit(X[tr], wrong[tr]), X)
    used_o, err_o = cv.simulate(r_old, X, wrong, OLD_THR)
    used_n, err_n = cv.simulate(r_new, X, wrong, thr_new)
    hs = sorted(ho_seeds); idx = {s: np.where(seeds == s)[0] for s in hs}
    def diff(sel):
        so, do = stats(used_o[sel], err_o[sel]); sn, dn = stats(used_n[sel], err_n[sel])
        return sn - so, dn - do
    point = diff(np.concatenate([idx[s] for s in hs]))
    rng = np.random.default_rng(0); boots = []
    for _ in range(2000):
        pick = rng.choice(len(hs), len(hs))
        boots.append(diff(np.concatenate([idx[hs[i]] for i in pick])))
    boots = np.array(boots)
    ci = lambda j: [float(np.percentile(boots[:, j], 2.5)), float(np.percentile(boots[:, j], 97.5))]
    hsel = np.concatenate([idx[s] for s in hs])
    res = {"decisions": int(len(X)), "seeds_train": len(tr_seeds), "seeds_heldout": len(ho_seeds),
           "old": {"id": old["id"], "threshold": OLD_THR, "train_disagreement": d_old_tr,
                   "heldout_saving_disagreement": stats(used_o[hsel], err_o[hsel])},
           "new": {"threshold": thr_new, "oof_train": best,
                   "heldout_saving_disagreement": stats(used_n[hsel], err_n[hsel])},
           "new_minus_old": {"saving": point[0], "saving_ci95": ci(0),
                             "disagreement": point[1], "disagreement_ci95": ci(1)}}
    res["verdict"] = ("RETRAIN_BETTER" if res["new_minus_old"]["saving_ci95"][0] > 0
                      and res["new_minus_old"]["disagreement_ci95"][1] <= DIS_MARGIN else "OLD_STAYS")
    json.dump(res, open(out, "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
