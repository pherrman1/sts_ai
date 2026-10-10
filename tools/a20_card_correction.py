"""A20 card correction on top of the teacher's pick: offline test.

Plan: docs/experiments/evidence/a20_card_floor_20261009/PLAN-CORRECTION.md.
Predicts, per non-chosen card-reward option, the paired floor difference to the
teacher's chosen option (shared futures) and switches only when the best
predicted difference is positive. Same loader, rules, split and inner early-stop
set as tools.a20_card_floor; boss card rewards whose map row is in a later act
are dropped. TEST is scored only with --open-test.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from tools.a20_card_floor import inner, train
from tools.vwin_e3_cf import HIDDEN_FUTURE, apply_rules, cluster_mean, load, load_trees

TARGET = "horizonFloor"


def prepare(root):
    lab, mp, manifests = load(root)
    df, dropped = apply_rules(lab, mp)
    df = df[df["type"] == "CARD_REWARD"].copy()
    names, _ = load_trees()
    public = [n for n in names if n not in HIDDEN_FUTURE]
    state = ["sourceSeed", "decisionIdx"]
    leak = df.groupby(state)["mapAct"].transform(lambda s: s.astype(int)) != df["lab_act"].astype(int)
    leaky = df.loc[leak, state].drop_duplicates()
    df = df.merge(leaky.assign(_leak=1), on=state, how="left")
    df = df[df["_leak"].isna()].drop(columns="_leak")
    nchosen = df.groupby(state)["chosen"].transform(lambda s: s.groupby(df.loc[s.index, "optionIdx"]).max().sum())
    nopt = df.groupby(state)["optionIdx"].transform("nunique")
    df = df[(nchosen == 1) & (nopt >= 2)].copy()
    ch = df[df["chosen"] == 1][state + ["k", TARGET] + public].rename(
        columns={TARGET: "chosenFloor", **{c: "ch_" + c for c in public}})
    alt = df[df["chosen"] == 0].merge(ch, on=state + ["k"], how="inner", validate="many_to_one")
    alt["d"] = alt[TARGET].astype(float) - alt["chosenFloor"].astype(float)
    diff = alt[public].to_numpy(np.float32) - alt[["ch_" + c for c in public]].to_numpy(np.float32)
    X = np.concatenate([alt[public].to_numpy(np.float32), diff], axis=1)
    feats = public + ["diff_" + c for c in public]
    return alt.reset_index(drop=True), X, feats, manifests, dropped, len(leaky)


def evaluate(part, pred_col, reps, rng_seed=0):
    rows = []
    for (seed, d), g in part.groupby(["sourceSeed", "decisionIdx"]):
        per = g.groupby("optionIdx").agg(pred=(pred_col, "mean"), d=("d", "mean"))
        best = per["pred"].idxmax()
        switch = per.loc[best, "pred"] > 0
        rows.append(dict(seed=int(seed), gain=float(per.loc[best, "d"]) if switch else 0.0, switch=bool(switch),
                         oracle=max(0.0, float(per["d"].max())), rand_alt=float(per["d"].mean())))
    seeds = [r["seed"] for r in rows]
    rate = float(np.mean([r["switch"] for r in rows]))
    return dict(states=len(rows), switch_rate=rate,
                gain=cluster_mean([r["gain"] for r in rows], seeds, reps),
                oracle=cluster_mean([r["oracle"] for r in rows], seeds, reps),
                random_alt_same_rate=cluster_mean([rate * r["rand_alt"] for r in rows], seeds, reps),
                random_alt_always=cluster_mean([r["rand_alt"] for r in rows], seeds, reps))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--smoke", action="store_true", help="20 rounds")
    ap.add_argument("--open-test", action="store_true", help="only after PASS_VALIDATION (plan)")
    args = ap.parse_args()
    import xgboost as xgb
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    alt, X, feats, manifests, dropped, leaky = prepare(args.root)
    y = alt["d"].to_numpy(np.float32)
    state = alt.groupby(["sourceSeed", "decisionIdx"]).ngroup().to_numpy()
    w = 1.0 / np.bincount(state)[state]
    w *= len(w) / w.sum()
    src = alt["sourceSeed"].astype(int).to_numpy()
    tr = (alt["split"] == "TRAIN").to_numpy()
    stop = tr & np.array([inner(s) for s in src])
    fit = tr & ~stop
    preds, trained = [], []
    for s in [int(v) for v in args.seeds.split(",")]:
        booster, count = train(X[fit], y[fit], w[fit], X[stop], y[stop], w[stop], feats, s, args.threads,
                               20 if args.smoke else 2500)
        preds.append(booster.predict(xgb.DMatrix(X, feature_names=feats)))
        trained.append(dict(seed=s, trees=count, rows=int(fit.sum())))
        booster.save_model(out / f"CORR-s{s}.ubj")
    alt["CORR"] = np.mean(preds, axis=0)
    results = {"VALIDATION": evaluate(alt[alt["split"] == "VALIDATION"], "CORR", args.reps)}
    lo = results["VALIDATION"]["gain"]["ci95"][0]
    verdict = "PASS_VALIDATION" if lo > 0 else "NOT_SHOWN"
    if args.open_test:
        if verdict != "PASS_VALIDATION":
            raise SystemExit("plan: TEST opens only after PASS_VALIDATION")
        results["TEST"] = evaluate(alt[alt["split"] == "TEST"], "CORR", args.reps)
        verdict = "PASS" if results["TEST"]["gain"]["ci95"][0] > 0 else "VALIDATION_ONLY"
    report = dict(schema="a20_card_correction_v1", root=str(Path(args.root).resolve()),
                  producer_git=sorted({m["git"] for m in manifests}),
                  producer_exe=sorted({m["exe"] for m in manifests}), parts=len(manifests),
                  dropped_state_k_groups=dropped, leaky_states_dropped=leaky,
                  states_by_split=alt.drop_duplicates(["sourceSeed", "decisionIdx"]).groupby("split").size().to_dict(),
                  trained=trained, results=results, test_opened=args.open_test, verdict=verdict,
                  seconds=time.time() - t0)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    alt[alt["split"] != "TEST"][["sourceSeed", "decisionIdx", "optionIdx", "k", "split", "d", "CORR"]].to_csv(
        out / "predictions.csv", index=False)
    print("VERDICT", verdict, json.dumps(results["VALIDATION"]))


if __name__ == "__main__":
    main()
