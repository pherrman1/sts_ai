#!/usr/bin/env python3
"""Ranking fine-tuning for the VNet XGBoost model.

Fine-tunes the endHp regression model on Searcher3 leaf states (leafdiag)
with leafref high-budget reference values as the regression target. The
base model predicts endHp; new trees learn corrections toward the leafref
value, improving leaf-state ranking without losing the HP prediction scale.

Usage:
  python3 tools/train_vnet_ranking.py --rounds 200 --eta 0.005
"""
import sys, os, json, argparse, time, subprocess
import numpy as np
import pandas as pd
import xgboost as xgb

PAIR_EPS = 1e-6


def load_leafdiag(leafdiag_path, leafref_path, seed_range):
    """Load leafdiag features + leafref labels for a seed block."""
    print(f"Loading leafdiag {leafdiag_path} ...", flush=True)
    ld = pd.read_csv(leafdiag_path)
    ld = ld[ld["seed"].isin(seed_range)].copy().reset_index(drop=True)
    print(f"  {len(ld)} leaves from seeds {min(seed_range)}-{max(seed_range)}", flush=True)

    print(f"Loading leafref {leafref_path} ...", flush=True)
    lr = pd.read_csv(leafref_path)
    lr = lr[lr["seed"].isin(seed_range)]
    lr_agg = lr.groupby(["seed","fightIdx","decIdx","obsHash"])["referenceValue"].mean()
    lr_map = {k: float(v) for k, v in lr_agg.items() if not np.isnan(v)}

    refs = np.full(len(ld), np.nan, dtype=np.float64)
    has_ref = np.zeros(len(ld), dtype=bool)
    for i, row in ld.iterrows():
        key = (int(row["seed"]), int(row["fightIdx"]), int(row["decIdx"]), int(row["obsHash"]))
        val = lr_map.get(key)
        if val is not None:
            refs[i] = val
            has_ref[i] = True
    ld = ld[has_ref].copy().reset_index(drop=True)
    refs = refs[has_ref]
    print(f"  {len(ld)} leaves have reference values", flush=True)

    # Feature columns
    meta_cols = ["seed","fightIdx","decIdx","floor","act","encounterName",
                 "treeDepth","obsHash","nLegalActions","stratum","fightWon",
                 "fightEndHp","endHp_pred","utilityR_pred","rawRolloutEval","blendedEval"]
    feat_cols_leaf = [c for c in ld.columns if c not in meta_cols]

    # Align with model feature set
    model_feats = get_model_features()
    common = [f for f in model_feats if f in feat_cols_leaf]
    missing = set(model_feats) - set(common)
    if missing:
        print(f"  WARNING: {len(missing)} model features missing from leafdiag")
    X = ld[common].to_numpy(np.float32)
    print(f"  {len(common)}/{len(model_feats)} features aligned", flush=True)

    # Create groups
    ld["_gk"] = (ld["seed"].astype(str) + "_" + ld["fightIdx"].astype(str) +
                 "_" + ld["decIdx"].astype(str))
    group_keys = ld["_gk"].to_numpy()
    unique = {}
    qid = np.zeros(len(ld), dtype=np.int64)
    for i, gk in enumerate(group_keys):
        if gk not in unique:
            unique[gk] = len(unique)
        qid[i] = unique[gk]

    # Filter to groups with ≥2 leaves
    counts = {}
    for g in qid: counts[g] = counts.get(g, 0) + 1
    valid = {g for g, c in counts.items() if c >= 2}
    keep = np.array([g in valid for g in qid], dtype=bool)
    X, refs, qid = X[keep], refs[keep], qid[keep]

    # Remap qids contiguous
    old_to_new = {}
    new_qid = []
    for g in qid:
        if g not in old_to_new: old_to_new[g] = len(old_to_new)
        new_qid.append(old_to_new[g])
    qid = np.array(new_qid, dtype=np.int64)

    print(f"  {len(X)} leaves in {len(old_to_new)} groups (>=2 leaves/group)", flush=True)
    return X, refs, qid, common


def get_model_features():
    csv = "build/vcombat_7k.csv"
    hdr = pd.read_csv(csv, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv, dtype=dtypes)
    feats = [c for c in df.columns if c not in ("seed","fightIdx","won","endHp") and df[c].std() > 1e-9]
    del df
    return feats


def pairwise_accuracy(y_pred, y_true, qid):
    correct = total = 0
    groups = {}
    for i, g in enumerate(qid): groups.setdefault(g, []).append(i)
    for g, indices in groups.items():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                dref = y_true[a] - y_true[b]
                if abs(dref) <= PAIR_EPS: continue
                dmod = y_pred[a] - y_pred[b]
                total += 1
                if (dmod > 0) == (dref > 0): correct += 1
    return correct / total if total > 0 else 0.0, total


def export_trees(bst, feat_cols, out_path):
    fidx = {n: i for i, n in enumerate(feat_cols)}
    cfg = json.loads(bst.save_config())
    base_score = float(cfg['learner']['learner_model_param']['base_score'].strip('[] '))
    dumps = bst.get_dump(dump_format='json')
    with open(out_path, 'w') as f:
        f.write(f'nfeat {len(feat_cols)}\n')
        for n in feat_cols: f.write(f'feat {n}\n')
        f.write(f'base_score {base_score}\n')
        f.write(f'ntrees {len(dumps)}\n')
        for t, d in enumerate(dumps):
            tree = json.loads(d)
            byid = {}
            def walk(nd):
                byid[nd['nodeid']] = nd
                for c in nd.get('children', []): walk(c)
            walk(tree)
            ids = sorted(byid)
            ci = {nid: i for i, nid in enumerate(ids)}
            nodes = []
            for nid in ids:
                nd = byid[nid]
                if 'leaf' in nd:
                    nodes.append(('L', float(nd['leaf'])))
                else:
                    nodes.append(('S', fidx[nd['split']], float(nd['split_condition']),
                                  ci[nd['yes']], ci[nd['no']]))
            f.write(f'tree {t} {len(nodes)}\n')
            for nd in nodes:
                if nd[0] == 'L': f.write(f'L {nd[1]:.7g}\n')
                else: f.write(f'S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n')
    return len(dumps)


def parse_range(s):
    lo, hi = s.split("-")
    return list(range(int(lo), int(hi) + 1))


def main():
    parser = argparse.ArgumentParser(description="Ranking fine-tuning for VNet")
    parser.add_argument("--base-model", default="build/v_combat_7k_tuned.json")
    parser.add_argument("--leafdiag", default="build/leafdiag_gate_64.csv")
    parser.add_argument("--leafref", default="build/leafref_gate_64_4k.csv")
    parser.add_argument("--train-seeds", default="126700-126747")
    parser.add_argument("--eval-seeds", default="126748-126763")
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--eta", type=float, default=0.005)
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--out", default="build/v_combat_7k_rank.json")
    args = parser.parse_args()

    train_seeds = parse_range(args.train_seeds)
    eval_seeds = parse_range(args.eval_seeds)

    X_train, y_train, qid_train, feat_cols = load_leafdiag(
        args.leafdiag, args.leafref, train_seeds)
    X_eval, y_eval, qid_eval, _ = load_leafdiag(
        args.leafdiag, args.leafref, eval_seeds)

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feat_cols)
    deval = xgb.DMatrix(X_eval, label=y_eval, feature_names=feat_cols)

    # Load base model
    print(f"\nLoading base model {args.base_model} ...", flush=True)
    bst_base = xgb.Booster()
    bst_base.load_model(args.base_model)

    # Baseline evaluation
    pred_base_train = bst_base.predict(dtrain)
    pred_base_eval = bst_base.predict(deval)
    acc_base_train, n_train = pairwise_accuracy(pred_base_train, y_train, qid_train)
    acc_base_eval, n_eval = pairwise_accuracy(pred_base_eval, y_eval, qid_eval)
    print(f"Baseline (endHp model):")
    print(f"  Train pairwise acc: {acc_base_train:.4f} ({n_train} pairs)")
    print(f"  Eval  pairwise acc: {acc_base_eval:.4f} ({n_eval} pairs)")
    print(f"  Eval  RMSE vs leafref: {np.sqrt(((y_eval-pred_base_eval)**2).mean()):.1f}")
    print(f"  Eval  MAE vs leafref:  {np.abs(y_eval-pred_base_eval).mean():.1f}")

    if args.eval_only:
        return 0

    # Fine-tune: continue training from base, targeting leafref values
    print(f"\nFine-tuning on leafref targets ({args.rounds} rounds, eta={args.eta}) ...", flush=True)
    print(f"  base pred mean={pred_base_train.mean():.1f}, leafref target mean={y_train.mean():.1f}", flush=True)

    ft_params = {
        "objective": "reg:squarederror", "tree_method": "hist", "device": "cuda",
        "max_depth": 8, "eta": args.eta, "subsample": 0.8, "colsample_bytree": 0.8,
        "min_child_weight": 82, "max_bin": 256, "reg_alpha": 1.8, "gamma": 4.4,
    }

    t0 = time.time()
    bst_combined = xgb.train(
        ft_params, dtrain,
        num_boost_round=args.rounds,
        xgb_model=bst_base,
        evals=[(deval, "eval")],
        verbose_eval=50,
    )
    print(f"  trained in {time.time()-t0:.0f}s", flush=True)

    # Evaluate combined model
    pred_comb_eval = bst_combined.predict(deval)
    acc_comb_eval, _ = pairwise_accuracy(pred_comb_eval, y_eval, qid_eval)
    print(f"\nCombined (base + {args.rounds} finetune trees):")
    print(f"  Eval pairwise acc: {acc_comb_eval:.4f}")
    print(f"  Δ from baseline: {acc_comb_eval - acc_base_eval:+.4f}")
    print(f"  Eval RMSE vs leafref: {np.sqrt(((y_eval-pred_comb_eval)**2).mean()):.1f}")
    print(f"  Eval MAE vs leafref:  {np.abs(y_eval-pred_comb_eval).mean():.1f}")

    # Prediction scale check
    print(f"\n  Prediction scale (first 10 eval leaves):")
    base_preview = [f'{p:.1f}' for p in pred_base_eval[:10]]
    comb_preview = [f'{p:.1f}' for p in pred_comb_eval[:10]]
    print(f"    Base:     {base_preview}")
    print(f"    Combined: {comb_preview}")

    # Save
    out_json = args.out
    out_txt = out_json.replace('.json', '.txt')
    bst_combined.save_model(out_json)
    print(f"\nSaved -> {out_json}", flush=True)
    ntrees = export_trees(bst_combined, feat_cols, out_txt)
    print(f"  -> {out_txt} ({ntrees} trees)", flush=True)


if __name__ == "__main__":
    main()
