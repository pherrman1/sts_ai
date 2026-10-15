"""A20 card ranker on floor reached: offline test.

Plan: docs/experiments/evidence/a20_card_floor_20261009/PLAN.md. Reuses the E3
loader, data rules and split from `tools.vwin_e3_cf`. Trains XGBoost regressors
on `horizonFloor` from the X2-B public map-row features and scores, on
VALIDATION card-reward states, the floor gain of each arm's argmax option over
V4's chosen option. Early stopping uses an inner TRAIN-source set; TEST is
never read for scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from tools.vwin_e3_cf import HIDDEN_FUTURE, X2B_RECIPE, KEYS, apply_rules, cluster_mean, load, load_trees

TARGET = "horizonFloor"


def inner(seed: int) -> bool:
    return int(hashlib.sha256(f"a20-card-floor-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32 < 0.2


def half(seed: int) -> bool:
    return int(hashlib.sha256(f"a20-card-floor-half-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32 < 0.5


def train(Xt, yt, wt, Xe, ye, we, names, seed, threads, rounds):
    import xgboost as xgb
    params = dict(objective="reg:squarederror", eval_metric="rmse", tree_method="hist", device="cpu",
                  subsample=.8, colsample_bytree=.7, max_bin=256, nthread=threads, seed=seed, **X2B_RECIPE)
    dt = xgb.DMatrix(Xt, label=yt, weight=wt, feature_names=list(names))
    de = xgb.DMatrix(Xe, label=ye, weight=we, feature_names=list(names))
    booster = xgb.train(params, dt, num_boost_round=rounds, evals=[(de, "inner")],
                        early_stopping_rounds=50, verbose_eval=False)
    try:
        count = booster.best_iteration + 1
    except AttributeError:
        count = booster.num_boosted_rounds()
    return booster[:count], count


def selection(part, col):
    rows = []
    for (seed, d), g in part.groupby(["sourceSeed", "decisionIdx"]):
        per = g.groupby("optionIdx").agg(score=(col, "mean"), floor=(TARGET, "mean"),
                                         chosen=("chosen", "max"), key=("optionKey", "first"))
        if len(per) < 2 or per["chosen"].sum() != 1:
            continue
        top = np.isclose(per["score"], per["score"].max(), rtol=0, atol=1e-12)
        base = float(per.loc[per["chosen"] == 1, "floor"].iloc[0])
        skip = per["key"].str.contains("effect=12:").to_numpy()
        rows.append(dict(seed=int(seed), gain=float(per["floor"][top].mean()) - base,
                         oracle=float(per["floor"].max()) - base, uniform=float(per["floor"].mean()) - base,
                         agrees=bool(top.sum() == 1 and per["chosen"].to_numpy()[top][0] == 1),
                         picks_skip=float(skip[top].mean()), v4_skip=bool(skip[per["chosen"].to_numpy() == 1][0])))
    return rows


def summary(rows, key, reps, baseline=None):
    vals = [r[key] - (b[key] if baseline else 0.0) for r, b in zip(rows, baseline or rows)]
    res = cluster_mean(vals, [r["seed"] for r in rows], reps)
    res["agree_with_v4"] = float(np.mean([r["agrees"] for r in rows]))
    res["picks_skip"] = float(np.mean([r["picks_skip"] for r in rows]))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--smoke", action="store_true", help="20 rounds")
    ap.add_argument("--win-bonus", type=float, default=0.0,
                    help="post-hoc: target and score floor + BONUS * finalWon (default 0 = plan)")
    args = ap.parse_args()
    import xgboost as xgb
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    lab, mp, manifests = load(args.root)
    df, dropped = apply_rules(lab, mp)
    if args.win_bonus:
        df[TARGET] = df[TARGET].astype(float) + args.win_bonus * df["finalWon"].astype(float)
    df = df[df["type"].isin(["CARD_REWARD", "BOSS_RELIC"])].copy()
    names, x2b = load_trees()
    public = [n for n in names if n not in HIDDEN_FUTURE]
    Xm = df[names].to_numpy(np.float64, copy=True)
    Xm[:, [names.index(n) for n in HIDDEN_FUTURE]] = -1
    df["X2B"] = x2b(Xm)
    X = df[public].to_numpy(np.float32)
    y = df[TARGET].to_numpy(np.float32)
    state = df.groupby(["sourceSeed", "decisionIdx"]).ngroup().to_numpy()
    w = 1.0 / np.bincount(state)[state]
    w *= len(w) / w.sum()   # mean 1, as E3: min_child_weight is in these units (§405 review)
    seeds_src = df["sourceSeed"].astype(int).to_numpy()
    is_card = (df["type"] == "CARD_REWARD").to_numpy()
    train_src = (df["split"] == "TRAIN").to_numpy()
    in_inner = np.array([inner(s) for s in seeds_src])
    in_half = np.array([half(s) for s in seeds_src])
    fit, stop = train_src & ~in_inner, train_src & in_inner
    arms = {"CARD": fit & is_card, "ALL": fit, "CARD_50": fit & is_card & in_half}
    trained = []
    for arm, sel in arms.items():
        es = stop & is_card
        preds = []
        for s in [int(v) for v in args.seeds.split(",")]:
            booster, count = train(X[sel], y[sel], w[sel], X[es], y[es], w[es], public, s, args.threads,
                                   20 if args.smoke else 2500)
            preds.append(booster.predict(xgb.DMatrix(X, feature_names=public)))
            trained.append(dict(arm=arm, seed=s, trees=count, rows=int(sel.sum()),
                                sources=int(len(set(seeds_src[sel])))))
            booster.save_model(out / f"{arm}-s{s}.ubj")
        df[arm] = np.mean(preds, axis=0)
    part = df[(df["split"] == "VALIDATION") & (df["type"] == "CARD_REWARD")]
    cols = ["CARD", "ALL", "CARD_50", "X2B"]
    sel_rows = {c: selection(part, c) for c in cols}
    results = {c: dict(gain=summary(sel_rows[c], "gain", args.reps),
                       rmse=float(np.sqrt(np.mean((part[c] - part[TARGET]) ** 2))) if c != "X2B" else None)
               for c in cols}
    results["CARD_minus_X2B"] = summary(sel_rows["CARD"], "gain", args.reps, sel_rows["X2B"])
    results["CARD_minus_CARD_50"] = summary(sel_rows["CARD"], "gain", args.reps, sel_rows["CARD_50"])
    results["oracle"] = summary(sel_rows["CARD"], "oracle", args.reps)
    results["uniform_random"] = summary(sel_rows["CARD"], "uniform", args.reps)
    results["v4_skip_rate"] = float(np.mean([r["v4_skip"] for r in sel_rows["CARD"]]))
    lo = results["CARD"]["gain"]["ci95"][0]
    report = dict(schema="a20_card_floor_v1", root=str(Path(args.root).resolve()),
                  producer_git=sorted({m["git"] for m in manifests}),
                  producer_exe=sorted({m["exe"] for m in manifests}), parts=len(manifests),
                  dropped_state_k_groups=dropped,
                  card_states_by_split=df[is_card].drop_duplicates(["sourceSeed", "decisionIdx"])
                  .groupby("split").size().to_dict(),
                  inner_card_states=int(df[stop & is_card].drop_duplicates(["sourceSeed", "decisionIdx"]).shape[0]),
                  trained=trained, results=results, test_opened=False,
                  verdict="PASS" if lo > 0 else "NOT_SHOWN", win_bonus=args.win_bonus, seconds=time.time() - t0)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    part[KEYS + ["optionKey", "chosen", TARGET] + cols].to_csv(out / "validation_predictions.csv", index=False)
    print("VERDICT", report["verdict"], json.dumps(results["CARD"]["gain"]))


if __name__ == "__main__":
    main()
