#!/usr/bin/env python3
"""GPU XGBoost combat value function V_combat(combat_state) -> fight label,
trained on a MIXTURE of on-policy combatgen snapshots PLUS actual Searcher3
search-leaf states, with SEPARATE on-policy and search-leaf holdouts.

Pre-registered covariate-shift mixture retrain (EXPERIMENTS.md §135a verdict,
decision log 2026-08-08-leaf-state-diagnostics.md "Results addendum"):
  - Source 1 (on-policy): build/vcombat_honest.csv — the §126 training set
    (combatgen seeds 0-1499).
  - Source 2 (search-leaf): build/leafdiag_gate_64.csv — the §135a leafdiag
    dataset (seeds 126700-126763); ONLY train seeds 126700-126747 (48 seeds)
    enter training/validation. Eval seeds 126748-126763 (16 seeds) are held
    out ENTIRELY and asserted absent from every training row.
Splits (per source, by fight group):
  - combatgen: GroupShuffleSplit(test_size=0.15, random_state=0,
    groups=(seed,fightIdx)) -> ON-POLICY holdout (val_cg).
  - leafdiag (train seeds only): the same fight-group split inside the 48
    train seeds -> SEARCH-LEAF holdout (val_ld).
Training set = combatgen train fights + leafdiag train-seed train fights.

The training label is the fight outcome (endHp / won) for BOTH sources — the
leafref reference values are vnet-influenced approximations and are NEVER
training labels.

Model recipe is the canonical §126 recipe byte-for-byte with
train_value_combat.py: VCOMBAT_TARGET=endhp (default; utility_r supported via
the same env var for symmetry), max_depth=8, eta=0.05, subsample=0.8,
colsample_bytree=0.7, min_child_weight=20, max_bin=256, num_boost_round=1500,
early_stopping_rounds=40, critical-state weights, device = cuda when
nvidia-smi is present (STS_XGB_DEVICE overrides). Validation metrics are
reported PER REGIME (on-policy val vs search-leaf val) against BOTH label
scales (endHp and utility R with VCOMBAT_WIN_BONUS=50), matching
train_value_combat.py semantics.

This is a diagnostic artifact only: no default change, no promotion, no C++
change. Output: <model-out> (xgboost JSON) + <model-out-stem>_metrics.json.

Usage:
  python3 tools/train_value_mixture.py [--combatgen-csv CSV] [--leafdiag-csv CSV]
      [--model-out PATH] [--policy-csv PATH] [--smoke-rows N] [--smoke-rounds N]
"""
import sys, os, json, shutil, argparse, gc
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

# Leafdiag CSV columns that are provenance/diagnostic only (never features):
LD_DIAG_COLS = ["decIdx", "floor", "act", "encounterName", "treeDepth",
                "obsHash", "nLegalActions", "stratum", "endHp_pred",
                "utilityR_pred", "rawRolloutEval", "blendedEval"]
# Pre-registered seed split of the §135a leafdiag dataset:
LD_TRAIN_SEED_MIN = 126700
LD_TRAIN_SEED_MAX = 126747   # 48 train seeds
LD_EVAL_SEED_MIN  = 126748
LD_EVAL_SEED_MAX  = 126763   # 16 eval seeds, held out ENTIRELY


def read_combatgen_csv(path, nrows=None):
    """Read the combatgen CSV (seed/fightIdx/won/endHp + 1766 features)."""
    _hdr = pd.read_csv(path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
    df = pd.read_csv(path, dtype=dtypes, nrows=nrows)
    return df, list(df.columns)


def read_leafdiag_csv(path, nrows=None):
    """Read the leafdiag CSV; drop diagnostic/metadata columns; rename
    fightWon->won, fightEndHp->endHp so the frame matches the combatgen schema
    exactly (seed/fightIdx + 1766 features + won/endHp)."""
    _hdr = pd.read_csv(path, nrows=0).columns
    keep = [c for c in _hdr if c not in LD_DIAG_COLS]
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in keep}
    df = pd.read_csv(path, dtype=dtypes, nrows=nrows)
    df = df.drop(columns=[c for c in LD_DIAG_COLS if c in df.columns])
    df = df.rename(columns={"fightWon": "won", "fightEndHp": "endHp"})
    return df, list(df.columns)


def prepare_source(df, policy_rows):
    """Canonical §126 per-source arrays: critical-state weight, fight group,
    endHp label, won, hp_frac, enc_fail, disagreement. Mirrors
    train_value_combat.py exactly (weight formula, mean normalization, key
    construction); POLICY_CSV unset -> disagreement stays zero."""
    N = len(df)
    group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
    won = df["won"].to_numpy(np.float32)
    hp_frac = (df["curHp"].to_numpy(np.float32)
               / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
    fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(["seed", "fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
    decision = df.groupby(["seed", "fightIdx"], sort=False).cumcount().to_numpy(np.int64)
    decision_key = (df["seed"].to_numpy(np.int64) * 100000
                    + df["fightIdx"].to_numpy(np.int64) * 1000 + decision)
    disagreement = np.zeros(N, dtype=np.float32)
    matched_disagreement = 0
    if policy_rows is not None:
        pg = policy_rows.groupby("_key", sort=False).agg(
            best=("visit", "max"), total=("total", "first"))
        ambiguity = (1.0 - pg["best"] / np.maximum(pg["total"], 1)).astype(np.float32)
        mapped = pd.Series(decision_key).map(ambiguity)
        present = mapped.notna().to_numpy()
        disagreement[present] = mapped[present].to_numpy(np.float32)
        matched_disagreement = int(present.sum())
    weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
              + 1.5 * enc_fail + 1.5 * disagreement)
    weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
    weight /= weight.mean()
    endhp = df["endHp"].to_numpy(np.float32)
    return (weight, group, endhp, won, hp_frac, enc_fail, disagreement,
            matched_disagreement)


def regime_metrics(bst, dval, target_val, endhp_val, won_val, best, win_bonus):
    """RMSE/MAE vs endHp AND vs utility R (0 on loss, win_bonus+endHp on win)
    for one validation regime; r2 is vs the training target label."""
    pv = bst.predict(dval, iteration_range=(0, best + 1))
    R = np.where(won_val >= 0.5, np.float32(win_bonus) + endhp_val,
                 np.float32(0.0)).astype(np.float32)
    return {
        "rows": int(len(endhp_val)),
        "rmse_vs_endhp": float(np.sqrt(((endhp_val - pv) ** 2).mean())),
        "mae_vs_endhp": float(np.abs(endhp_val - pv).mean()),
        "rmse_vs_utility_r": float(np.sqrt(((R - pv) ** 2).mean())),
        "mae_vs_utility_r": float(np.abs(R - pv).mean()),
        "r2_vs_target": float(r2_score(target_val, pv)),
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--combatgen-csv", default="build/vcombat_honest.csv")
    ap.add_argument("--leafdiag-csv", default="build/leafdiag_gate_64.csv")
    ap.add_argument("--model-out", default="build/v_combat_mix.json")
    ap.add_argument("--policy-csv", default="",
                    help="optional teacher disagreement CSV (canonical recipe; "
                         "unset for the pre-registered run)")
    ap.add_argument("--smoke-rows", type=int, default=0,
                    help="read only the first N rows per source (smoke)")
    ap.add_argument("--smoke-rounds", type=int, default=0,
                    help="override num_boost_round (smoke)")
    args = ap.parse_args(argv)

    TARGET = (os.environ.get("VCOMBAT_TARGET") or "endhp").strip().lower()
    if TARGET not in ("endhp", "utility_r"):
        raise SystemExit(f"VCOMBAT_TARGET must be 'endhp' or 'utility_r', got {TARGET!r}")
    WIN_BONUS = float(os.environ.get("VCOMBAT_WIN_BONUS", "50"))
    LABEL_NAME = "utility R" if TARGET == "utility_r" else "endHp"
    NROUNDS = args.smoke_rounds or 1500
    nrows = args.smoke_rows or None
    if args.smoke_rows > 0:
        print(f"SMOKE MODE: first {args.smoke_rows} rows per source, "
              f"{NROUNDS} boost rounds", flush=True)

    # ---- teacher disagreement (optional; unset for the pre-registered run) ----
    policy_rows = None
    if args.policy_csv and os.path.exists(args.policy_csv):
        print(f"loading teacher disagreement from {args.policy_csv} ...", flush=True)
        p = pd.read_csv(args.policy_csv,
                        usecols=["seed", "fightIdx", "decIdx", "visit", "total"],
                        dtype={"seed": np.int32, "fightIdx": np.int32,
                               "decIdx": np.int32, "visit": np.int32,
                               "total": np.int32})
        p["_key"] = (p["seed"].to_numpy(np.int64) * 100000
                     + p["fightIdx"].to_numpy(np.int64) * 1000
                     + p["decIdx"].to_numpy(np.int64))
        policy_rows = p
        del p
    elif args.policy_csv:
        print(f"WARNING: POLICY_CSV {args.policy_csv} missing; teacher "
              "disagreement stays zero", flush=True)

    # ---- combatgen source (on-policy) ----
    print(f"loading {args.combatgen_csv} ...", flush=True)
    df_cg, header_cg = read_combatgen_csv(args.combatgen_csv, nrows=nrows)
    N_cg = len(df_cg)
    cg_feats = [c for c in header_cg if c not in ("seed", "fightIdx", "won", "endHp")]
    X_cg = df_cg[cg_feats].to_numpy(np.float32)
    (w_cg, g_cg, endhp_cg, won_cg, hp_cg, ef_cg, dis_cg, mdis_cg) = \
        prepare_source(df_cg, policy_rows)
    print(f"combatgen rows {N_cg}, fights {len(np.unique(g_cg))}, "
          f"features {len(cg_feats)}", flush=True)
    del df_cg; gc.collect()

    # ---- leafdiag source (search-leaf, train seeds only) ----
    print(f"loading {args.leafdiag_csv} ...", flush=True)
    df_ld, _ = read_leafdiag_csv(args.leafdiag_csv, nrows=nrows)
    N_ld_all = len(df_ld)
    ld_feats = [c for c in df_ld.columns if c not in ("seed", "fightIdx", "won", "endHp")]
    assert ld_feats == cg_feats, (
        "leafdiag feature block must equal combatgen canonical features; "
        f"got {len(ld_feats)} vs {len(cg_feats)}")
    # Held-out eval seeds: counted, then filtered OUT of every training row.
    ld_eval_mask = ((df_ld["seed"] >= LD_EVAL_SEED_MIN)
                    & (df_ld["seed"] <= LD_EVAL_SEED_MAX))
    N_ld_eval = int(ld_eval_mask.sum())
    df_ld = df_ld[~ld_eval_mask].reset_index(drop=True)
    ld_train_mask = ((df_ld["seed"] >= LD_TRAIN_SEED_MIN)
                     & (df_ld["seed"] <= LD_TRAIN_SEED_MAX))
    assert bool(ld_train_mask.all()), (
        "leafdiag rows outside the pre-registered train seed range "
        f"[{LD_TRAIN_SEED_MIN},{LD_TRAIN_SEED_MAX}] would enter training: "
        f"{sorted(df_ld[~ld_train_mask]['seed'].unique().tolist())}")
    N_ld = len(df_ld)
    print(f"leafdiag rows {N_ld_all}; eval-seed rows held out {N_ld_eval} "
          f"(seeds {LD_EVAL_SEED_MIN}-{LD_EVAL_SEED_MAX}); train-seed rows "
          f"{N_ld}", flush=True)
    X_ld = df_ld[ld_feats].to_numpy(np.float32)
    (w_ld, g_ld, endhp_ld, won_ld, hp_ld, ef_ld, dis_ld, mdis_ld) = \
        prepare_source(df_ld, policy_rows)
    print(f"leafdiag train-seed rows {N_ld}, fights {len(np.unique(g_ld))}",
          flush=True)
    del df_ld; gc.collect()

    # ---- canonical feature filter (std > 1e-9), computed on the COMBATGEN
    # source exactly like the canonical §126 recipe (train_value_combat.py
    # filters its input CSV). The resulting set is the deployed model's own
    # feature set (733 for vcombat_honest.csv), so the mixture model is
    # directly comparable to v_combat_honest.txt — the training mixture is
    # the only difference. Filtering on the concatenated frame instead would
    # add/remove features because the 64-seed leafdiag slice has different
    # variance (e.g. 750 features) and break that comparability.
    all_feats = cg_feats
    feat_cols = [f for i, f in enumerate(all_feats) if X_cg[:, i].std() > 1e-9]
    print(f"feature filter (combatgen-derived, canonical §126): kept "
          f"{len(feat_cols)}/{len(all_feats)} features (deployed "
          f"v_combat_honest.txt uses the same combatgen-derived set)",
          flush=True)
    fpos = [all_feats.index(f) for f in feat_cols]
    X_cg, X_ld = X_cg[:, fpos], X_ld[:, fpos]

    # ---- labels (canonical endHp objective; utility_r for symmetry) ----
    if TARGET == "utility_r":
        y_cg = np.where(won_cg >= 0.5, np.float32(WIN_BONUS) + endhp_cg,
                        np.float32(0.0)).astype(np.float32)
        y_ld = np.where(won_ld >= 0.5, np.float32(WIN_BONUS) + endhp_ld,
                        np.float32(0.0)).astype(np.float32)
    else:
        y_cg, y_ld = endhp_cg, endhp_ld

    # ---- pre-registered per-source fight-group splits ----
    tr_cg, va_cg = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
                        .split(X_cg, groups=g_cg))
    tr_ld, va_ld = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
                        .split(X_ld, groups=g_ld))
    N_train = len(tr_cg) + len(tr_ld)
    print(f"split: combatgen train {len(tr_cg)} / on-policy val {len(va_cg)}; "
          f"leafdiag train {len(tr_ld)} / search-leaf val {len(va_ld)}; "
          f"mixture training rows {N_train}", flush=True)

    Xtr = np.concatenate([X_cg[tr_cg], X_ld[tr_ld]], axis=0)
    ytr = np.concatenate([y_cg[tr_cg], y_ld[tr_ld]], axis=0)
    wtr = np.concatenate([w_cg[tr_cg], w_ld[tr_ld]], axis=0)
    # validation matrices (per regime) must exist before we free the sources
    dtr = xgb.QuantileDMatrix(Xtr, label=ytr, weight=wtr, feature_names=feat_cols)
    dva_cg = xgb.QuantileDMatrix(X_cg[va_cg], label=y_cg[va_cg],
                                 weight=w_cg[va_cg], ref=dtr,
                                 feature_names=feat_cols)
    dva_ld = xgb.QuantileDMatrix(X_ld[va_ld], label=y_ld[va_ld],
                                 weight=w_ld[va_ld], ref=dtr,
                                 feature_names=feat_cols)
    endhp_cg_va = endhp_cg[va_cg]; won_cg_va = won_cg[va_cg]
    endhp_ld_va = endhp_ld[va_ld]; won_ld_va = won_ld[va_ld]
    del X_cg, X_ld; gc.collect()

    print(f"V_combat mixture: {N_train} training rows, {len(feat_cols)} "
          f"features; target {LABEL_NAME} (VCOMBAT_TARGET={TARGET}) "
          f"mean {ytr.mean():.1f} std {ytr.std():.1f}", flush=True)
    print(f"critical weighting: min {wtr.min():.2f} mean {wtr.mean():.2f} "
          f"max {wtr.max():.2f}; teacher disagreement matched "
          f"{mdis_cg + mdis_ld}/{N_train} rows", flush=True)

    DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
    params = dict(objective="reg:squarederror", tree_method="hist", device=DEVICE,
                  max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
                  min_child_weight=20, max_bin=256)
    print(f"training on {DEVICE} ...", flush=True)
    # Early stopping uses the LAST evals entry = the on-policy (combatgen
    # holdout) regime, i.e. the same stopping signal as the canonical §126
    # recipe; both regimes are reported separately regardless.
    bst = xgb.train(params, dtr, num_boost_round=NROUNDS,
                    evals=[(dva_ld, "search_leaf_val"), (dva_cg, "on_policy_val")],
                    early_stopping_rounds=40, verbose_eval=100)
    best = bst.best_iteration
    print(f"\nbest_iteration {best}", flush=True)

    # ---- per-regime validation metrics (the decisive offline evidence) ----
    m_on_policy = regime_metrics(bst, dva_cg, y_cg[va_cg], endhp_cg_va,
                                 won_cg_va, best, WIN_BONUS)
    m_search_leaf = regime_metrics(bst, dva_ld, y_ld[va_ld], endhp_ld_va,
                                   won_ld_va, best, WIN_BONUS)
    print("\n=== ON-POLICY val (combatgen holdout fights) ===", flush=True)
    print(f"  val RMSE/MAE vs endHp: {m_on_policy['rmse_vs_endhp']:.2f}/"
          f"{m_on_policy['mae_vs_endhp']:.2f}  "
          f"vs utility R: {m_on_policy['rmse_vs_utility_r']:.2f}/"
          f"{m_on_policy['mae_vs_utility_r']:.2f}  "
          f"(rows {m_on_policy['rows']})", flush=True)
    print("=== SEARCH-LEAF val (leafdiag train-seed holdout fights) ===",
          flush=True)
    print(f"  val RMSE/MAE vs endHp: {m_search_leaf['rmse_vs_endhp']:.2f}/"
          f"{m_search_leaf['mae_vs_endhp']:.2f}  "
          f"vs utility R: {m_search_leaf['rmse_vs_utility_r']:.2f}/"
          f"{m_search_leaf['mae_vs_utility_r']:.2f}  "
          f"(rows {m_search_leaf['rows']})", flush=True)
    base_rmse = float(np.sqrt(((endhp_cg_va - ytr.mean()) ** 2).mean()))
    print(f"  on-policy predict-mean RMSE reference: {base_rmse:.2f}",
          flush=True)
    critical = ((hp_cg[va_cg] < 0.35) | (won_cg_va < 0.5) | (ef_cg[va_cg] >= 0.20))
    if critical.any():
        pv_cg = bst.predict(dva_cg, iteration_range=(0, best + 1))
        print(f"  on-policy critical-state val RMSE "
              f"{float(np.sqrt(((endhp_cg_va[critical] - pv_cg[critical]) ** 2).mean())):.2f} "
              f"on {int(critical.sum())}/{len(va_cg)} rows", flush=True)

    bst.save_model(args.model_out)
    print(f"saved -> {args.model_out}", flush=True)

    # ---- metrics sidecar (target semantics + split + per-regime metrics) ----
    metrics = {
        "task": "covariate-shift mixture retrain (EXPERIMENTS.md §137)",
        "target": TARGET,
        "target_label_name": LABEL_NAME,
        "win_bonus": WIN_BONUS,
        "combatgen_csv": args.combatgen_csv,
        "leafdiag_csv": args.leafdiag_csv,
        "rows": {
            "combatgen": int(N_cg),
            "leafdiag_all": int(N_ld_all),
            "leafdiag_eval_seed_held_out": int(N_ld_eval),
            "leafdiag_train_seed": int(N_ld),
            "train_total": int(N_train),
        },
        "fights": {
            "combatgen": int(len(np.unique(g_cg))),
            "leafdiag_train_seed": int(len(np.unique(g_ld))),
        },
        "split": {
            "combatgen": {"test_size": 0.15, "random_state": 0,
                          "method": "GroupShuffleSplit", "groups": "(seed,fightIdx)"},
            "leafdiag_train_seeds": {"seed_range": [LD_TRAIN_SEED_MIN, LD_TRAIN_SEED_MAX],
                                     "test_size": 0.15, "random_state": 0,
                                     "method": "GroupShuffleSplit",
                                     "groups": "(seed,fightIdx)"},
            "leafdiag_eval_seeds_held_out": [LD_EVAL_SEED_MIN, LD_EVAL_SEED_MAX],
        },
        "device": DEVICE,
        "features": list(feat_cols),
        "params": params,
        "num_boost_round": NROUNDS,
        "early_stopping_rounds": 40,
        "best_iteration": int(best),
        "validation": {
            "on_policy": m_on_policy,
            "search_leaf": m_search_leaf,
        },
    }
    metrics_path = os.path.splitext(args.model_out)[0] + "_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"metrics -> {metrics_path}", flush=True)

    # feature importance (gain)
    imp = bst.get_score(importance_type="gain")
    top = sorted(imp.items(), key=lambda x: -x[1])[:18]
    print("\nTop features by gain:")
    for k, v in top:
        print(f"   {k:<14s} {v:8.1f}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
