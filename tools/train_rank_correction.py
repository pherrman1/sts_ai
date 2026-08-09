#!/usr/bin/env python3
"""Zero-mean ranking correction model for the combat leaf value (experimental).

Trains a SMALL standalone XGBoost model to predict the residual between a
high-budget Searcher3 reference evaluation and the deployed end-HP vnet's
prediction on the same leaf state:

    residual = leafref.referenceValue - leafdiag.endHp_pred

The residuals are CENTERED to zero-mean within each (seed, fightIdx, decIdx)
decision group before training, so the model learns a scale-neutral ranking
correction: at inference the correction is ADDED on top of the primary
vnet/PVNet leaf value (`BattleScumSearcher3::evaluateLeaf` /
`BattleScumSearcher2::evaluateLeafState`, plus the S3 leaf-blend site), and
the fair-path search-complete zero-mean clamp
(`clampRankCorrAtRoot`) guarantees the HP scale is preserved. The correction
model is a standalone diagnostic/experimental arm only: `STS_VNET_RANK_CORR`
is off by default and nothing is promoted without a paired gameplay gate.

Recipe (deliberately shallower than the deployed vnet):
  * same combat-feature layout as the deployed vnet — the std>1e-9 filter is
    applied on combatgen rows (default `build/vcombat_honest.csv`, the §126
    corpus that yields the deployed 733-feature layout), NOT on leafdiag rows;
  * max_depth=6, eta=0.05, subsample=0.8, colsample_bytree=0.7,
    min_child_weight=20, 100 rounds, 20-round early stopping;
  * fight-group GroupShuffleSplit (test_size=0.15, random_state=0) with
    groups = seed*1000+fightIdx (same fight-group split as
    `train_value_combat.py`).

Exports the compact-tree artifact via `export_combat_model.py::export_trees`
and writes a parity CSV (canonical combat features + pyPred) for
`one_combat vnettest`. Reports validation RMSE/MAE and within-group ranking
metrics (pairwise accuracy, top-1, regret — `tools/leaf_ranking.py` internals)
on held-out fight groups.

Usage:
  python3 tools/train_rank_correction.py \
      --leafdiag-csv build/leafdiag_gate_64.csv \
      --leafref-csv build/leafref_gate_64_4k.csv \
      --model-out build/v_rank_corr.json
  # fast smoke: add --smoke-rows 5000 --smoke-rounds 10
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

# Allow running as `python3 tools/train_rank_correction.py` from the repo
# root: the script's own directory (tools/) is sys.path[0], and the repo-root
# modules below live one level up.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
import export_combat_model                       # noqa: E402  (export_trees)
import tools.leaf_ranking as leaf_ranking        # noqa: E402  (group_pairwise)

PAIR_EPS = 1e-6
META_COLS = ("seed", "fightIdx", "decIdx", "floor", "act", "encounterName",
             "treeDepth", "obsHash", "nLegalActions", "stratum", "fightWon",
             "fightEndHp", "endHp_pred", "utilityR_pred", "rawRolloutEval",
             "blendedEval")


def get_model_features(combatgen_csv):
    """Deployed-vnet feature layout: columns of a combatgen CSV excluding the
    label columns, filtered by std>1e-9 on the combatgen rows (NOT leafdiag
    rows — the correction must reuse the vnet's feature set exactly)."""
    hdr = pd.read_csv(combatgen_csv, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16)
              for c in hdr}
    df = pd.read_csv(combatgen_csv, dtype=dtypes)
    feats = [c for c in df.columns
             if c not in ("seed", "fightIdx", "won", "endHp")
             and df[c].std() > 1e-9]
    del df
    return feats


def load_leafref_map(leafref_csv):
    """(seed, fightIdx, decIdx, obsHash) -> mean finite referenceValue.
    Keys are the same pipe-joined strings used by join_leafdiag_leafref."""
    lr = pd.read_csv(leafref_csv)
    keep = lr[["seed", "fightIdx", "decIdx", "obsHash", "referenceValue"]]
    keep = keep[np.isfinite(keep["referenceValue"].to_numpy(np.float64))]
    agg = keep.groupby(["seed", "fightIdx", "decIdx", "obsHash"],
                       sort=False)["referenceValue"].mean()
    out = {}
    for (seed, fi, di, oh), v in agg.items():
        out[f"{seed}|{fi}|{di}|{oh}"] = float(v)
    return out


def join_leafdiag_leafref(leafdiag_csv, leafref_csv, seed_range):
    """Join leafdiag rows to leafref references on (seed, fightIdx, decIdx,
    obsHash); residual = referenceValue - endHp_pred. Returns a DataFrame with
    the leafdiag rows that have both a finite reference and a finite base
    prediction."""
    print(f"loading leafdiag {leafdiag_csv} ...", flush=True)
    ld = pd.read_csv(leafdiag_csv)
    if seed_range:
        ld = ld[ld["seed"].isin(seed_range)].reset_index(drop=True)
        print(f"  {len(ld)} leaves from seeds {min(seed_range)}-{max(seed_range)}",
              flush=True)
    refs = load_leafref_map(leafref_csv)

    # Composite key for a fast join: a string key is magnitude-safe for the
    # large seed values used by the leafdiag corpora.
    key = (ld["seed"].astype(str) + "|" + ld["fightIdx"].astype(str)
           + "|" + ld["decIdx"].astype(str) + "|" + ld["obsHash"].astype(str))
    key_arr = key.to_numpy()
    ref_vals = np.array([refs.get(k, np.nan) for k in key_arr], dtype=np.float64)

    base = ld["endHp_pred"].to_numpy(np.float64)
    finite = np.isfinite(ref_vals) & np.isfinite(base)
    if not finite.any():
        print("  WARNING: no leafdiag rows joined to a leafref reference "
              "(check the join keys / env match)", flush=True)
    out = ld[finite].copy().reset_index(drop=True)
    out["referenceValue"] = ref_vals[finite]
    out["residual"] = out["referenceValue"].to_numpy(np.float64) - base[finite]
    print(f"  {len(out)} leaves joined with a finite reference (of {len(ld)}); "
          f"raw residual mean {out['residual'].mean():.3f} "
          f"std {out['residual'].std():.3f}", flush=True)
    return out


def center_residuals(ld):
    """Zero-mean the residual within each (seed, fightIdx, decIdx) decision
    group (the runtime clamp enforces the same property per search)."""
    g = ld.groupby(["seed", "fightIdx", "decIdx"], sort=False)["residual"]
    means = g.transform("mean").to_numpy(np.float64)
    centered = ld["residual"].to_numpy(np.float64) - means
    ld["centeredResidual"] = centered
    n_groups = ld.groupby(["seed", "fightIdx", "decIdx"], sort=False).ngroups
    print(f"  centered residual within {n_groups} decision groups "
          f"(mean {centered.mean():.3f} std {centered.std():.3f})", flush=True)
    return ld


def ranking_metrics(groups):
    """leaf_ranking-style within-decision-group ranking metrics (scale
    invariant): pooled pairwise accuracy, top-1 accuracy, mean regret.
    Returns (metrics dict, nPairs)."""
    pair_correct = pair_total = 0
    top1_ok = 0
    top1_n = 0
    regrets = []
    for idx in groups:
        refs = np.array(groups[idx]["referenceValue"], dtype=np.float64)
        preds = np.array(groups[idx]["pred"], dtype=np.float64)
        c, t, _ = leaf_ranking.group_pairwise(list(refs), list(preds))
        pair_correct += c
        pair_total += t
        imax_ref = int(np.argmax(refs))
        imax_pred = int(np.argmax(preds))
        top1_ok += 1 if imax_pred == imax_ref else 0
        top1_n += 1
        regrets.append(float(refs[imax_ref] - refs[imax_pred]))
    m = {"pairwiseAcc": (pair_correct / pair_total) if pair_total else float("nan"),
         "pairs": int(pair_total),
         "top1": (top1_ok / top1_n) if top1_n else float("nan"),
         "regret": float(np.mean(regrets)) if regrets else float("nan")}
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leafdiag-csv", default="build/leafdiag_gate_64.csv")
    ap.add_argument("--leafref-csv", default="build/leafref_gate_64_4k.csv")
    ap.add_argument("--combatgen-csv", default="build/vcombat_honest.csv",
                    help="combatgen CSV for the std>1e-9 feature filter "
                         "(the deployed-vnet layout source)")
    ap.add_argument("--model-out", default="build/v_rank_corr.json")
    ap.add_argument("--rounds", type=int, default=100)
    ap.add_argument("--eta", type=float, default=0.05)
    ap.add_argument("--train-seeds", default="", help="e.g. 126700-126747")
    ap.add_argument("--eval-seeds", default="", help="e.g. 126748-126763")
    ap.add_argument("--smoke-rows", type=int, default=0,
                    help="cap the joined training rows (fast smoke)")
    ap.add_argument("--smoke-rounds", type=int, default=0,
                    help="cap boosting rounds (fast smoke)")
    ap.add_argument("--parity-rows", type=int, default=200,
                    help="rows in the vnettest parity CSV")
    args = ap.parse_args()

    def parse_range(s):
        if not s:
            return None
        lo, hi = s.split("-")
        return list(range(int(lo), int(hi) + 1))

    train_seeds = parse_range(args.train_seeds)
    eval_seeds = parse_range(args.eval_seeds)

    t0 = time.time()
    # 1. join leafdiag <-> leafref, residual = ref - base endHp prediction
    ld = join_leafdiag_leafref(args.leafdiag_csv, args.leafref_csv, train_seeds)
    if args.smoke_rows > 0 and len(ld) > args.smoke_rows:
        ld = ld.head(args.smoke_rows).reset_index(drop=True)
        print(f"  smoke: capped to {len(ld)} rows", flush=True)
    if len(ld) < 64:
        print("ERROR: too few joined rows to train (check the leafdiag/leafref "
              "seed overlap and the run-env match)", file=sys.stderr)
        return 2

    # 2. zero-mean the residual within each decision group
    ld = center_residuals(ld)
    if eval_seeds:
        eval_mask = ld["seed"].isin(eval_seeds).to_numpy()
    else:
        eval_mask = None

    # 3. feature layout: the deployed-vnet 733 features (combatgen std filter)
    print(f"loading combatgen feature layout {args.combatgen_csv} ...", flush=True)
    model_feats = get_model_features(args.combatgen_csv)
    print(f"  {len(model_feats)} model features (combatgen std>1e-9 filter)",
          flush=True)
    feat_cols = [f for f in model_feats if f in ld.columns]
    missing = set(model_feats) - set(feat_cols)
    if missing:
        print(f"  WARNING: {len(missing)} model features missing from leafdiag: "
              f"{sorted(missing)[:8]} ...", flush=True)
    print(f"  {len(feat_cols)}/{len(model_feats)} features aligned with leafdiag",
          flush=True)

    # 4. fight-group split (same as train_value_combat.py), with an optional
    #    explicit eval-seed holdout for the seed-blocked leafdiag convention
    y = ld["centeredResidual"].to_numpy(np.float32)
    X = ld[feat_cols].to_numpy(np.float32)
    fight_group = (ld["seed"].to_numpy(np.int64) * 1000
                   + ld["fightIdx"].to_numpy(np.int64))
    if eval_mask is not None:
        tr = np.flatnonzero(~eval_mask)
        va = np.flatnonzero(eval_mask)
    else:
        tr, va = next(GroupShuffleSplit(
            1, test_size=0.15, random_state=0).split(X, y, groups=fight_group))
    print(f"train {len(tr)} rows / val {len(va)} rows "
          f"({len(np.unique(fight_group[tr]))} vs "
          f"{len(np.unique(fight_group[va]))} fights)", flush=True)

    # 5. train the small correction model
    dtr = xgb.DMatrix(X[tr], label=y[tr], feature_names=feat_cols)
    dva = xgb.DMatrix(X[va], label=y[va], feature_names=feat_cols)
    params = dict(objective="reg:squarederror", tree_method="hist",
                  device=os.environ.get("STS_XGB_DEVICE")
                  or ("cuda" if os.path.exists("/usr/bin/nvidia-smi") else "cpu"),
                  max_depth=6, eta=args.eta, subsample=0.8,
                  colsample_bytree=0.7, min_child_weight=20, max_bin=256)
    rounds = args.rounds if args.smoke_rounds <= 0 else min(args.rounds,
                                                            args.smoke_rounds)
    print(f"training {rounds} rounds (eta {args.eta}, device {params['device']}) "
          f"...", flush=True)
    bst = xgb.train(params, dtr, num_boost_round=rounds, evals=[(dva, "val")],
                    early_stopping_rounds=20, verbose_eval=50)
    best = bst.best_iteration
    pv = bst.predict(dva, iteration_range=(0, best + 1))
    val_rmse = float(np.sqrt(np.mean((y[va] - pv) ** 2)))
    val_mae = float(np.mean(np.abs(y[va] - pv)))
    print(f"  val RMSE {val_rmse:.3f} / MAE {val_mae:.3f} on the centered "
          f"residual (best_iter {best})", flush=True)

    # 6. save JSON + export compact trees (export_combat_model.py)
    out_json = args.model_out
    if out_json.endswith(".json"):
        out_txt = out_json[:-5] + ".txt"
    else:   # model-out named .txt (or bare): the JSON is a temporary intermediate
        out_txt = out_json
        out_json = os.path.splitext(out_json)[0] + ".json"
    bst.save_model(out_json)
    print(f"saved booster -> {out_json}", flush=True)
    bst2, feats2, ntrees, base_score = export_combat_model.export_trees(
        out_json, out_txt)
    print(f"  -> {out_txt} ({ntrees} trees, base_score {base_score})", flush=True)

    # 7. parity CSV for `one_combat vnettest`: canonical combat features (in
    #    combatFeatureNames() order = the leafdiag feature block order) + pyPred
    canon_cols = [c for c in ld.columns if c not in META_COLS + ("residual",
                                                                 "centeredResidual",
                                                                 "referenceValue")]
    parity = ld.sample(frac=1, random_state=1).head(args.parity_rows).copy()
    Xpar = parity[feat_cols].to_numpy(np.float32)
    parity["pyPred"] = bst2.predict(xgb.DMatrix(Xpar, feature_names=feat_cols),
                                    iteration_range=(0, ntrees))
    parity_csv = os.path.splitext(out_txt)[0] + "_parity.csv"
    parity[list(canon_cols) + ["pyPred"]].to_csv(parity_csv, index=False)
    print(f"  -> {parity_csv} ({len(parity)} rows, {len(canon_cols)} canonical "
          f"features)", flush=True)

    # 8. held-out ranking metrics: corrected = endHp_pred + corr_pred vs the
    #    raw reference, within decision groups (leaf_ranking semantics)
    corr_pred = bst2.predict(xgb.DMatrix(X, feature_names=feat_cols),
                             iteration_range=(0, ntrees))
    ld["corrPred"] = corr_pred
    ld["pred"] = ld["endHp_pred"].to_numpy(np.float64) + corr_pred
    def eval_groups(col):
        agg = {}
        val_fights = np.unique(fight_group[va])
        for key, sub in ld[np.isin(fight_group, val_fights)].groupby(
                ["seed", "fightIdx", "decIdx"], sort=False):
            if len(sub) < 2:
                continue
            refs = sub["referenceValue"].to_numpy(np.float64)
            preds = sub[col].to_numpy(np.float64)
            good = np.isfinite(refs) & np.isfinite(preds)
            if good.sum() < 2:
                continue
            agg[key] = {"referenceValue": refs[good], "pred": preds[good]}
        return ranking_metrics(agg)
    m_base = eval_groups("endHp_pred")
    m_corr = eval_groups("pred")
    print(f"\nHeld-out (fight-group val) within-decision ranking vs leafref:")
    print(f"  baseline endHp_pred: pairwiseAcc {m_base['pairwiseAcc']:.4f} "
          f"({m_base['pairs']} pairs) top1 {m_base['top1']:.4f} "
          f"regret {m_base['regret']:.3f}")
    print(f"  corrected           : pairwiseAcc {m_corr['pairwiseAcc']:.4f} "
          f"({m_corr['pairs']} pairs) top1 {m_corr['top1']:.4f} "
          f"regret {m_corr['regret']:.3f}")
    print(f"  delta pairwiseAcc {m_corr['pairwiseAcc'] - m_base['pairwiseAcc']:+.4f} "
          f"top1 {m_corr['top1'] - m_base['top1']:+.4f} "
          f"regret {m_corr['regret'] - m_base['regret']:+.3f}")
    # raw-residual fit (RMSE/MAE of the correction vs the UNCENTERED residual)
    raw_rmse = float(np.sqrt(np.mean((ld["residual"].to_numpy(np.float64)
                                      - corr_pred) ** 2)))
    raw_mae = float(np.mean(np.abs(ld["residual"].to_numpy(np.float64)
                                   - corr_pred)))
    print(f"  correction fit vs RAW residual: RMSE {raw_rmse:.3f} / "
          f"MAE {raw_mae:.3f} (raw residual std "
          f"{ld['residual'].std():.3f})", flush=True)

    metrics = {
        "leafdiag": args.leafdiag_csv,
        "leafref": args.leafref_csv,
        "combatgen_features": args.combatgen_csv,
        "rows": int(len(ld)),
        "val_rows": int(len(va)),
        "features": list(feat_cols),
        "params": params,
        "num_boost_round": int(rounds),
        "early_stopping_rounds": 20,
        "best_iteration": int(best),
        "validation": {
            "rmse_centered_residual": val_rmse,
            "mae_centered_residual": val_mae,
            "rmse_raw_residual": raw_rmse,
            "mae_raw_residual": raw_mae,
        },
        "ranking": {
            "baseline": m_base,
            "corrected": m_corr,
        },
        "model_txt": out_txt,
        "parity_csv": parity_csv,
    }
    metrics_path = os.path.splitext(out_json)[0] + "_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"metrics -> {metrics_path}", flush=True)
    print(f"total {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
