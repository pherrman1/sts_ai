#!/usr/bin/env python3
"""E2b masked post-combat run-win diagnostic."""
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
XGB_PARAMS = dict(objective="binary:logistic", eval_metric=["auc", "logloss"],
                  tree_method="hist", max_depth=8, eta=0.05, subsample=0.8,
                  colsample_bytree=0.7, min_child_weight=20, max_bin=256,
                  random_state=0)

# Explicit live-schema families. Unknown features fail closed as ambiguous.
HIDDEN_EXACT = {"bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2",
                "remElites", "remFights", "monOffset", "eliteOffset"}
HIDDEN_PREFIXES = ("fmD", "fmC")
DIRECT_REWARD_EXACT = {"gold", "potionCount", "potionChance",
                       "cardRarityFactor", "blueKey", "greenKey", "redKey"}
REWARD_SIDE_EFFECT_EXACT = {"curHp", "maxHp", "deckSize", "potionCapacity",
                            "bottledAtkId", "bottledSkillId", "bottledPowId"}
STABLE_EXACT = {"ascension", "act", "floor", "blueKey", "greenKey", "redKey",
                "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure",
                "curMapX", "curMapY"}
STABLE_PREFIXES = ("d", "u")


def classify_feature(name):
    if name in HIDDEN_EXACT or name.startswith(HIDDEN_PREFIXES):
        return "hidden/future", False, False, "future encounter/map-derived information"
    if (name in DIRECT_REWARD_EXACT or
            (name.startswith("r") and name[1:].isdigit()) or
            (name.startswith("pot") and name[3:].isdigit())):
        return "reward-mutated-direct", False, False, "reward generation or direct pickup changes this value"
    if name in REWARD_SIDE_EFFECT_EXACT or name.startswith(("d", "u")):
        return "reward-mutated-side-effect", False, False, "elite relic pickup can change this encoded state"
    if name in STABLE_EXACT or name.startswith(STABLE_PREFIXES):
        return "fair+post-reward-stable", True, True, "persistent state emitted by richRow"
    return "ambiguous", False, False, "no exact live-code boundary proof"


def manifest(header):
    out = []
    for name in header:
        if name in LABELS:
            continue
        family, fair, stable, reason = classify_feature(name)
        out.append({"feature": name, "family": family, "fair_observable": fair,
                    "raw_terminal_stable": stable, "reason": reason,
                    "source_symbol": "apps/one_combat.cpp::richHeader/richRow"})
    return out


def feature_sets(header, varying):
    by_name = {r["feature"]: r for r in manifest(header)}
    full = [c for c in header if c not in LABELS and c in varying]
    fair = [c for c in full if by_name[c]["family"] != "hidden/future"]
    masked = [c for c in fair if by_name[c]["family"] == "fair+post-reward-stable"]
    if not set(masked).issubset(fair) or not set(fair).issubset(full):
        raise AssertionError("feature masks are not nested")
    return full, fair, masked


def ece(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    idx = np.clip(np.digitize(p, np.linspace(0, 1, bins + 1)[1:-1]), 0, bins - 1)
    return float(sum(np.mean(idx == b) * abs(y[idx == b].mean() - p[idx == b].mean())
                     for b in range(bins) if np.any(idx == b)))


def calibration(y, p, bins=10):
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
    return {"rows": int(len(y)), "pos": int(y.sum()), "neg": int(len(y) - y.sum()),
            "auc": float(roc_auc_score(y, p)), "logloss": float(log_loss(y, p, labels=[0, 1])),
            "brier": float(np.mean((p - y) ** 2)), "ece": ece(y, p),
            "pos_rate": float(y.mean())}


def grouped_split(seeds):
    return next(GroupShuffleSplit(1, test_size=SPLIT["test_size"],
                                  random_state=SPLIT["random_state"])
                .split(np.zeros(len(seeds)), groups=seeds))


def bootstrap_pair(y, pa, pb, run, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    y, pa, pb = map(lambda a: np.asarray(a, float), (y, pa, pb))
    pa, pb = np.clip(pa, 1e-12, 1 - 1e-12), np.clip(pb, 1e-12, 1 - 1e-12)
    la = -(y * np.log(pa) + (1 - y) * np.log1p(-pa))
    lb = -(y * np.log(pb) + (1 - y) * np.log1p(-pb))
    ba, bb = (pa - y) ** 2, (pb - y) ** 2
    nr = int(np.max(run)) + 1
    rng = np.random.default_rng(seed)
    out = {"logloss": [], "brier": [], "auc": []}
    for _ in range(n):
        weights = np.bincount(rng.integers(nr, size=nr), minlength=nr)[run]
        out["logloss"].append(float(np.average(la - lb, weights=weights)))
        out["brier"].append(float(np.average(ba - bb, weights=weights)))
        out["auc"].append(float(roc_auc_score(y, pa, sample_weight=weights)
                                - roc_auc_score(y, pb, sample_weight=weights)))
    return out


def bootstrap_all(y, preds, run, pairs, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """Bootstrap every comparison from the same contiguous seed resamples."""
    y = np.asarray(y, float)
    losses = {k: -(y * np.log(np.clip(p, 1e-12, 1 - 1e-12))
                  + (1 - y) * np.log1p(-np.clip(p, 1e-12, 1 - 1e-12)))
              for k, p in preds.items()}
    briers = {k: (np.asarray(p, float) - y) ** 2 for k, p in preds.items()}
    nr = int(np.max(run)) + 1
    rng = np.random.default_rng(seed)
    out = {f"{a} - {b}": {"logloss": [], "brier": [], "auc": []}
           for a, b in pairs}
    for _ in range(n):
        weights = np.bincount(rng.integers(nr, size=nr), minlength=nr)[run]
        aucs = {k: roc_auc_score(y, p, sample_weight=weights) for k, p in preds.items()}
        for a, b in pairs:
            row = out[f"{a} - {b}"]
            row["logloss"].append(float(np.average(losses[a] - losses[b], weights=weights)))
            row["brier"].append(float(np.average(briers[a] - briers[b], weights=weights)))
            row["auc"].append(float(aucs[a] - aucs[b]))
    return out


def summarize_boot(boot):
    return {k: {"mean": float(np.mean(v)),
                 "ci95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]}
            for k, v in boot.items()}


def fit(Xtr, ytr, Xva, yva, names, dev):
    params = {**XGB_PARAMS, "device": dev}
    dtr = xgb.QuantileDMatrix(Xtr, label=ytr, feature_names=names)
    dva = xgb.QuantileDMatrix(Xva, label=yva, ref=dtr, feature_names=names)
    model = xgb.train(params, dtr, num_boost_round=1500, evals=[(dva, "val")],
                      early_stopping_rounds=40, verbose_eval=200)
    best = int(model.best_iteration)
    return model, best, model.predict(dva, iteration_range=(0, best + 1))


def device():
    requested = os.environ.get("STS_XGB_DEVICE")
    if requested:
        return requested
    try:
        subprocess.run(["nvidia-smi"], check=True, capture_output=True)
        return "cuda"
    except (OSError, subprocess.CalledProcessError):
        return "cpu"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main():
    csv = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "build/e2b_leaf_available"
    os.makedirs(out, exist_ok=True)
    df = pd.read_csv(csv, dtype=np.float32)
    header = list(df.columns)
    required = {"seed", "won", "act", "floor", "curHp", "maxHp"}
    if required - set(header):
        raise SystemExit(f"missing columns: {sorted(required - set(header))}")
    if (df.groupby("seed")["won"].nunique() > 1).any():
        raise SystemExit("won is not constant within every seed")
    data = df.to_numpy(); del df
    col = {c: i for i, c in enumerate(header)}
    seeds = data[:, col["seed"]].astype(np.int64)
    y = data[:, col["won"]].astype(np.float32)
    tr, va = grouped_split(seeds)
    if set(seeds[tr]) & set(seeds[va]):
        raise AssertionError("group leakage")
    varying = {c for c in header if c not in LABELS and data[:, col[c]].std() > 1e-9}
    full, fair, masked_features = feature_sets(header, varying)
    manifest_rows = manifest(header)
    with open(os.path.join(out, "feature_manifest.csv"), "w") as f:
        f.write("feature,family,fair_observable,raw_terminal_stable,reason,source_symbol\n")
        for r in manifest_rows:
            f.write(",".join(str(r[k]) for k in ("feature", "family", "fair_observable",
                                                   "raw_terminal_stable", "reason", "source_symbol")) + "\n")
    dev = device()
    hpfrac = data[:, col["curHp"]] / np.maximum(data[:, col["maxHp"]], 1)
    b1 = np.column_stack([data[:, col["curHp"]], data[:, col["maxHp"]], hpfrac,
                          data[:, col["act"]], data[:, col["floor"]]]).astype(np.float32)
    preds = {"B0": np.full(len(va), float(y[tr].mean()), dtype=np.float32)}
    best = {}
    for name, features, matrix in (("B1", B1_FEATURES, b1), ("T-full", full, None),
                                   ("T-fair", fair, None), ("T-masked", masked_features, None)):
        if matrix is None:
            matrix = data[:, [col[c] for c in features]].astype(np.float32)
        model, best[name], preds[name] = fit(matrix[tr], y[tr], matrix[va], y[va], features, dev)
        model.save_model(os.path.join(out, name.lower().replace("-", "_") + "_model.json"))
    metrics_out = {name: metrics(y[va], p) for name, p in preds.items()}
    val_runs = np.unique(seeds[va], return_inverse=True)[1]
    pairs = (("T-full", "B1"), ("T-fair", "B1"), ("T-masked", "B1"),
             ("T-fair", "T-full"), ("T-masked", "T-fair"))
    comparisons = {name: summarize_boot(values)
                   for name, values in bootstrap_all(y[va], preds, val_runs, pairs).items()}
    gain_full = metrics_out["B1"]["logloss"] - metrics_out["T-full"]["logloss"]
    gain_fair = metrics_out["B1"]["logloss"] - metrics_out["T-fair"]["logloss"]
    gain_masked = metrics_out["B1"]["logloss"] - metrics_out["T-masked"]["logloss"]
    retention = {"gain_full": gain_full, "gain_fair": gain_fair, "gain_masked": gain_masked,
                 "fair_retention": gain_fair / gain_full if gain_full > 0 else None,
                 "masked_retention": gain_masked / gain_full if gain_full > 0 else None}
    masked = metrics_out["T-masked"]
    checks = {"logloss_below_B1": masked["logloss"] < metrics_out["B1"]["logloss"],
              "brier_below_B1": masked["brier"] < metrics_out["B1"]["brier"],
              "auc_above_B1": masked["auc"] > metrics_out["B1"]["auc"],
              "bootstrap_logloss_ci_favorable": comparisons["T-masked - B1"]["logloss"]["ci95"][1] < 0,
              "ece_le_0.10": masked["ece"] <= 0.10,
              "masked_retention_ge_0.50": retention["masked_retention"] is not None and retention["masked_retention"] >= 0.50}
    primary_checks = ("logloss_below_B1", "brier_below_B1", "auc_above_B1")
    verdict = "MASKED SUPPORT" if all(checks.values()) else ("MASKED INCONCLUSIVE" if all(checks[k] for k in primary_checks) else "MASKED NEGATIVE")
    with open(os.path.join(out, "calibration_deciles.csv"), "w") as f:
        f.write("model,bin_lo,bin_hi,n,mean_pred,observed\n")
        for name, p in preds.items():
            for r in calibration(y[va], p):
                f.write(name + "," + ",".join(str(r[k]) for k in ("bin_lo", "bin_hi", "n", "mean_pred", "observed")) + "\n")
    np.savez_compressed(os.path.join(out, "validation_predictions.npz"), seed=seeds[va], y=y[va], **{k.replace("-", "_"): v for k, v in preds.items()})
    result = {"experiment": "E2b masked post-combat run-win diagnostic", "dataset": os.path.abspath(csv),
              "dataset_sha256": sha256(csv), "boundary": "after forced gold/relic/potion pickup before card pick/skip",
              "primary_subset": "all represented card-reward rows; exact ordinary-combat subset unavailable",
              "rows": int(len(y)), "seeds": int(len(np.unique(seeds))), "wins": int(y.sum()), "losses": int(len(y) - y.sum()),
              "heldout_rows": int(len(va)), "heldout_seeds": int(len(np.unique(seeds[va]))), "train_seeds": int(len(np.unique(seeds[tr]))),
              "features": {"B1": len(B1_FEATURES), "T-full": len(full), "T-fair": len(fair), "T-masked": len(masked_features)},
              "feature_lists": {"T-full": full, "T-fair": fair, "T-masked": masked_features}, "metrics": metrics_out,
              "best_iteration": best, "split": SPLIT, "xgb_params": {**XGB_PARAMS, "device": dev},
              "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "unit": "held-out seed", "comparisons": comparisons},
              "retention": retention, "checks": checks, "verdict": verdict,
              "counter_diagnostic": "NOT TESTABLE FROM E2 DATASET: relic columns combine ownership/counter and pickup can add relics",
              "limitations": ["no room/encounter identifier", "post-reward capture prevents exact raw-boundary confirmation"],
              "provenance": {"git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "source": "apps/one_combat.cpp::vFeatCsv/richRow/richHeader"}}
    for name, payload in (("metrics.json", result), ("provenance.json", result["provenance"])):
        with open(os.path.join(out, name), "w") as f:
            json.dump(payload, f, indent=2)
    with open(os.path.join(out, "sha256sums.txt"), "w") as f:
        for name in sorted(os.listdir(out)):
            if name != "sha256sums.txt":
                f.write(f"{sha256(os.path.join(out, name))}  {name}\n")
    print(json.dumps({"verdict": verdict, "features": result["features"], "metrics": metrics_out, "retention": retention}, indent=2))


if __name__ == "__main__":
    main()