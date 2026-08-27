#!/usr/bin/env python3
"""Train and compare matched 10k-A/25k-A Silver leaf XGBoost models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import xgboost as xgb

ARMS = {"M10": (10000, "A"), "M25": (25000, "A")}
PARAMS = dict(objective="reg:squarederror", tree_method="hist", max_depth=8,
              eta=0.03, subsample=0.54, colsample_bytree=0.81,
              min_child_weight=82, max_bin=256, reg_alpha=1.8, gamma=4.4)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quantile(values, p):
    return float(np.quantile(values, p)) if values else None


def correlation(a, b, rank=False):
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    if rank:
        def ranks(v):
            order = np.argsort(v, kind="mergesort")
            out = np.empty(len(v), dtype=float)
            pos = 0
            while pos < len(v):
                end = pos + 1
                while end < len(v) and v[order[end]] == v[order[pos]]:
                    end += 1
                out[order[pos:end]] = (pos + end - 1) / 2
                pos = end
            return out
        a, b = ranks(a), ranks(b)
    return float(np.corrcoef(a, b)[0, 1])


def metrics(rows, predictions):
    by_group = defaultdict(list)
    for row, prediction in zip(rows, predictions):
        by_group[row["group_id"]].append((row, float(prediction)))
    concordant = pair_total = top = evaluable_groups = 0
    regrets, centered = [], []
    for group_rows in by_group.values():
        if len(group_rows) < 2:
            continue
        evaluable_groups += 1
        values = np.asarray([row["reference"] for row, _ in group_rows])
        preds = np.asarray([pred for _, pred in group_rows])
        for left in range(len(values)):
            for right in range(left + 1, len(values)):
                vd, pd = values[left] - values[right], preds[left] - preds[right]
                if vd == 0 or pd == 0:
                    continue
                pair_total += 1
                concordant += (vd > 0) == (pd > 0)
        vi, pi = int(np.argmax(values)), int(np.argmax(preds))
        top += vi == pi
        regrets.append(float(values[vi] - values[pi]))
        centered.extend((preds - preds.mean()) - (values - values.mean()))
    truth = np.asarray([row["reference"] for row in rows])
    predictions = np.asarray(predictions)
    errors = predictions - truth
    return {
        "rows": len(rows), "groups": len(by_group), "groups_with_two_plus_leaves": evaluable_groups,
        "strict_sibling_pairwise_concordance": concordant / pair_total if pair_total else 0.0,
        "strict_sibling_pairs": pair_total,
        "top_leaf_agreement": top / evaluable_groups if evaluable_groups else None,
        "mean_regret": statistics.fmean(regrets) if regrets else None,
        "median_regret": statistics.median(regrets) if regrets else None,
        "centered_mae": statistics.fmean(abs(v) for v in centered) if centered else None,
        "centered_rmse": math.sqrt(statistics.fmean(v*v for v in centered)) if centered else None,
        "global_mae": float(np.mean(np.abs(errors))), "global_rmse": float(np.sqrt(np.mean(errors**2))),
        "pearson": correlation(predictions, truth), "spearman": correlation(predictions, truth, True),
    }


def subgroup_metrics(rows, predictions):
    output = {}
    dimensions = {
        "act": lambda r: str(r["act"]),
        "hp_band": lambda r: "low" if r["hp_fraction"] < .34 else "mid" if r["hp_fraction"] < .67 else "high",
        "rollout_length_band": lambda r: "short" if r["rollout_turn_delta"] <= 2 else "medium" if r["rollout_turn_delta"] <= 5 else "long",
        "encounter_category": lambda r: r["encounter_category"],
    }
    for dimension, labeler in dimensions.items():
        buckets = defaultdict(list)
        for row, pred in zip(rows, predictions):
            buckets[labeler(row)].append((row, pred))
        output[dimension] = {label: metrics([r for r, _ in values], [p for _, p in values])
                             for label, values in sorted(buckets.items())}
    return output


def bootstrap(rows, predictions, replicates, seed):
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row["group_id"]].append(index)
    groups = sorted(grouped)
    rng = random.Random(seed)
    samples = defaultdict(list)
    for _ in range(replicates):
        chosen_rows, arm_predictions = [], {arm: [] for arm in ARMS}
        for occurrence in range(len(groups)):
            group = rng.choice(groups)
            for index in grouped[group]:
                row = dict(rows[index]); row["group_id"] = f"{group}#{occurrence}"
                chosen_rows.append(row)
                for arm in ARMS: arm_predictions[arm].append(predictions[arm][index])
        arm_metrics = {arm: metrics(chosen_rows, arm_predictions[arm]) for arm in ARMS}
        for key in ("strict_sibling_pairwise_concordance", "top_leaf_agreement",
                    "mean_regret", "median_regret", "centered_mae", "centered_rmse",
                    "global_mae", "global_rmse"):
            samples[key].append(arm_metrics["M25"][key] - arm_metrics["M10"][key])
    return {key: {"m25_minus_m10": {"p05": quantile(values, .05), "p50": quantile(values, .5),
                                     "p95": quantile(values, .95)},
                  "probability_positive": statistics.fmean(value > 0 for value in values),
                  "probability_negative": statistics.fmean(value < 0 for value in values)}
            for key, values in samples.items()}


def load_features(path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("feature_schema") != "silver_leaf_combat_features_v1" or "feature_names" not in header:
            raise SystemExit("incompatible feature header")
        rows = {}
        for number, line in enumerate(stream, 2):
            if not line.strip(): continue
            row = json.loads(line)
            leaf = row["leaf_snapshot_id"]
            if leaf in rows: raise SystemExit(f"duplicate feature leaf at line {number}")
            if len(row["features"]) != len(header["feature_names"]): raise SystemExit("feature width mismatch")
            rows[leaf] = row
    return header["feature_names"], rows


def load_labels(path):
    labels = {}
    anchor_groups = set()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1": raise SystemExit("incompatible relabel schema")
            if row["state_kind"] != "leaf": continue
            key = (row["leaf_snapshot_id"], row["budget"], row["replicate"])
            if key in labels: raise SystemExit(f"duplicate label at line {number}")
            labels[key] = row
            if row["budget"] == 25000 and row["replicate"] == "B": anchor_groups.add(row["group_id"])
    return labels, anchor_groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path); parser.add_argument("relabels", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--device", default="cpu"); parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260827)
    parser.add_argument("--smoke-rounds", type=int, default=0)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names, feature_rows = load_features(args.features)
    labels, anchor_groups = load_labels(args.relabels)
    eligible = []
    for leaf, feature in feature_rows.items():
        arm_rows = {arm: labels.get((leaf, *identity)) for arm, identity in ARMS.items()}
        if all(row and row.get("teacher_valid", True) for row in arm_rows.values()):
            eligible.append((leaf, feature, arm_rows))
    eligible.sort()
    all_groups = {feature["group_id"] for _, feature, _ in eligible}
    nonanchor = sorted(all_groups - anchor_groups)
    val_groups = {group for group in nonanchor
                  if int(hashlib.sha256(("silver-leaf-val-v1/" + group).encode()).hexdigest(), 16) % 100 < 15}
    train_groups = set(nonanchor) - val_groups
    if not train_groups or not val_groups: raise SystemExit("deterministic split produced an empty train or validation set")
    split_rows = {"train": [], "validation": [], "test": []}
    for leaf, feature, arm_rows in eligible:
        group = feature["group_id"]
        split = "test" if group in anchor_groups else "validation" if group in val_groups else "train"
        reference = labels.get((leaf, 25000, "B"))
        if split == "test" and (not reference or not reference.get("teacher_valid", True)):
            continue
        split_rows[split].append({**feature, "labels": {arm: row["original_root_corrected_teacher_value"] for arm, row in arm_rows.items()},
                                  "reference": reference["original_root_corrected_teacher_value"] if reference else None})
    leakage = bool((train_groups | val_groups) & anchor_groups)
    if leakage: raise SystemExit("anchor leakage detected")
    feature_matrix = {split: np.asarray([row["features"] for row in rows], dtype=np.float32)
                      for split, rows in split_rows.items()}
    params = {**PARAMS, "device": args.device}
    predictions, models, training = {}, {}, {}
    rounds = args.smoke_rounds or 2000
    for arm in ARMS:
        ytr = np.asarray([row["labels"][arm] for row in split_rows["train"]], dtype=np.float32)
        yva = np.asarray([row["labels"][arm] for row in split_rows["validation"]], dtype=np.float32)
        dtr = xgb.QuantileDMatrix(feature_matrix["train"], label=ytr, feature_names=names)
        dva = xgb.QuantileDMatrix(feature_matrix["validation"], label=yva, ref=dtr, feature_names=names)
        start = time.monotonic()
        model = xgb.train(params, dtr, num_boost_round=rounds, evals=[(dva, "validation")],
                          early_stopping_rounds=None if args.smoke_rounds else 40, verbose_eval=100)
        model_path = args.output_dir / f"{arm.lower()}.json"; model.save_model(model_path)
        models[arm] = model_path
        best_iteration = rounds - 1 if args.smoke_rounds else model.best_iteration
        predictions[arm] = model.predict(xgb.DMatrix(feature_matrix["test"], feature_names=names),
                                         iteration_range=(0, best_iteration + 1))
        training[arm] = {"seconds": time.monotonic() - start, "best_iteration": best_iteration,
                         "model_sha256": sha256(model_path)}
    heldout = {arm: metrics(split_rows["test"], predictions[arm]) for arm in ARMS}
    subgroups = {arm: subgroup_metrics(split_rows["test"], predictions[arm]) for arm in ARMS}
    paired = bootstrap(split_rows["test"], predictions, args.bootstrap_replicates, args.bootstrap_seed)
    delta = heldout["M25"]["strict_sibling_pairwise_concordance"] - heldout["M10"]["strict_sibling_pairwise_concordance"]
    positive = paired["strict_sibling_pairwise_concordance"]["probability_positive"]
    top_worse = heldout["M25"]["top_leaf_agreement"] + .02 < heldout["M10"]["top_leaf_agreement"]
    regret_worse = heldout["M25"]["mean_regret"] > heldout["M10"]["mean_regret"] + .25
    conflict = delta >= .01 and positive >= .90 and (top_worse or regret_worse)
    verdict = ("MODEL_TEACHER_BUDGET_UNRESOLVED" if conflict else
               "USE_25K_TEACHER" if delta >= .01 and positive >= .90 and not top_worse and not regret_worse else
               "USE_10K_TEACHER")
    report = {
        "schema": "silver_leaf_model_comparison_v1", "verdict": verdict,
        "inputs": {"features": str(args.features), "features_sha256": sha256(args.features),
                   "relabels": str(args.relabels), "relabels_sha256": sha256(args.relabels)},
        "feature_schema": "silver_leaf_combat_features_v1", "feature_count": len(names), "feature_names": names,
        "recipe": {"params": params, "num_boost_round": rounds,
                   "early_stopping_rounds": None if args.smoke_rounds else 40,
                   "same_features_split_and_weights": True, "sample_weighting": "uniform"},
        "groups": {"anchor": len(anchor_groups), "train": len(train_groups), "validation": len(val_groups),
                   "test": len({row["group_id"] for row in split_rows["test"]}),
                   "anchor_leakage": leakage},
        "rows": {split: len(rows) for split, rows in split_rows.items()},
        "training": training, "heldout_25k_B": heldout, "subgroups": subgroups,
        "paired_whole_group_bootstrap": {"replicates": args.bootstrap_replicates,
             "seed": args.bootstrap_seed, "confidence_level": .90, "metrics": paired},
        "decision_diagnostics": {"pairwise_delta": delta, "probability_pairwise_positive": positive,
                                 "top_materially_worse": top_worse, "regret_materially_worse": regret_worse,
                                 "strong_metric_conflict": conflict},
        "warning": "Offline teacher/model comparison only; no gameplay improvement is established.",
    }
    output = args.output_dir / "comparison.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
