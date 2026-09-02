#!/usr/bin/env python3
"""Train the V1 signed combat evaluator with fixed XGBoost heads."""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from combat_evaluator_contract import validate_csv, sha256, SCHEMA_VERSION

def stable_split(seeds):
    # Stable across later seed blocks; no random reshuffling of old sources.
    groups = {}
    for seed in sorted(set(int(x) for x in seeds)):
        h = int(hashlib.sha256(f"combat-evaluator-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32
        groups[seed] = "train" if h < .70 else "validation" if h < .85 else "test"
    if len(groups) < 4 or len(set(groups.values())) < 3: raise ValueError("grouped split needs at least four seeds across three splits")
    return groups

def reg(y, p):
    e = np.asarray(p) - np.asarray(y)
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt(np.mean(e*e)))}

def binary(y, p):
    from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
    return {"logloss": float(log_loss(y, p, labels=[0, 1])), "brier": float(brier_score_loss(y, p)),
            "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None}

def calibration(y, p):
    return [{"bin": i, "n": int(((p >= i/10) & (p < (i+1)/10 if i < 9 else p <= 1)).sum()),
             "pred": float(p[((p >= i/10) & (p < (i+1)/10 if i < 9 else p <= 1))].mean()),
             "observed": float(np.asarray(y)[((p >= i/10) & (p < (i+1)/10 if i < 9 else p <= 1))].mean())}
            for i in range(10) if ((p >= i/10) & (p < (i+1)/10 if i < 9 else p <= 1)).any()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("output")
    ap.add_argument("--rounds", type=int, default=300); ap.add_argument("--max-depth", type=int, default=6)
    ap.add_argument("--eta", type=float, default=.05); ap.add_argument("--threads", type=int, default=1)
    args = ap.parse_args(); info = validate_csv(args.csv); df = pd.read_csv(args.csv)
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    state = info["features"]
    encounters = sorted(df.encounter.astype(str).unique())
    enc_cols = [f"encounter__{x}" for x in encounters]
    for x, c in zip(encounters, enc_cols): df[c] = (df.encounter.astype(str) == x).astype(float)
    all_features = state + enc_cols
    groups = stable_split(df.sourceSeed)
    split = df.sourceSeed.map(groups); train = split.eq("train"); val = split.eq("validation"); test = split.eq("test")
    variance = df.loc[train, all_features].var(ddof=0)
    features = [c for c in all_features if variance[c] > 1e-12]
    if not features: raise ValueError("no nonconstant TRAIN features")
    valid = df.labelValid.eq(1) & (df.won.eq(1) | df.trueDeath.eq(1))
    if not valid[train].any(): raise ValueError("TRAIN has no valid outcomes")
    import xgboost as xgb
    params = {"max_depth": args.max_depth, "eta": args.eta, "subsample": .8, "colsample_bytree": .8,
              "seed": 20260902, "nthread": args.threads}
    def fit(mask, label, objective):
        return xgb.train({**params, "objective": objective, "eval_metric": "logloss" if objective == "binary:logistic" else "rmse"},
                          xgb.DMatrix(df.loc[mask, features], label=df.loc[mask, label]), num_boost_round=args.rounds)
    survival = fit(train & valid, "won", "binary:logistic")
    wh = train & valid & df.won.eq(1)
    ld = train & valid & df.trueDeath.eq(1) & ~df.progressAmbiguous.eq(1)
    if not wh.any() or not ld.any(): raise ValueError("TRAIN lacks winners or unambiguous deaths")
    win_hp = fit(wh, "winHpFrac", "reg:squarederror")
    loss_rem = fit(ld, "lossRemainingFrac", "reg:squarederror")
    dm = xgb.DMatrix(df.loc[test, features]); p = np.clip(survival.predict(dm), 0, 1)
    winp = np.clip(win_hp.predict(dm), 1e-3, 1); lossp = np.clip(loss_rem.predict(dm), 1e-3, 1)
    score = np.where(p >= .5, winp, -lossp); expected = p*winp - (1-p)*lossp
    testdf = df.loc[test].copy(); testdf["p_win"] = p; testdf["predicted_win_hp_frac"] = winp; testdf["predicted_loss_remaining_frac"] = lossp; testdf["score"] = score; testdf["expected_score"] = expected
    testdf.to_csv(out / "heldout_predictions.csv", index=False)
    y = testdf.won.to_numpy(); prior = float(df.loc[train & valid, "won"].mean())
    wh_t = test & valid & df.won.eq(1); ld_t = test & valid & df.trueDeath.eq(1) & ~df.progressAmbiguous.eq(1)
    signed = test & valid
    sign_pred = (score >= 0).astype(int); sign_true = (testdf.signedOutcome.to_numpy() >= 0).astype(int)
    metrics = {"survival": {"model": binary(y, p), "train_prior_baseline": binary(y, np.full(len(y), prior)), "calibration": calibration(y, p), "train_win_prior": prior},
               "conditional_win_hp": {"model": reg(df.loc[wh_t, "winHpFrac"], winp[wh_t[test].to_numpy()]), "train_winner_mean_baseline": reg(df.loc[wh_t, "winHpFrac"], np.full(wh_t.sum(), df.loc[wh, "winHpFrac"].mean()))},
               "conditional_loss_remaining": {"model": reg(df.loc[ld_t, "lossRemainingFrac"], lossp[ld_t[test].to_numpy()]), "train_death_mean_baseline": reg(df.loc[ld_t, "lossRemainingFrac"], np.full(ld_t.sum(), df.loc[ld, "lossRemainingFrac"].mean()))},
               "expected_signed_score": {"model": reg(df.loc[signed, "signedOutcome"], expected[signed[test].to_numpy()]), "train_signed_mean_baseline": reg(df.loc[signed, "signedOutcome"], np.full(signed.sum(), df.loc[train & valid, "signedOutcome"].mean()))},
               "thresholded_score": {"accuracy": float((sign_pred == sign_true).mean()), "confusion": [[int(((sign_true == a) & (sign_pred == b)).sum()) for b in (0, 1)] for a in (0, 1)]},
               "counts": {"rows": len(df), "source_seeds": int(df.sourceSeed.nunique()), "train": int(train.sum()), "validation": int(val.sum()), "test": int(test.sum()), "valid_deaths": int((valid & df.trueDeath).sum()), "valid_nonambiguous_deaths": int((valid & df.trueDeath & ~df.progressAmbiguous.eq(1)).sum()), "ambiguous": int(df.progressAmbiguous.sum())},
               "split_membership": {k: sorted(int(s) for s,v in groups.items() if v == k) for k in ("train", "validation", "test")}}
    survival.save_model(out / "survival.json"); win_hp.save_model(out / "conditional_win_hp.json"); loss_rem.save_model(out / "conditional_loss_remaining.json")
    manifest = {"schema_version": SCHEMA_VERSION, "data_sha256": sha256(args.csv), "csv": {"path": str(Path(args.csv).resolve()), "sha256": sha256(args.csv)},
                "producer_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "seed_spec": {"group_key": "sourceSeed"},
                "models": {n: sha256(out / f) for n,f in (("survival", "survival.json"), ("conditional_win_hp", "conditional_win_hp.json"), ("conditional_loss_remaining", "conditional_loss_remaining.json"))},
                "feature_contract": {"count": 1017, "state_names": state, "encounters": encounters, "model_features": features, "one_hot": True, "order_hash": hashlib.sha256("\n".join(state + enc_cols).encode()).hexdigest()},
                "teacher": sorted(df.teacherId.astype(str).unique().tolist()), "integrity": info["counts"], "training_parameters": vars(args), "metrics": metrics}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metrics, indent=2, sort_keys=True))
if __name__ == "__main__": main()
