#!/usr/bin/env python3
"""Train-vs-search state distribution shift (leafdiag vs combatgen).

Task 4 of the 2026-08-08 handover: quantify how different the actual
Searcher3 leaf/query-state distribution (leafdiag CSV) is from the on-policy
combatgen trajectory-state distribution (build/vcombat_honest.csv, the §126
vnet training data).

Diagnostics:
  1. Per-feature means/std and 5/50/95 quantiles for both distributions, with
     the Kolmogorov-Smirnov distance (numpy-based) per feature; the top-KS
     features are printed.
  2. A binary classifier (SGD logistic regression, deterministic seed)
     distinguishing combatgen states (label 0) from Searcher3 leaf states
     (label 1); ROC-AUC is reported on a HELD-OUT test split (not the rows
     used to fit the classifier). A high AUC is evidence of covariate shift.
  3. Feature importance = standardized logistic coefficient magnitude. This
     is correlation, NOT causal attribution — do not overinterpret.

Row/feature alignment: both CSVs carry the canonical combat feature columns
(search::combatFeatureNames, src/sim/search/CombatValueNet.cpp). The scripts
align features by NAME, so producer column order may differ.

Output:
  --write-ood OUT.csv writes per-leafdiag-row P(search-leaf) as
  seed,fightIdx,decIdx,obsHash,ood_prob — the flag consumers such as
  tools/leaf_ranking.py use for the in-distribution vs off-distribution
  stratification. Note ood_prob is the classifier's class-1 probability (a
  shift indicator), NOT a calibrated out-of-distribution score.

All random draws use fixed seeds; repeated runs on identical inputs produce
identical output.
"""
import argparse
import csv
import json
import math
import sys

import numpy as np
import pandas as pd

CLASSIFIER_SEED = 20260808
MAX_TRAIN_ROWS = 60_000       # subsample cap for the (1 GB) training CSV
MAX_SEARCH_ROWS = 60_000      # subsample cap for the leafdiag CSV


def ks_distance(a, b):
    """Two-sample Kolmogorov-Smirnov distance (max CDF gap), numpy-based."""
    a = np.sort(np.asarray(a, dtype=float))
    b = np.sort(np.asarray(b, dtype=float))
    if a.size == 0 or b.size == 0:
        return float("nan")
    allv = np.unique(np.concatenate([a, b]))
    cdf_a = np.searchsorted(a, allv, side="right") / len(a)
    cdf_b = np.searchsorted(b, allv, side="right") / len(b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


def load_features(path, max_rows, usecols, id_cols=("seed", "fightIdx")):
    """Read canonical feature columns; uniform row subsample (deterministic).

    The id columns are read verbatim as strings (the leafdiag obsHash is a
    uint64 beyond float64 precision — converting it to float would corrupt the
    join keys used by leaf_ranking.py); the feature columns are float32."""
    rng = np.random.default_rng(CLASSIFIER_SEED)
    cols = list(id_cols) + list(usecols)
    dtype = {c: str for c in id_cols}
    for c in usecols:
        dtype[c] = np.float32
    out = []
    for chunk in pd.read_csv(path, usecols=cols, dtype=dtype, chunksize=50_000):
        keep = rng.random(len(chunk)) < (max_rows / max(len(chunk), 1))
        out.append(chunk.loc[keep])
        if sum(len(c) for c in out) >= max_rows:
            break
    if not out:
        return pd.DataFrame(columns=cols)
    df = pd.concat(out, ignore_index=True)
    if len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=CLASSIFIER_SEED)
    return df


def quantiles(a, qs=(0.05, 0.50, 0.95)):
    a = np.asarray(a, dtype=float)
    if a.size == 0:
        return (float("nan"),) * len(qs)
    return tuple(float(np.quantile(a, q)) for q in qs)


def per_feature_table(train, search, names):
    rows = []
    for name in names:
        ta = train[name].to_numpy(dtype=float)
        sa = search[name].to_numpy(dtype=float)
        rows.append({
            "feature": name,
            "train_mean": float(ta.mean()) if ta.size else float("nan"),
            "search_mean": float(sa.mean()) if sa.size else float("nan"),
            "train_std": float(ta.std()) if ta.size else float("nan"),
            "search_std": float(sa.std()) if sa.size else float("nan"),
            "train_q5": quantiles(ta)[0],
            "train_q50": quantiles(ta)[1],
            "train_q95": quantiles(ta)[2],
            "search_q5": quantiles(sa)[0],
            "search_q50": quantiles(sa)[1],
            "search_q95": quantiles(sa)[2],
            "ks": ks_distance(ta, sa),
        })
    return rows


def fit_classifier(train_feats, search_feats, names):
    """SGD logistic regression, deterministic; returns (auc_test, coef, model)."""
    from sklearn.linear_model import SGDClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    X = np.vstack([train_feats.to_numpy(dtype=np.float32),
                   search_feats.to_numpy(dtype=np.float32)])
    y = np.concatenate([np.zeros(len(train_feats), dtype=np.int8),
                        np.ones(len(search_feats), dtype=np.int8)])
    rng = np.random.default_rng(CLASSIFIER_SEED)
    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]
    n_test = max(1, len(y) // 3)
    X_tr, X_te = X[:len(y) - n_test], X[len(y) - n_test:]
    y_tr, y_te = y[:len(y) - n_test], y[len(y) - n_test:]
    scaler = StandardScaler().fit(X_tr)
    clf = SGDClassifier(loss="log_loss", max_iter=2000, tol=1e-4,
                        random_state=CLASSIFIER_SEED)
    clf.fit(scaler.transform(X_tr), y_tr)
    proba = clf.decision_function(scaler.transform(X_te))
    auc = float(roc_auc_score(y_te, proba))
    # importance on the standardized scale: coefficient magnitude per feature
    coef = clf.coef_[0]
    importances = sorted(zip(names, coef.tolist()), key=lambda t: -abs(t[1]))
    return auc, importances, clf, scaler


def write_ood(search, names, clf, scaler, out_path):
    X = search[names].to_numpy(dtype=np.float32)
    proba = clf.decision_function(scaler.transform(X))
    # clip before exp: decision_function can be huge (|d| > 700 overflows)
    p = 1.0 / (1.0 + np.exp(-np.clip(proba, -700.0, 700.0)))
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "fightIdx", "decIdx", "obsHash", "ood_prob"])
        for i in range(len(search)):
            w.writerow([search.iloc[i]["seed"], search.iloc[i]["fightIdx"],
                        search.iloc[i]["decIdx"], search.iloc[i]["obsHash"],
                        f"{p[i]:.6f}"])
    print(f"[leaf_distribution_shift] OOD flags -> {out_path}")


def self_test():
    rng = np.random.default_rng(3)
    names = ["f0", "f1"]
    # class 0: f0 ~ N(0,1), f1 ~ N(0,1); class 1: f0 shifted +3
    tr = pd.DataFrame({"f0": rng.normal(0, 1, 400), "f1": rng.normal(0, 1, 400)})
    sr = pd.DataFrame({"f0": rng.normal(3, 1, 400), "f1": rng.normal(0, 1, 400)})
    auc, imp, clf, scaler = fit_classifier(tr, sr, names)
    print(f"self-test: ROC-AUC {auc:.3f}")
    assert auc > 0.95, f"shifted distribution should be easy to separate, got {auc}"
    print("leaf_distribution_shift self-test PASS")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", default="build/vcombat_honest.csv",
                    help="combatgen training CSV (default build/vcombat_honest.csv)")
    ap.add_argument("--search", default="build/leafdiag.csv",
                    help="leafdiag CSV (default build/leafdiag.csv)")
    ap.add_argument("--json", default=None, help="write machine-readable JSON summary")
    ap.add_argument("--write-ood", default=None,
                    help="write per-search-row ood_prob CSV for leaf_ranking.py")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        return 0

    # canonical feature names come from the leafdiag header (between the
    # provenance block and the model columns); the training CSV uses the same
    # names. Align by name below.
    with open(args.search, newline="") as f:
        header = f.readline().strip().split(",")
    f0 = header.index("fightEndHp") + 1
    f1 = header.index("endHp_pred")
    names = header[f0:f1]
    print(f"[leaf_distribution_shift] {len(names)} canonical features, "
          f"train {args.train} vs search {args.search}")

    train = load_features(args.train, MAX_TRAIN_ROWS, names,
                          id_cols=("seed", "fightIdx"))
    search = load_features(args.search, MAX_SEARCH_ROWS, names,
                           id_cols=("seed", "fightIdx", "decIdx", "obsHash"))
    # keep only features present in BOTH CSVs
    common = [n for n in names if n in train.columns and n in search.columns]
    print(f"rows: train {len(train)} (subsampled), search {len(search)}; "
          f"{len(common)} common features")

    table = per_feature_table(train, search, common)
    table.sort(key=lambda r: -r["ks"])

    print("\n=== top-20 features by KS distance (train vs search-leaf) ===")
    print(f"{'feature':<18} {'train_mean':>10} {'search_mean':>11} {'train_q50':>9} "
          f"{'search_q50':>10} {'ks':>7}")
    for r in table[:20]:
        print(f"{r['feature']:<18} {r['train_mean']:>10.3f} {r['search_mean']:>11.3f} "
              f"{r['train_q50']:>9.3f} {r['search_q50']:>10.3f} {r['ks']:>7.4f}")

    # named diagnostic features the plan asks about explicitly
    interest = ["curHp", "maxHp", "monSumHp", "monMaxHp", "incomingDmg", "turn",
                "hand", "draw", "discard", "block"]
    print("\n=== named diagnostic features (train vs search) ===")
    print(f"{'feature':<14} {'train_mean':>10} {'search_mean':>11} {'ks':>7}")
    for r in table:
        if r["feature"] in interest:
            print(f"{r['feature']:<14} {r['train_mean']:>10.3f} {r['search_mean']:>11.3f} {r['ks']:>7.4f}")

    print("\n=== binary classifier: combatgen state (0) vs Searcher3 leaf state (1) ===")
    auc, importances, clf, scaler = fit_classifier(
        train[common], search[common], common)
    print(f"ROC-AUC (held-out test): {auc:.4f}")
    print(f"  train rows {len(train)}, search rows {len(search)}, "
          f"test fraction ~1/3")
    if auc > 0.9:
        print("  -> strong covariate shift evidence (a simple classifier "
              "separates the distributions almost perfectly)")
    elif auc > 0.75:
        print("  -> moderate covariate shift")
    else:
        print("  -> weak covariate shift")
    print("\n=== top-20 classifier features by |coef| (standardized; "
          "correlation, NOT causal) ===")
    for name, c in importances[:20]:
        print(f"  {name:<18} coef {c:+.4f}")

    summary = {
        "nTrain": len(train), "nSearch": len(search), "nFeatures": len(common),
        "auc": auc,
        "topKs": table[:20],
        "topCoef": [{"feature": n, "coef": c} for n, c in importances[:20]],
    }
    if args.write_ood:
        write_ood(search, common, clf, scaler, args.write_ood)
        summary["oodFile"] = args.write_ood
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2, sort_keys=True)
        print(f"[leaf_distribution_shift] JSON summary -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
