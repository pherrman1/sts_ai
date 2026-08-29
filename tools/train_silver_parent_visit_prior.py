#!/usr/bin/env python3
"""Train and evaluate a scalar Silver parent-action visit-share prior.

This is an offline diagnostic companion to train_silver_parent_policy.py.  It
uses the same canonical features, non-anchor split, XGBoost recipe, and model
capacity; only the target changes from centered Q to the normalized 25k-A
root-visit share.  The output JSONL is an offline replay artifact, not a
runtime model integration.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_silver_parent_policy as parent  # noqa: E402


def visit_shares(rows, label):
    label_visits = {
        action["action_fingerprint"]: int(action["visits"])
        for action in label["root_actions"]
    }
    fingerprints = [row["action_fingerprint"] for row in rows]
    if set(fingerprints) != set(label_visits) or len(fingerprints) != len(label_visits):
        raise ValueError("feature/visit action surface mismatch")
    total = sum(label_visits.values())
    if total <= 0:
        raise ValueError("non-positive 25k-A visit total")
    return np.asarray([label_visits[fp] / total for fp in fingerprints], dtype=float)


def normalize_predictions(raw):
    raw = np.asarray(raw, dtype=float)
    clipped = np.maximum(raw, 0.0)
    if np.sum(clipped) <= 0.0:
        return np.full(len(raw), 1.0 / len(raw)), True, clipped
    return clipped / np.sum(clipped), False, clipped


def pearson(truth, prediction):
    if len(truth) < 2 or np.std(truth) == 0 or np.std(prediction) == 0:
        return None
    return float(np.corrcoef(truth, prediction)[0, 1])


def json_safe_metrics(metrics):
    """Convert undefined correlations from tied groups to strict JSON null."""
    return {
        key: None if isinstance(value, float) and not math.isfinite(value) else value
        for key, value in metrics.items()
    }


def distribution_metrics(test, raw_scores, normalized_scores):
    truth_flat = []
    pred_flat = []
    per_parent_kl = []
    for group in sorted(test):
        truth = visit_shares(test[group], raw_scores[group]["label"])
        prediction = normalized_scores[group]
        truth_flat.extend(truth)
        pred_flat.extend(prediction)
        epsilon_prediction = np.maximum(prediction, 1e-12)
        per_parent_kl.append(float(np.sum(truth * np.log(truth / epsilon_prediction))))
    truth_flat = np.asarray(truth_flat)
    pred_flat = np.asarray(pred_flat)
    error = pred_flat - truth_flat
    return {
        "action_rows": len(truth_flat),
        "pearson": pearson(truth_flat, pred_flat),
        "spearman": parent.spearman(truth_flat, pred_flat),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "mean_parent_kl_a_to_prediction": statistics.fmean(per_parent_kl),
        "median_parent_kl_a_to_prediction": statistics.median(per_parent_kl),
    }


def top_agreement(test, labels, scores, against):
    agreements = []
    for group in sorted(test):
        rows = test[group]
        chosen = int(np.argmax(scores[group]))
        if against == "A":
            truth = visit_shares(rows, labels[(group, 25000, "A")])
            best = int(np.argmax(truth))
        else:
            truth = np.asarray([row["reference_q"] for row in rows], dtype=float)
            best = int(np.argmax(truth))
        agreements.append(chosen == best)
    return {
        "parents": len(agreements),
        "agreement": statistics.fmean(agreements),
        "correct": sum(agreements),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--smoke-rounds", type=int, default=0)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    header, names, groups = parent.load_features(args.features)
    labels, anchors, relabel_coverage = parent.load_relabels(args.relabels)
    test, test_exclusions = parent.attach_reference(groups, labels, anchors)
    nonanchors = sorted(set(groups) - anchors)
    validation = {
        group for group in nonanchors
        if int(parent.hashlib.sha256((parent.SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15
    }
    train = set(nonanchors) - validation
    if not train or not validation:
        raise SystemExit("empty deterministic train/validation split")
    if (train | validation) & anchors:
        raise SystemExit("anchor leakage")

    # The target is sourced from the frozen A relabel rows.  The feature rows'
    # retained visits_25k_a metadata are cross-checked but never enter X.
    metadata_mismatches = 0
    target_cache = {}
    for group in sorted(set(groups)):
        label = labels.get((group, 25000, "A"))
        if label is None or not label.get("teacher_valid", False):
            raise SystemExit(f"missing valid 25k-A label for feature group {group}")
        target = visit_shares(groups[group], label)
        target_cache[group] = target
        for row, share in zip(groups[group], target):
            expected = row.get("visits_25k_a")
            if expected is None or int(expected) != round(share * sum(
                    int(action["visits"]) for action in label["root_actions"])):
                metadata_mismatches += 1

    train_rows = parent.flatten(groups, train)
    val_rows = parent.flatten(groups, validation)
    xtr = np.asarray([row["features"] for row in train_rows], dtype=np.float32)
    xva = np.asarray([row["features"] for row in val_rows], dtype=np.float32)
    ytr = np.concatenate([target_cache[group] for group in sorted(train)]).astype(np.float32)
    yva = np.concatenate([target_cache[group] for group in sorted(validation)]).astype(np.float32)
    params = {**parent.PARAMS, "device": args.device}
    rounds = args.smoke_rounds or 2000
    dtr = xgb.QuantileDMatrix(xtr, label=ytr, feature_names=names)
    dva = xgb.QuantileDMatrix(xva, label=yva, ref=dtr, feature_names=names)
    model = xgb.train(
        params, dtr, num_boost_round=rounds, evals=[(dva, "validation")],
        early_stopping_rounds=None if args.smoke_rounds else 40,
        verbose_eval=100,
    )
    best_iteration = rounds - 1 if args.smoke_rounds else model.best_iteration
    model_path = args.output_dir / "silver_parent_visit_prior_25k.json"
    model.save_model(model_path)

    test_rows = parent.flatten(test, test)
    xtest = np.asarray([row["features"] for row in test_rows], dtype=np.float32)
    raw_prediction = model.predict(
        xgb.DMatrix(xtest, feature_names=names),
        iteration_range=(0, best_iteration + 1),
    )
    raw_scores = {}
    normalized_scores = {}
    offset = 0
    fallback_groups = []
    for group in sorted(test):
        count = len(test[group])
        raw = np.asarray(raw_prediction[offset:offset + count], dtype=float)
        offset += count
        normalized, fallback, _ = normalize_predictions(raw)
        raw_scores[group] = {"values": raw, "label": labels[(group, 25000, "A")]}
        normalized_scores[group] = normalized
        if fallback:
            fallback_groups.append(group)

    replay_path = args.output_dir / "silver_parent_visit_prior_predictions.jsonl"
    with replay_path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "visit_prior_schema": "silver_parent_visit_prior_predictions_v1",
            "feature_schema": header["feature_schema"],
            "feature_count": len(names),
            "target": "normalized_visits_25k_A",
            "model": str(model_path),
        }, sort_keys=True) + "\n")
        for group in sorted(test):
            rows = test[group]
            raw = raw_scores[group]["values"]
            normalized = normalized_scores[group]
            actual = target_cache[group]
            for row, raw_value, normalized_value, actual_value in zip(
                    rows, raw, normalized, actual):
                stream.write(json.dumps({
                    "group_id": group,
                    "action_fingerprint": row["action_fingerprint"],
                    "silver_order": row["silver_order"],
                    "a_visit_share": float(actual_value),
                    "raw_prediction": float(raw_value),
                    "clipped_prediction": float(max(raw_value, 0.0)),
                    "normalized_visit_share": float(normalized_value),
                }, sort_keys=True) + "\n")

    current_scores = {
        group: np.asarray([-row["silver_order"] for row in rows], dtype=float)
        for group, rows in test.items()
    }
    model_metrics, _ = parent.group_metrics(test, normalized_scores)
    current_metrics, _ = parent.group_metrics(test, current_scores)
    multi = {group: rows for group, rows in test.items() if len(rows) > 1}
    multi_model = {group: normalized_scores[group] for group in multi}
    multi_current = {group: current_scores[group] for group in multi}
    multi_metrics, _ = parent.group_metrics(multi, multi_model)
    multi_current_metrics, _ = parent.group_metrics(multi, multi_current)
    model_metrics = json_safe_metrics(model_metrics)
    current_metrics = json_safe_metrics(current_metrics)
    multi_metrics = json_safe_metrics(multi_metrics)
    multi_current_metrics = json_safe_metrics(multi_current_metrics)

    raw_flat = np.concatenate([raw_scores[group]["values"] for group in sorted(test)])
    clipped_flat = np.maximum(raw_flat, 0.0)
    clipping = {
        "raw_negative_action_count": int(np.sum(raw_flat < 0.0)),
        "raw_zero_action_count": int(np.sum(raw_flat == 0.0)),
        "clipped_zero_action_count": int(np.sum(clipped_flat == 0.0)),
        "negative_mass_clipped": float(np.sum(np.maximum(-raw_flat, 0.0))),
        "all_zero_fallback_parent_count": len(fallback_groups),
        "all_zero_fallback_groups": fallback_groups,
        "feature_visit_metadata_mismatches": metadata_mismatches,
    }
    report = {
        "schema": "silver_parent_visit_prior_experiment_v1",
        "inputs": {
            "features": str(args.features),
            "features_sha256": parent.sha256(args.features),
            "relabels": str(args.relabels),
            "relabels_sha256": parent.sha256(args.relabels),
        },
        "coverage": {"relabels": relabel_coverage, "test_exclusions": test_exclusions},
        "split": {
            "train_parents": len(train), "validation_parents": len(validation),
            "test_parents": len(test), "multi_action_test_parents": len(multi),
            "anchor_parents_identified_before_modeling": len(anchors),
            "anchor_leakage": False, "salt": parent.SPLIT_SALT,
            "train_action_rows": len(train_rows), "validation_action_rows": len(val_rows),
            "test_action_rows": len(test_rows),
        },
        "feature_schema": {"name": header["feature_schema"], "count": len(names)},
        "target": "normalized 25k-A root visit fraction within each legal sibling group",
        "recipe": {
            "params": params, "num_boost_round": rounds,
            "early_stopping_rounds": None if args.smoke_rounds else 40,
            "best_iteration": best_iteration, "hyperparameter_sweep": False,
            "architecture": "same scalar XGBoost recipe as silver_parent_policy_25k",
        },
        "model": {"path": str(model_path), "sha256": parent.sha256(model_path)},
        "prediction_artifact": {"path": str(replay_path), "sha256": parent.sha256(replay_path)},
        "offline_distribution": {
            "all_held_out_25k_b_anchors": distribution_metrics(test, raw_scores, normalized_scores),
            "multi_action_held_out_25k_b_anchors": distribution_metrics(multi, raw_scores, normalized_scores),
        },
        "top_prior_agreement": {
            "all_held_out_25k_b_anchors": {
                "against_A_visits": top_agreement(test, labels, normalized_scores, "A"),
                "against_B_q": top_agreement(test, labels, normalized_scores, "B"),
            },
            "multi_action_held_out_25k_b_anchors": {
                "against_A_visits": top_agreement(multi, labels, multi_model, "A"),
                "against_B_q": top_agreement(multi, labels, multi_model, "B"),
            },
        },
        "ordering_against_frozen_25k_b_q": {
            "all_held_out_25k_b_anchors": model_metrics,
            "multi_action_held_out_25k_b_anchors": multi_metrics,
            "current_ordering_multi_action_reference": multi_current_metrics,
        },
        "clipping_and_fallback": clipping,
        "replay_contract": {
            "clamp_negative_predictions_to_zero": True,
            "normalize_within_legal_siblings": True,
            "fallback": "uniform if all clipped predictions are zero",
            "replay_parents": sorted(multi),
            "native_model_parity": "not applicable; C++ replay consumes this frozen offline prediction artifact",
        },
        "warning": "Descriptive held-out A-visit fit; frozen 25k-B is used only for ordering diagnostics and replay judgment.",
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
