#!/usr/bin/env python3
"""Train and evaluate the preregistered Silver 25k parent-action Q scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import xgboost as xgb

PARAMS = dict(objective="reg:squarederror", tree_method="hist", max_depth=8,
              eta=0.03, subsample=0.54, colsample_bytree=0.81,
              min_child_weight=82, max_bin=256, reg_alpha=1.8, gamma=4.4,
              seed=20260828, nthread=1)
SPLIT_SALT = "silver-parent-policy-val-v1/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rankdata(values):
    values = np.asarray(values)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    pos = 0
    while pos < len(values):
        end = pos + 1
        while end < len(values) and values[order[end]] == values[order[pos]]:
            end += 1
        ranks[order[pos:end]] = (pos + end - 1) / 2
        pos = end
    return ranks


def spearman(truth, pred):
    if len(truth) < 2 or np.std(truth) == 0 or np.std(pred) == 0:
        return None
    return float(np.corrcoef(rankdata(truth), rankdata(pred))[0, 1])


def action_type(fingerprint):
    return fingerprint.split("|", 1)[0]


def load_features(path):
    groups = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("feature_schema") != "silver_parent_policy_features_v1":
            raise SystemExit("incompatible feature schema")
        names = header["feature_names"]
        if header["feature_count"] != len(names): raise SystemExit("feature header width mismatch")
        seen = set()
        for number, line in enumerate(stream, 2):
            if not line.strip(): continue
            row = json.loads(line)
            key = (row["group_id"], row["action_fingerprint"])
            if key in seen: raise SystemExit(f"duplicate feature action at line {number}")
            seen.add(key)
            if len(row["features"]) != len(names): raise SystemExit(f"feature width mismatch at line {number}")
            groups[row["group_id"]].append(row)
    for rows in groups.values(): rows.sort(key=lambda row: row["silver_order"])
    return header, names, groups


def load_relabels(path):
    parents = {}
    anchors = set()
    coverage = Counter()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1":
                raise SystemExit(f"incompatible relabel schema at line {number}")
            if row["state_kind"] != "parent": continue
            key = (row["group_id"], int(row["budget"]), row["replicate"])
            if key in parents: raise SystemExit(f"duplicate parent label at line {number}")
            parents[key] = row
            coverage[f"{row['budget']}-{row['replicate']}-rows"] += 1
            if row.get("teacher_valid", False): coverage[f"{row['budget']}-{row['replicate']}-valid"] += 1
            if row["budget"] == 25000 and row["replicate"] == "B": anchors.add(row["group_id"])
    return parents, anchors, dict(sorted(coverage.items()))


def q_map(row):
    if not row or not row.get("teacher_valid", False): return None
    actions = {}
    for action in row["root_actions"]:
        if not action.get("leaf_root_q_valid", False): return None
        fp = action["action_fingerprint"]
        if fp in actions: raise SystemExit(f"duplicate relabel fingerprint for {row['group_id']}")
        actions[fp] = float(action["original_root_corrected_q"])
    return actions if len(actions) == row["root_action_count"] else None


def attach_reference(feature_groups, labels, anchors):
    test = {}
    exclusions = Counter()
    for group in sorted(anchors):
        if group not in feature_groups:
            exclusions["anchor_missing_complete_25k_a_features"] += 1; continue
        reference = q_map(labels.get((group, 25000, "B")))
        if reference is None:
            exclusions["anchor_invalid_25k_b"] += 1; continue
        fingerprints = {row["action_fingerprint"] for row in feature_groups[group]}
        if fingerprints != set(reference):
            exclusions["anchor_25k_b_action_set_mismatch"] += 1; continue
        rows = []
        mean = statistics.fmean(reference.values())
        for row in feature_groups[group]:
            rows.append({**row, "reference_q": reference[row["action_fingerprint"]],
                         "reference_centered_q": reference[row["action_fingerprint"]] - mean})
        test[group] = rows
    return test, dict(sorted(exclusions.items()))


def flatten(groups, ids):
    return [row for group in sorted(ids) for row in groups[group]]


def group_metrics(groups, scores):
    concordant = pairs = ties = tops = 0
    regrets = []
    centered_errors = []
    parent_spearman = []
    parent_rows = {}
    for group, rows in groups.items():
        pred = np.asarray(scores[group], dtype=float)
        truth = np.asarray([row["reference_q"] for row in rows], dtype=float)
        concordant_parent = pairs_parent = 0.0
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                qd = truth[left] - truth[right]
                if qd == 0: continue
                pd = pred[left] - pred[right]
                pairs += 1; pairs_parent += 1
                if pd == 0:
                    ties += 1; concordant += .5; concordant_parent += .5
                elif (pd > 0) == (qd > 0):
                    concordant += 1; concordant_parent += 1
        best = int(np.argmax(truth)); chosen = int(np.argmax(pred))
        tops += best == chosen
        regret = float(truth[best] - truth[chosen]); regrets.append(regret)
        centered_errors.extend((pred - pred.mean()) - (truth - truth.mean()))
        rho = spearman(truth, pred)
        if rho is not None: parent_spearman.append(rho)
        parent_rows[group] = {"concordant": concordant_parent, "pairs": pairs_parent,
                              "top": int(best == chosen), "regret": regret}
    errors = np.asarray(centered_errors)
    return {"pairwise_concordance": concordant / pairs if pairs else None,
            "reference_pairs": pairs, "prediction_tie_count": ties,
            "top_action_agreement": tops / len(groups),
            "mean_regret": statistics.fmean(regrets), "median_regret": statistics.median(regrets),
            "centered_q_mae": float(np.mean(np.abs(errors))),
            "centered_q_rmse": float(np.sqrt(np.mean(errors * errors))),
            "mean_parent_spearman": statistics.fmean(parent_spearman) if parent_spearman else None,
            "parents_with_spearman": len(parent_spearman)}, parent_rows


def bootstrap(model_parent, ordering_parent, replicates, seed):
    ids = sorted(model_parent)
    rng = np.random.default_rng(seed)
    pair_delta, regret_reduction, top_delta = [], [], []
    for _ in range(replicates):
        selected = rng.choice(ids, size=len(ids), replace=True)
        def aggregate(source):
            rows = [source[group] for group in selected]
            pair = sum(row["concordant"] for row in rows) / sum(row["pairs"] for row in rows)
            return pair, statistics.fmean(row["regret"] for row in rows), statistics.fmean(row["top"] for row in rows)
        model = aggregate(model_parent); order = aggregate(ordering_parent)
        pair_delta.append(model[0] - order[0])
        regret_reduction.append(order[1] - model[1])
        top_delta.append(model[2] - order[2])
    def summary(values):
        return {"p05": float(np.quantile(values, .05)), "p50": float(np.quantile(values, .5)),
                "p95": float(np.quantile(values, .95)),
                "probability_positive": statistics.fmean(value > 0 for value in values)}
    return {"replicates": replicates, "seed": seed,
            "model_minus_ordering_pairwise": summary(pair_delta),
            "ordering_minus_model_mean_regret": summary(regret_reduction),
            "model_minus_ordering_top_agreement": summary(top_delta)}


def score_teacher(test, labels, budget):
    scores = {}
    eligible = {}
    for group, rows in test.items():
        source = q_map(labels.get((group, budget, "A")))
        if source is None or set(source) != {row["action_fingerprint"] for row in rows}: continue
        eligible[group] = rows
        scores[group] = [source[row["action_fingerprint"]] for row in rows]
    metrics, _ = group_metrics(eligible, scores)
    metrics["eligible_parents"] = len(eligible)
    return metrics


def diagnostics(test, model_scores, ordering_scores):
    action_counts = Counter(len(rows) for rows in test.values())
    margins = defaultdict(list)
    types = defaultdict(list)
    acts, encounters, hp_bands = defaultdict(list), defaultdict(list), defaultdict(list)
    for group, rows in test.items():
        truth = np.asarray([row["reference_q"] for row in rows])
        order = np.argsort(truth)
        margin = float(truth[order[-1]] - truth[order[-2]]) if len(rows) > 1 else 0.0
        bucket = "<0.25" if margin < .25 else "0.25-1" if margin < 1 else "1-3" if margin < 3 else ">=3"
        margins[bucket].append(group)
        acts[str(rows[0]["act"])].append(group)
        encounters[rows[0]["encounter_category"]].append(group)
        hp = float(rows[0].get("hp_fraction", 0.0))
        hp_bands["<=0.33" if hp <= .33 else "0.33-0.67" if hp <= .67 else ">0.67"].append(group)
        chosen = int(np.argmax(model_scores[group])); best = int(np.argmax(truth))
        types[action_type(rows[best]["action_fingerprint"])].append({"top": int(chosen == best),
            "regret": float(truth[best] - truth[chosen])})
    def subgroup(source):
        result = {}
        for key, ids in sorted(source.items()):
            if len(ids) < 5: continue
            subset = {group: test[group] for group in ids}
            model, _ = group_metrics(subset, {group: model_scores[group] for group in ids})
            ordering, _ = group_metrics(subset, {group: ordering_scores[group] for group in ids})
            result[key] = {"parents": len(ids), "model": model, "current_ordering": ordering}
        return result
    return {"action_count_distribution": dict(sorted(action_counts.items())),
            "top_two_25k_b_margin": subgroup(margins),
            "best_action_type": {kind: {"parents": len(rows),
                "top_action_agreement": statistics.fmean(row["top"] for row in rows),
                "mean_regret": statistics.fmean(row["regret"] for row in rows)}
                for kind, rows in sorted(types.items()) if len(rows) >= 5},
            "act": subgroup(acts), "hp_fraction": subgroup(hp_bands),
            "encounter_category": subgroup(encounters)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path); parser.add_argument("relabels", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260828)
    parser.add_argument("--smoke-rounds", type=int, default=0)
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    header, names, groups = load_features(args.features)
    labels, anchors, relabel_coverage = load_relabels(args.relabels)
    # Anchor identity is fixed from labels before any split, matrix, or model construction.
    test, test_exclusions = attach_reference(groups, labels, anchors)
    nonanchors = sorted(set(groups) - anchors)
    validation = {group for group in nonanchors if int(hashlib.sha256((SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15}
    train = set(nonanchors) - validation
    if not train or not validation: raise SystemExit("empty deterministic train/validation split")
    if (train | validation) & anchors: raise SystemExit("anchor leakage")
    train_rows, val_rows = flatten(groups, train), flatten(groups, validation)
    xtr = np.asarray([row["features"] for row in train_rows], dtype=np.float32)
    xva = np.asarray([row["features"] for row in val_rows], dtype=np.float32)
    ytr = np.asarray([row["centered_q_25k_a"] for row in train_rows], dtype=np.float32)
    yva = np.asarray([row["centered_q_25k_a"] for row in val_rows], dtype=np.float32)
    params = {**PARAMS, "device": args.device}
    rounds = args.smoke_rounds or 2000
    dtr = xgb.QuantileDMatrix(xtr, label=ytr, feature_names=names)
    dva = xgb.QuantileDMatrix(xva, label=yva, ref=dtr, feature_names=names)
    start = time.monotonic()
    model = xgb.train(params, dtr, num_boost_round=rounds, evals=[(dva, "validation")],
        early_stopping_rounds=None if args.smoke_rounds else 40, verbose_eval=100)
    training_seconds = time.monotonic() - start
    best_iteration = rounds - 1 if args.smoke_rounds else model.best_iteration
    model_path = args.output_dir / "silver_parent_policy_25k.json"; model.save_model(model_path)
    test_rows = flatten(test, test)
    xtest = np.asarray([row["features"] for row in test_rows], dtype=np.float32)
    predict_start = time.perf_counter_ns()
    pred = model.predict(xgb.DMatrix(xtest, feature_names=names), iteration_range=(0, best_iteration + 1))
    prediction_ns = time.perf_counter_ns() - predict_start
    model_scores, offset = {}, 0
    for group in sorted(test):
        count = len(test[group]); model_scores[group] = pred[offset:offset + count].tolist(); offset += count
    ordering_scores = {group: [-row["silver_order"] for row in rows] for group, rows in test.items()}
    model_metrics, model_parent = group_metrics(test, model_scores)
    ordering_metrics, ordering_parent = group_metrics(test, ordering_scores)
    paired = bootstrap(model_parent, ordering_parent, args.bootstrap_replicates, args.bootstrap_seed)
    pair_delta = model_metrics["pairwise_concordance"] - ordering_metrics["pairwise_concordance"]
    top_delta = model_metrics["top_action_agreement"] - ordering_metrics["top_action_agreement"]
    pair_positive = paired["model_minus_ordering_pairwise"]["probability_positive"]
    regret_positive = paired["ordering_minus_model_mean_regret"]["probability_positive"]
    promising = pair_delta >= .03 and pair_positive >= .90 and regret_positive >= .90 and top_delta >= -.02
    meaningful = pair_delta >= .03 or regret_positive >= .90
    conflict = pair_delta >= .03 and (regret_positive < .90 or top_delta < -.02)
    verdict = "POLICY_MODEL_OFFLINE_PROMISING" if promising else (
        "POLICY_MODEL_OFFLINE_UNRESOLVED" if conflict else "POLICY_MODEL_OFFLINE_REJECTED")
    report = {"schema": "silver_parent_policy_experiment_v1", "verdict": verdict,
        "inputs": {"features": str(args.features), "features_sha256": sha256(args.features),
                   "relabels": str(args.relabels), "relabels_sha256": sha256(args.relabels)},
        "coverage": {"relabels": relabel_coverage, "feature_header": header,
                     "test_exclusions": test_exclusions},
        "split": {"train_parents": len(train), "validation_parents": len(validation),
                  "test_parents": len(test), "anchor_parents_identified_before_modeling": len(anchors),
                  "anchor_leakage": False, "salt": SPLIT_SALT,
                  "train_action_rows": len(train_rows), "validation_action_rows": len(val_rows),
                  "test_action_rows": len(test_rows)},
        "feature_schema": {"name": "silver_parent_policy_features_v1", "count": len(names), "names": names},
        "target": "Q_25kA(s,a) - mean_b Q_25kA(s,b); raw corrected Q and visits retained as diagnostics",
        "recipe": {"params": params, "num_boost_round": rounds,
                   "early_stopping_rounds": None if args.smoke_rounds else 40,
                   "best_iteration": best_iteration, "hyperparameter_sweep": False},
        "model": {"path": str(model_path), "sha256": sha256(model_path)},
        "cost": {"training_seconds": training_seconds, "batch_prediction_seconds": prediction_ns / 1e9,
                 "prediction_actions": len(test_rows), "microseconds_per_action": prediction_ns / 1000 / len(test_rows)},
        "current_silver_ordering": ordering_metrics, "model_25k_b": model_metrics,
        "teacher_references_25k_b": {str(budget): score_teacher(test, labels, budget) for budget in (1000, 10000, 25000)},
        "paired_whole_parent_bootstrap": paired,
        "diagnostics": diagnostics(test, model_scores, ordering_scores),
        "decision": {"pairwise_percentage_point_improvement": 100 * pair_delta,
                     "top_action_percentage_point_change": 100 * top_delta,
                     "probability_pairwise_improvement_positive": pair_positive,
                     "probability_mean_regret_lower": regret_positive,
                     "meaningful_signal": meaningful, "metric_conflict": conflict},
        "warning": "Offline action ranking only; no gameplay or Silver integration was performed."}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "report.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__": main()
