#!/usr/bin/env python3
"""Pairwise ranking fine-tuning for the VNet XGBoost model.

Trains on actual Searcher3 leaf states (leafdiag) with a pairwise ranking
objective (LambdaRank) using leafref high-budget reference values as the
ranking target. Starts from the existing endHp model to preserve the HP
prediction scale while improving action-ranking quality.

The hypothesis (§148 follow-up): the endHp regression objective doesn't teach
the model to rank MCTS leaf states correctly. A pairwise ranking loss on
these states directly optimizes for what MCTS needs — correct ordering of
action alternatives.

Usage:
  # Fine-tune the 7k model on leafdiag ranking data
  python3 tools/train_vnet_ranking.py

  # Evaluate ranking accuracy before/after
  python3 tools/train_vnet_ranking.py --eval-only
"""
import sys, os, json, argparse, time
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

# ── Data loading ────────────────────────────────────────────────────────────

def load_leafdiag(leafdiag_path, leafref_path, seed_range):
    """Load leafdiag features + leafref labels for a seed block.
    Returns (X, y_rank, qid) where:
      X: (n, n_features) float32 features aligned with model feature set
      y_rank: (n,) float64 leafref reference values (ranking target)
      qid: (n,) int64 group IDs (one per decision group)
    """
    print(f"Loading leafdiag {leafdiag_path} ...", flush=True)
    ld = pd.read_csv(leafdiag_path)
    ld = ld[ld["seed"].isin(seed_range)].copy().reset_index(drop=True)
    print(f"  {len(ld)} leaves from seeds {min(seed_range)}-{max(seed_range)}", flush=True)

    # Load leafref
    print(f"Loading leafref {leafref_path} ...", flush=True)
    lr = pd.read_csv(leafref_path)
    lr = lr[lr["seed"].isin(seed_range)]
    lr_agg = lr.groupby(["seed","fightIdx","decIdx","obsHash"])["referenceValue"].mean()
    lr_map = {k: float(v) for k, v in lr_agg.items()}

    # Join reference values
    refs = np.full(len(ld), np.nan, dtype=np.float64)
    has_ref = np.zeros(len(ld), dtype=bool)
    for i, row in ld.iterrows():
        key = (int(row["seed"]), int(row["fightIdx"]), int(row["decIdx"]), int(row["obsHash"]))
        val = lr_map.get(key)
        if val is not None and not np.isnan(val):
            refs[i] = val
            has_ref[i] = True
    ld = ld[has_ref].copy().reset_index(drop=True)
    refs = refs[has_ref]
    print(f"  {len(ld)} leaves have reference values", flush=True)

    # Feature columns: canonical combat features (between metadata and prediction cols)
    meta_end_col = "endHp_pred"
    meta_cols = ["seed","fightIdx","decIdx","floor","act","encounterName",
                 "treeDepth","obsHash","nLegalActions","stratum","fightWon",
                 "fightEndHp","endHp_pred","utilityR_pred","rawRolloutEval","blendedEval"]
    feat_cols_leaf = [c for c in ld.columns if c not in meta_cols]

    # Align with model feature set
    model_feats = get_model_features()
    common = [f for f in model_feats if f in feat_cols_leaf]
    missing = set(model_feats) - set(common)
    extra = set(feat_cols_leaf) - set(model_feats)
    if missing:
        print(f"  WARNING: {len(missing)} model features missing from leafdiag")
    if extra:
        print(f"  {len(extra)} leafdiag features not in model (ignored)")

    X = ld[common].to_numpy(np.float32)
    print(f"  {len(common)}/{len(model_feats)} features aligned", flush=True)

    # Create decision group IDs (qid)
    ld["_group_key"] = (ld["seed"].astype(str) + "_" +
                        ld["fightIdx"].astype(str) + "_" +
                        ld["decIdx"].astype(str))
    group_keys = ld["_group_key"].to_numpy()
    # Assign sequential qid per unique group key
    unique_groups = {}
    qid = np.zeros(len(ld), dtype=np.int64)
    next_qid = 0
    for i, gk in enumerate(group_keys):
        if gk not in unique_groups:
            unique_groups[gk] = next_qid
            next_qid += 1
        qid[i] = unique_groups[gk]

    # Filter to groups with ≥2 leaves (needed for pairwise)
    group_counts = {}
    for g in qid:
        group_counts[g] = group_counts.get(g, 0) + 1
    valid_groups = {g for g, c in group_counts.items() if c >= 2}
    keep = np.array([g in valid_groups for g in qid], dtype=bool)
    X = X[keep]; refs = refs[keep]; qid = qid[keep]

    # Remap qids to be contiguous
    old_to_new = {}
    new_qid = []
    for g in qid:
        if g not in old_to_new:
            old_to_new[g] = len(old_to_new)
        new_qid.append(old_to_new[g])

    n_groups = len(old_to_new)
    print(f"  {len(X)} leaves in {n_groups} groups (≥2 leaves/group)", flush=True)
    return X, refs, np.array(new_qid, dtype=np.int64), common


def get_model_features():
    """Return model feature set trained on 7k data."""
    csv = "build/vcombat_7k.csv"
    hdr = pd.read_csv(csv, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv, dtype=dtypes)
    feats = [c for c in df.columns
             if c not in ("seed","fightIdx","won","endHp")
             and df[c].std() > 1e-9]
    del df
    return feats


# ── Pairwise accuracy evaluation ────────────────────────────────────────────

PAIR_EPS = 1e-6

def pairwise_accuracy(y_pred, y_true, qid):
    """Compute pairwise ranking accuracy within each group."""
    correct = total = 0
    groups = {}
    for i, g in enumerate(qid):
        groups.setdefault(g, []).append(i)
    for g, indices in groups.items():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                dref = y_true[a] - y_true[b]
                if abs(dref) <= PAIR_EPS:
                    continue
                dmod = y_pred[a] - y_pred[b]
                total += 1
                if (dmod > 0) == (dref > 0):
                    correct += 1
    return correct / total if total > 0 else 0.0, total


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ranking fine-tuning for VNet")
    parser.add_argument("--base-model", default="build/v_combat_7k_tuned.json",
                        help="Base model to fine-tune from")
    parser.add_argument("--leafdiag", default="build/leafdiag_gate_64.csv")
    parser.add_argument("--leafref", default="build/leafref_gate_64_4k.csv")
    parser.add_argument("--train-seeds", default="126700-126747",
                        help="Seed range for training (default: 126700-126747)")
    parser.add_argument("--eval-seeds", default="126748-126763",
                        help="Seed range for evaluation (default: 126748-126763)")
    parser.add_argument("--rounds", type=int, default=200,
                        help="Fine-tuning boost rounds (default: 200)")
    parser.add_argument("--eta", type=float, default=0.01,
                        help="Fine-tuning learning rate (default: 0.01)")
    parser.add_argument("--eval-only", action="store_true",
                        help="Only evaluate, don't train")
    parser.add_argument("--out", default="build/v_combat_7k_rank.json",
                        help="Output model path")
    args = parser.parse_args()

    # Parse seed ranges
    def parse_range(s):
        lo, hi = s.split("-")
        return list(range(int(lo), int(hi) + 1))
    train_seeds = parse_range(args.train_seeds)
    eval_seeds = parse_range(args.eval_seeds)

    # Load data
    X_train, y_train, qid_train, feat_cols = load_leafdiag(
        args.leafdiag, args.leafref, train_seeds)
    X_eval, y_eval, qid_eval, _ = load_leafdiag(
        args.leafdiag, args.leafref, eval_seeds)

    # Create DMatrix with group info
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feat_cols)
    dtrain.set_group([list(qid_train).count(g) for g in sorted(set(qid_train))])
    deval = xgb.DMatrix(X_eval, label=y_eval, feature_names=feat_cols)
    deval.set_group([list(qid_eval).count(g) for g in sorted(set(qid_eval))])

    # Load base model and evaluate baseline
    print(f"\nLoading base model {args.base_model} ...", flush=True)
    bst = xgb.Booster()
    bst.load_model(args.base_model)

    # Baseline ranking accuracy
    pred_base_train = bst.predict(dtrain)
    pred_base_eval = bst.predict(deval)
    acc_base_train, n_train = pairwise_accuracy(pred_base_train, y_train, qid_train)
    acc_base_eval, n_eval = pairwise_accuracy(pred_base_eval, y_eval, qid_eval)
    print(f"\nBaseline (endHp model):")
    print(f"  Train pairwise acc: {acc_base_train:.4f} ({n_train} pairs)")
    print(f"  Eval  pairwise acc: {acc_base_eval:.4f} ({n_eval} pairs)")

    if args.eval_only:
        return 0

    # Fine-tune with rank:pairwise
    print(f"\nFine-tuning with rank:pairwise ({args.rounds} rounds, eta={args.eta}) ...",
          flush=True)
    rank_params = {
        "objective": "rank:pairwise",
        "tree_method": "hist",
        "device": "cuda",
        "max_depth": 8,
        "eta": args.eta,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 82,
        "max_bin": 256,
        "reg_alpha": 1.8,
        "gamma": 4.4,
        "lambdarank_pair_method": "topk",
    }

    t0 = time.time()
    bst_rank = xgb.train(
        rank_params, dtrain,
        num_boost_round=args.rounds,
        evals=[(deval, "eval")],
        verbose_eval=50,
    )
    print(f"  trained in {time.time()-t0:.0f}s", flush=True)

    # Evaluate fine-tuned model
    pred_rank_eval = bst_rank.predict(deval)
    acc_rank_eval, n_eval2 = pairwise_accuracy(pred_rank_eval, y_eval, qid_eval)
    print(f"\nFine-tuned (ranking model):")
    print(f"  Eval pairwise acc: {acc_rank_eval:.4f} ({n_eval2} pairs)")
    print(f"  Δ from baseline: {acc_rank_eval - acc_base_eval:+.4f}")

    # Also evaluate the combined model (base + new trees)
    # When xgb.train returns a new model, we need to manually combine
    # Actually, xgb.train trains from scratch. We want to CONTINUE training.
    # Let me use the process_type parameter or xgb_model...
    print(f"\nTraining combined model (base + ranking trees) ...", flush=True)
    bst_base = xgb.Booster()
    bst_base.load_model(args.base_model)
    
    # XGBoost allows continuing training by passing xgb_model
    bst_combined = xgb.train(
        rank_params, dtrain,
        num_boost_round=args.rounds,
        xgb_model=bst_base,
        evals=[(deval, "eval")],
        verbose_eval=50,
    )
    
    pred_comb_eval = bst_combined.predict(deval)
    acc_comb_eval, _ = pairwise_accuracy(pred_comb_eval, y_eval, qid_eval)
    print(f"\nCombined (base + rank trees):")
    print(f"  Eval pairwise acc: {acc_comb_eval:.4f}")
    print(f"  Δ from baseline: {acc_comb_eval - acc_base_eval:+.4f}")

    # Also check: does the combined model still predict reasonable HP values?
    # Quick check on a few eval leaves
    print(f"\nPrediction scale check (first 10 eval leaves):")
    print(f"  Base model preds: {[f'{p:.1f}' for p in pred_base_eval[:10]]}")
    print(f"  Combined preds:   {[f'{p:.1f}' for p in pred_comb_eval[:10]]}")

    # Save combined model
    out_json = args.out
    out_txt = out_json.replace('.json', '.txt')
    bst_combined.save_model(out_json)
    print(f"\nSaved -> {out_json}", flush=True)

    # Export compact tree format
    print(f"Exporting compact trees ...", flush=True)
    import subprocess
    # Need to handle the feature alignment manually since export_combat_model is
    # for the full combat feature set, not the leafdiag subset
    fidx = {n: i for i, n in enumerate(feat_cols)}
    cfg = json.loads(bst_combined.save_config())
    base_score = float(cfg['learner']['learner_model_param']['base_score'].strip('[] '))
    dumps = bst_combined.get_dump(dump_format='json')
    with open(out_txt, 'w') as f:
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
            ids = sorted(byid); ci = {nid: i for i, nid in enumerate(ids)}
            nodes = []
            for nid in ids:
                nd = byid[nid]
                nodes.append(('L', float(nd['leaf'])) if 'leaf' in nd else
                    ('S', fidx[nd['split']], float(nd['split_condition']),
                     ci[nd['yes']], ci[nd['no']]))
            f.write(f'tree {t} {len(nodes)}\n')
            for nd in nodes:
                if nd[0] == 'L': f.write(f'L {nd[1]:.7g}\n')
                else: f.write(f'S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n')
    print(f"  -> {out_txt} ({len(dumps)} trees)", flush=True)


if __name__ == "__main__":
    main()
