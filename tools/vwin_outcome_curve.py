"""Step 0 of the OOC self-play question: does the outcome-trained leaf pick better with more games?

Offline, TRAIN/VALIDATION only, no gameplay. Pre-registration:
docs/experiments/evidence/ooc_outcome_curve_20261009/PREREG.md.

The X2-B recipe (P0 in tools.vwin_e1_focal: public 457 features, weights 1,
early stopping on #334 VALIDATION) is retrained on nested fractions 1/8, 1/4,
1/2, 1/1 of the 696 #334 TRAIN sources, in two corpora:

- SRC: rows of the source trajectories only (branchId == "source"), i.e. what
  N games of own play with run-victory labels give;
- ALL: source plus counterfactual branch rows (the X2-B training set).

Each arm's prediction is the probability mean over the seeds. Evaluation:
- #334 VALIDATION map-row NLL;
- selection gain vs V4's chosen option on #334 VALIDATION sampled decisions
  (tools.vwin_e1_focal.selection_gain) and on E3 VALIDATION states
  (tools.vwin_e3_cf.selection_rows), plus the E3 skip-pick share;
- per-doubling slope: for each decision, the least-squares slope of its gain on
  log2(fraction) over the four fractions; source-clustered bootstrap of the mean.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

FRACTIONS = (0.125, 0.25, 0.5, 1.0)
CORPORA = ("SRC", "ALL")
SEP = 10 ** 9   # E3 seeds (55M) and #334 seeds (13M) never collide; kept apart in clusters anyway


def curve_order(sources):
    return sorted(sources, key=lambda s: hashlib.sha256(f"outcome-curve-v1:{int(s)}".encode()).hexdigest())


def slope_weights(fractions=FRACTIONS):
    x = np.log2(np.asarray(fractions, float))
    d = x - x.mean()
    return d / (d ** 2).sum()


def slope_rows(rows_by_fraction, fractions=FRACTIONS):
    """Per-decision least-squares slope of gain on log2(fraction); rows must align."""
    w = slope_weights(fractions)
    base = rows_by_fraction[fractions[0]]
    for f in fractions:
        if [(r["seed"], r["type"]) for r in rows_by_fraction[f]] != [(r["seed"], r["type"]) for r in base]:
            raise ValueError("selection rows do not align across fractions")
    out = []
    for i, r in enumerate(base):
        out.append(dict(seed=r["seed"], type=r["type"],
                        slope=float(sum(wk * rows_by_fraction[f][i]["gain"] for wk, f in zip(w, fractions)))))
    return out


def summarize_key(rows, key, reps, types=None):
    from tools.vwin_e3_cf import cluster_mean
    groups = {}
    for r in rows:
        if types is None or r["type"] in types:
            groups.setdefault(r["type"], []).append(r)
            groups.setdefault("pooled", []).append(r)
    return {t: cluster_mean([r[key] for r in g], [r["seed"] for r in g], reps) for t, g in sorted(groups.items())}


def train_p0(Xt, yt, Xv, yv, names, seed, threads, max_rounds=2500):
    import xgboost as xgb
    from tools.vwin_e1_focal import X2B_RECIPE
    from tools.vwin_refresh_training import xgb_parameters
    params = {**xgb_parameters(names, monotone=True, threads=threads), **X2B_RECIPE, "seed": seed}
    dt = xgb.DMatrix(Xt, label=yt, feature_names=list(names))
    dv = xgb.DMatrix(Xv, label=yv, feature_names=list(names))
    booster = xgb.train(params, dt, num_boost_round=max_rounds, evals=[(dv, "validation")],
                        early_stopping_rounds=50, verbose_eval=False)
    try:
        count = booster.best_iteration + 1
    except AttributeError:
        count = booster.num_boosted_rounds()
    return booster[:count], count


def decide(slopes, skip, margin=0.005):
    """Pre-registered rule on the SRC corpus (PREREG.md).

    GO: on either evaluation set the pooled slope per doubling is >= margin
    with 95% CI lower > 0, and the E3 card-reward skip share at 1/1 is below
    1/8. STOP: on both sets the CI upper bound is < margin. Else INCONCLUSIVE.
    """
    pooled = [s["pooled"] for s in slopes.values()]
    if any(p["ci95"] is None for p in pooled):
        return "INCONCLUSIVE"
    if any(p["mean"] >= margin and p["ci95"][0] > 0 for p in pooled) and skip[1.0] < skip[0.125]:
        return "GO"
    if all(p["ci95"][1] < margin for p in pooled):
        return "STOP"
    return "INCONCLUSIVE"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("index", help="#334 corpus index (corpus-mixed-1024.json)")
    ap.add_argument("e3_root", help="E3 part directory (ooccfpilotgen GEN=2 outputs)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--smoke", type=int, help="load N #334 components per split, 20 rounds")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))
    import xgboost as xgb
    from tools.vwin_e1_focal import focal_rows, load_split_tables, selection_gain
    from tools.vwin_e3_cf import HIDDEN_FUTURE, apply_rules, load, load_trees, metrics, selection_rows
    t0 = time.time()
    names, x2b = load_trees()
    public = [n for n in names if n not in HIDDEN_FUTURE]
    if len(names) != 461 or len(public) != 457:
        raise ValueError("unexpected X2-B feature set")
    data = load_split_tables(args.index, names, smoke=args.smoke)
    cols = [names.index(n) for n in public]
    tr, va = data["TRAIN"], data["VALIDATION"]
    tr["Xp"] = np.ascontiguousarray(tr.pop("X")[:, cols])
    va["Xp"] = np.ascontiguousarray(va["X"][:, cols])
    va["focal_idx"] = focal_rows(va["seed"], va["branch"], va["row"], va["branches"])
    x2b_nll = metrics(va["y"], x2b(va["X"]))["nll"]
    lab, mp, manifests = load(args.e3_root)
    e3, dropped = apply_rules(lab, mp)
    e3 = e3[e3["split"] == "VALIDATION"].reset_index(drop=True)
    Xe3 = e3[public].to_numpy(np.float32)
    is_src = tr["branch"] == "source"
    order = curve_order(np.unique(tr["seed"]))
    log = dict(rows_train=int(len(tr["y"])), rows_train_src=int(is_src.sum()), rows_val=int(len(va["y"])),
               train_sources=len(order), val_branches=len(va["branches"]), e3_val_rows=int(len(e3)),
               e3_dropped_state_k_groups=dropped, x2b_validation_nll=x2b_nll,
               e3_producer_git=sorted({m["git"] for m in manifests}), load_seconds=time.time() - t0)
    print(json.dumps(log), flush=True)
    seeds = [int(s) for s in args.seeds.split(",")]
    trained, results, gains334, gainsE3 = [], {}, {}, {}
    for corpus in CORPORA:
        for f in FRACTIONS:
            keep = set(order[:max(1, int(round(f * len(order))))])
            sel = np.isin(tr["seed"], list(keep)) & (is_src if corpus == "SRC" else True)
            pv, pe = [], []
            for s in seeds:
                booster, count = train_p0(tr["Xp"][sel], tr["y"][sel], va["Xp"], va["y"], public, s, args.threads,
                                          20 if args.smoke else 2500)
                pv.append(booster.predict(xgb.DMatrix(va["Xp"], feature_names=public)))
                pe.append(booster.predict(xgb.DMatrix(Xe3, feature_names=public)))
                info = dict(corpus=corpus, fraction=f, seed=s, sources=len(keep), rows=int(sel.sum()), trees=count)
                trained.append(info)
                print(json.dumps(info), flush=True)
            pv, pe = np.mean(pv, axis=0), np.mean(pe, axis=0)
            e3[f"{corpus}_{f}"] = pe
            rows334, _ = selection_gain(va["branches"], va["focal_idx"], pv)
            rowsE3 = selection_rows(e3, f"{corpus}_{f}")
            for r in rowsE3:
                r["seed"] += SEP
            gains334[(corpus, f)], gainsE3[(corpus, f)] = rows334, rowsE3
            results[f"{corpus}_{f}"] = dict(
                sources=len(keep), rows=int(sel.sum()), nll334=metrics(va["y"], pv)["nll"],
                gain334=summarize_key(rows334, "gain", args.reps),
                gainE3=summarize_key(rowsE3, "gain", args.reps),
                e3_card_skip=float(np.mean([r["picks_skip"] for r in rowsE3 if r["type"] == "CARD_REWARD"])),
                e3_boss_skip=float(np.mean([r["picks_skip"] for r in rowsE3 if r["type"] == "BOSS_RELIC"])))
    slopes = {}
    for corpus in CORPORA:
        s334 = slope_rows({f: gains334[(corpus, f)] for f in FRACTIONS})
        sE3 = slope_rows({f: gainsE3[(corpus, f)] for f in FRACTIONS})
        slopes[corpus] = dict(eval334=summarize_key(s334, "slope", args.reps),
                              evalE3=summarize_key(sE3, "slope", args.reps),
                              combined=summarize_key(s334 + sE3, "slope", args.reps))
    skip = {f: results[f"SRC_{f}"]["e3_card_skip"] for f in FRACTIONS}
    verdict = decide({"eval334": slopes["SRC"]["eval334"], "evalE3": slopes["SRC"]["evalE3"]}, skip)
    report = dict(schema="vwin_outcome_curve_v1", smoke=args.smoke, fractions=FRACTIONS, seeds=seeds,
                  log=log, trained=trained, results=results, slopes=slopes, verdict_src=verdict,
                  references=dict(oracle334=summarize_key(gains334[("ALL", 1.0)], "oracle", args.reps),
                                  uniform334=summarize_key(gains334[("ALL", 1.0)], "uniform", args.reps),
                                  oracleE3=summarize_key(gainsE3[("ALL", 1.0)], "oracle", args.reps),
                                  uniformE3=summarize_key(gainsE3[("ALL", 1.0)], "uniform", args.reps)),
                  e1_p0_anchor=dict(trees=[278, 355, 373], val_nll=0.4237, note="ALL_1.0 should be close"),
                  seconds=time.time() - t0, test_opened=False)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    print("VERDICT", verdict)
    print("DONE", out / "report.json", flush=True)


if __name__ == "__main__":
    main()
