#!/usr/bin/env python3
"""E2: evaluate an eventual-run-win critic at the post-combat boundary.

Rows are the canonical ``vrich.csv`` rich state after forced gold/relic/potion
pickup and immediately before the first card pick/skip.  ``won`` is the final
run outcome.  All models use the same seed-grouped split and the existing
train_winrate.py XGBoost recipe; only the feature set differs.
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

LABELS = {"seed", "won", "finalFloor", "endHp"}
B1_FEATURES = ["curHp", "maxHp", "hpFrac", "act", "floor"]
SPLIT = {"method": "GroupShuffleSplit", "test_size": 0.15, "random_state": 0}
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 0
MIN_ACT_SEEDS = 1000
XGB_PARAMS = dict(objective="binary:logistic", eval_metric=["auc", "logloss"],
                  tree_method="hist", max_depth=8, eta=0.05, subsample=0.8,
                  colsample_bytree=0.7, min_child_weight=20, max_bin=256,
                  random_state=0)


def ece(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    idx = np.clip(np.digitize(p, np.linspace(0, 1, bins + 1)[1:-1]), 0, bins - 1)
    return float(sum(np.mean(idx == b) * abs(y[idx == b].mean() - p[idx == b].mean())
                     for b in range(bins) if np.any(idx == b)))


def calibration(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    return [{"bin_lo": float(edges[b]), "bin_hi": float(edges[b + 1]),
             "n": int((idx == b).sum()),
             "mean_pred": float(p[idx == b].mean()) if np.any(idx == b) else None,
             "observed": float(y[idx == b].mean()) if np.any(idx == b) else None}
            for b in range(bins)]


def metrics(y, p):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return {"n": int(len(y)), "pos": int(y.sum()), "neg": int(len(y) - y.sum()),
            "auc": float(roc_auc_score(y, p)),
            "logloss": float(log_loss(y, p, labels=[0, 1])),
            "brier": float(np.mean((p - y) ** 2)), "ece": ece(y, p),
            "pos_rate": float(y.mean())}


def grouped_split(seeds):
    return next(GroupShuffleSplit(1, test_size=SPLIT["test_size"],
                                  random_state=SPLIT["random_state"])
                .split(np.zeros(len(seeds)), groups=seeds))


def bootstrap_deltas(y, pt, pb, run, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """Return T-B1 deltas after resampling held-out runs, not rows."""
    y, pt, pb = map(lambda a: np.asarray(a, float), (y, pt, pb))
    pt, pb = np.clip(pt, 1e-12, 1 - 1e-12), np.clip(pb, 1e-12, 1 - 1e-12)
    lt = -(y * np.log(pt) + (1 - y) * np.log1p(-pt))
    lb = -(y * np.log(pb) + (1 - y) * np.log1p(-pb))
    bt, bb = (pt - y) ** 2, (pb - y) ** 2
    nr = int(np.max(run)) + 1
    rng = np.random.default_rng(seed)
    out = {"logloss": [], "brier": [], "auc": []}
    for _ in range(n):
        weights = np.bincount(rng.integers(nr, size=nr), minlength=nr)[run]
        out["logloss"].append(float(np.average(lt - lb, weights=weights)))
        out["brier"].append(float(np.average(bt - bb, weights=weights)))
        out["auc"].append(float(roc_auc_score(y, pt, sample_weight=weights)
                                - roc_auc_score(y, pb, sample_weight=weights)))
    return out


def ci(values):
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def device():
    requested = os.environ.get("STS_XGB_DEVICE")
    if requested:
        return requested
    try:
        subprocess.run(["nvidia-smi"], check=True, capture_output=True)
        return "cuda"
    except (OSError, subprocess.CalledProcessError):
        return "cpu"


def fit(Xtr, ytr, Xva, yva, names, dev):
    params = {**XGB_PARAMS, "device": dev}
    dtr = xgb.QuantileDMatrix(Xtr, label=ytr, feature_names=names)
    dva = xgb.QuantileDMatrix(Xva, label=yva, ref=dtr, feature_names=names)
    b = xgb.train(params, dtr, num_boost_round=1500, evals=[(dva, "val")],
                  early_stopping_rounds=40, verbose_eval=200)
    best = int(b.best_iteration)
    return b, best, b.predict(dva, iteration_range=(0, best + 1))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def classify(t, b1, boot, act_cal):
    ll_ci = ci(boot["logloss"])
    major = [{"act": a, **v} for a, v in act_cal.items()
             if v["seeds"] >= MIN_ACT_SEEDS and v["ece"] > 0.10]
    checks = {
        "T_logloss_below_B1": t["logloss"] < b1["logloss"],
        "T_brier_below_B1": t["brier"] < b1["brier"],
        "T_auc_above_B1": t["auc"] > b1["auc"],
        "bootstrap_logloss_ci_favorable": ll_ci[1] < 0,
        "T_ece_le_0.10": t["ece"] <= 0.10,
        "no_major_act_calibration_failure": not major,
    }
    first = all(checks[k] for k in ("T_logloss_below_B1", "T_brier_below_B1",
                                    "T_auc_above_B1"))
    result = "SUPPORTED" if all(checks.values()) else ("INCONCLUSIVE" if first else "NEGATIVE")
    return result, {"checks": checks, "logloss_ci95": ll_ci,
                    "major_act_failures": major}


def main():
    csv = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "build/e2_postcombat_runwin"
    cap = int(sys.argv[sys.argv.index("--max-runs") + 1]) if "--max-runs" in sys.argv else None
    os.makedirs(out, exist_ok=True)
    print(f"loading {csv} ...", flush=True)
    df = pd.read_csv(csv, dtype=np.float32)
    header, col = list(df.columns), {c: i for i, c in enumerate(df.columns)}
    required = {"seed", "won", "act", "floor", "curHp", "maxHp"}
    missing = required - set(header)
    if missing:
        raise SystemExit(f"missing columns: {sorted(missing)}")
    # Verify run labels before any filtering; this also proves won is eventual
    # run outcome rather than fight outcome.
    label_counts = df.groupby("seed")["won"].nunique()
    if (label_counts > 1).any():
        raise SystemExit("won is not constant within every seed")
    if cap is not None:
        keep = np.sort(df["seed"].unique())[:cap]
        df = df[df.seed.isin(keep)].reset_index(drop=True)
    data = df.to_numpy(); del df
    seeds = data[:, col["seed"]].astype(np.int64)
    y = data[:, col["won"]].astype(np.float32)
    _, run = np.unique(seeds, return_inverse=True)
    tr, va = grouped_split(seeds)
    if set(seeds[tr]) & set(seeds[va]):
        raise AssertionError("group leakage")
    nrun = int(run.max()) + 1
    run_win = np.bincount(run, weights=y, minlength=nrun) > 0
    print(f"rows={len(y)} runs={nrun} wins={run_win.sum()} "
          f"train={len(np.unique(seeds[tr]))} val={len(np.unique(seeds[va]))}", flush=True)
    dev = device()
    base = float(y[tr].mean())
    p0 = np.full(len(va), base)
    m0 = metrics(y[va], p0)
    hpfrac = data[:, col["curHp"]] / np.maximum(data[:, col["maxHp"]], 1)
    b1 = np.column_stack([data[:, col["curHp"]], data[:, col["maxHp"]], hpfrac,
                          data[:, col["act"]], data[:, col["floor"]]]).astype(np.float32)
    b1m, b1best, p1 = fit(b1[tr], y[tr], b1[va], y[va], B1_FEATURES, dev)
    b1m.save_model(os.path.join(out, "b1_model.json"))
    m1 = metrics(y[va], p1)
    rich = [c for c in header if c not in LABELS and data[:, col[c]].std() > 1e-9]
    idx = [col[c] for c in rich]
    tm, tbest, pt = fit(data[np.ix_(tr, idx)], y[tr], data[np.ix_(va, idx)], y[va], rich, dev)
    tm.save_model(os.path.join(out, "t_model.json"))
    mt = metrics(y[va], pt)
    print(f"B0 {m0}\nB1 {m1} best_iter={b1best}\nT {mt} features={len(rich)} best_iter={tbest}", flush=True)

    act_metrics, act_cal = {}, {}
    acts = data[:, col["act"]].astype(int)
    for a in sorted(np.unique(acts[va])):
        sel = acts[va] == a
        act_metrics[str(a)] = metrics(y[va][sel], pt[sel])
        act_cal[str(a)] = {"ece": ece(y[va][sel], pt[sel]),
                           "seeds": int(len(np.unique(run[va][sel]))),
                           "rows": int(sel.sum())}
    boot = bootstrap_deltas(y[va], pt, p1, run[va])
    boot_summary = {k: {"mean": float(np.mean(v)), "ci95": ci(v)} for k, v in boot.items()}
    result, decision = classify(mt, m1, boot, act_cal)
    print(f"bootstrap={boot_summary}\nclassification={result}", flush=True)
    cal_path = os.path.join(out, "calibration_deciles.csv")
    with open(cal_path, "w") as f:
        f.write("model,bin_lo,bin_hi,n,mean_pred,observed\n")
        for name, pred in (("B0", p0), ("B1", p1), ("T", pt)):
            for row in calibration(y[va], pred):
                f.write(name + "," + ",".join(str(row[k]) for k in
                        ("bin_lo", "bin_hi", "n", "mean_pred", "observed")) + "\n")
    metrics_out = {"experiment": "E2 post-combat run-win critic",
                   "dataset": os.path.abspath(csv), "rows": len(y), "runs": nrun,
                   "wins": int(run_win.sum()), "losses": int(nrun - run_win.sum()),
                   "acts": {str(a): int((acts == a).sum()) for a in sorted(np.unique(acts))},
                   "boundary": "after forced gold/relic/potion pickup, before card pick/skip",
                   "split": {**SPLIT, "train_rows": len(tr), "val_rows": len(va),
                             "train_seeds": len(np.unique(seeds[tr])),
                             "val_seeds": len(np.unique(seeds[va]))},
                   "b0": m0, "b1": m1, "t": mt, "b1_features": B1_FEATURES,
                   "t_features": rich, "device": dev,
                   "xgb_params": {**XGB_PARAMS, "device": dev},
                   "best_iteration": {"b1": b1best, "t": tbest},
                   "act_metrics": act_metrics, "act_calibration": act_cal,
                   "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED,
                                 "unit": "held-out seed", "summary": boot_summary},
                   "classification": result, "decision": decision}
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(metrics_out, f, indent=2)
    np.savez_compressed(os.path.join(out, "val_predictions.npz"), seed=seeds[va],
                        y=y[va], p_b1=p1, p_t=pt, act=acts[va])
    with open(os.path.join(out, "provenance.json"), "w") as f:
        json.dump({"git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                   "dataset_sha256": sha256(csv), "csv": os.path.abspath(csv),
                   "boundary": metrics_out["boundary"], "continuation_policy":
                   "datagen2 Jul 15 2026: sims=10000 asc=0 eps=0.05; v_server V-marginal"}, f, indent=2)
    with open(os.path.join(out, "sha256sums.txt"), "w") as f:
        for name in sorted(os.listdir(out)):
            if name != "sha256sums.txt":
                f.write(f"{sha256(os.path.join(out, name))}  {name}\n")


if __name__ == "__main__":
    main()