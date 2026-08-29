#!/usr/bin/env python3
"""Fit one validation-only power calibration for frozen raw visit scores."""

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


EPSILON = 1e-12


def calibrated(raw, alpha):
    z = np.maximum(np.asarray(raw, dtype=float), 0.0) + EPSILON
    weights = np.power(z, alpha)
    total = np.sum(weights)
    if not np.isfinite(total) or total <= 0.0:
        return np.full(len(z), 1.0 / len(z))
    return weights / total


def raw_normalized(raw):
    clipped = np.maximum(np.asarray(raw, dtype=float), 0.0)
    total = np.sum(clipped)
    if not np.isfinite(total) or total <= 0.0:
        return np.full(len(clipped), 1.0 / len(clipped))
    return clipped / total


def target_shares(rows, label):
    visits = {action["action_fingerprint"]: int(action["visits"])
              for action in label["root_actions"]}
    if {row["action_fingerprint"] for row in rows} != set(visits):
        raise ValueError("feature/A action surface mismatch")
    total = sum(visits.values())
    if total <= 0:
        raise ValueError("non-positive A visit total")
    return np.asarray([visits[row["action_fingerprint"]] / total for row in rows], dtype=float)


def cross_entropy(target, prediction):
    return float(-np.sum(target * np.log(np.maximum(prediction, EPSILON))))


def validation_objective(groups, raw_scores, alpha):
    return statistics.fmean(
        cross_entropy(target_shares(groups[group], raw_scores[group]["label"]),
                      calibrated(raw_scores[group]["values"], alpha))
        for group in sorted(groups)
    )


def derivative(groups, raw_scores, alpha):
    values = []
    for group in sorted(groups):
        target = target_shares(groups[group], raw_scores[group]["label"])
        z = np.maximum(raw_scores[group]["values"], 0.0) + EPSILON
        log_z = np.log(z)
        prediction = calibrated(raw_scores[group]["values"], alpha)
        values.append(float(np.sum(prediction * log_z) - np.sum(target * log_z)))
    return statistics.fmean(values)


def fit_alpha(groups, raw_scores):
    lower = 1e-9
    lower_derivative = derivative(groups, raw_scores, lower)
    if lower_derivative >= 0.0:
        return lower, "lower_boundary"
    upper = 1.0
    while derivative(groups, raw_scores, upper) < 0.0 and upper < 1e6:
        upper *= 2.0
    if upper >= 1e6 and derivative(groups, raw_scores, upper) < 0.0:
        raise ValueError("validation cross-entropy has no bounded minimum")
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if derivative(groups, raw_scores, midpoint) < 0.0:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0, "bisection_derivative"


def load_anchor_predictions(path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("visit_prior_schema") != "silver_parent_visit_prior_predictions_v1":
        raise ValueError("unexpected raw prediction schema")
    groups = {}
    for row in rows:
        groups.setdefault(row["group_id"], []).append(row)
    for values in groups.values():
        values.sort(key=lambda row: row["silver_order"])
    return header, groups


def prediction_summary(groups, scores):
    entropies = []
    tops = []
    for group in sorted(groups):
        values = scores[group]
        entropies.append(float(-np.sum(values * np.log(np.maximum(values, EPSILON)))))
        tops.append(float(np.max(values)))
    return {
        "mean_entropy": statistics.fmean(entropies),
        "mean_top1_mass": statistics.fmean(tops),
    }


def json_safe(metrics):
    return {
        key: None if isinstance(value, float) and not math.isfinite(value) else value
        for key, value in metrics.items()
    }


def anchor_metrics(groups, scores):
    metrics, _ = parent.group_metrics(groups, scores)
    return json_safe(metrics)


def agreement(groups, scores, labels, against):
    correct = 0
    for group in sorted(groups):
        if against == "A":
            best = int(np.argmax(target_shares(groups[group], labels[(group, 25000, "A")])))
        else:
            best = int(np.argmax([row["reference_q"] for row in groups[group]]))
        correct += int(np.argmax(scores[group]) == best)
    return {"correct": correct, "parents": len(groups), "agreement": correct / len(groups)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("raw_anchor_predictions", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    header, names, feature_groups = parent.load_features(args.features)
    labels, anchors, coverage = parent.load_relabels(args.relabels)
    test, exclusions = parent.attach_reference(feature_groups, labels, anchors)
    nonanchors = sorted(set(feature_groups) - anchors)
    validation_ids = {
        group for group in nonanchors
        if int(parent.hashlib.sha256((parent.SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15
    }
    if len(validation_ids) != 75:
        raise ValueError(f"expected 75 validation parents, found {len(validation_ids)}")
    validation = {group: feature_groups[group] for group in sorted(validation_ids)}
    for group in validation:
        if ((group, 25000, "A") not in labels
                or not labels[(group, 25000, "A")].get("teacher_valid", False)):
            raise ValueError(f"missing valid A validation label: {group}")

    booster = xgb.Booster()
    booster.load_model(args.model)
    best_iteration = int(booster.attr("best_iteration"))
    val_rows = parent.flatten(validation, validation)
    xval = np.asarray([row["features"] for row in val_rows], dtype=np.float32)
    raw_flat = booster.predict(
        xgb.DMatrix(xval, feature_names=names),
        iteration_range=(0, best_iteration + 1),
    )
    validation_raw = {}
    offset = 0
    for group in sorted(validation):
        count = len(validation[group])
        validation_raw[group] = {
            "values": np.asarray(raw_flat[offset:offset + count], dtype=float),
            "label": labels[(group, 25000, "A")],
        }
        offset += count

    alpha, optimizer = fit_alpha(validation, validation_raw)
    validation_before = {
        group: raw_normalized(validation_raw[group]["values"])
        for group in validation
    }
    validation_after = {
        group: calibrated(validation_raw[group]["values"], alpha)
        for group in validation
    }
    validation_teacher = {
        group: target_shares(validation[group], labels[(group, 25000, "A")])
        for group in validation
    }
    validation_kl_before = statistics.fmean(
        cross_entropy(validation_teacher[group], validation_before[group])
        - cross_entropy(validation_teacher[group], validation_teacher[group])
        for group in validation
    )
    validation_kl_after = statistics.fmean(
        cross_entropy(validation_teacher[group], validation_after[group])
        - cross_entropy(validation_teacher[group], validation_teacher[group])
        for group in validation
    )
    validation_entropy = {
        "teacher": prediction_summary(validation, validation_teacher),
        "before": prediction_summary(validation, validation_before),
        "after": prediction_summary(validation, validation_after),
    }

    raw_header, raw_anchor_rows = load_anchor_predictions(args.raw_anchor_predictions)
    if set(raw_anchor_rows) != set(test):
        raise ValueError("raw prediction/test anchor groups mismatch")
    raw_scores = {}
    raw_anchor_normalized = {}
    calibrated_scores = {}
    ranking_changes = []
    for group in sorted(test):
        rows = test[group]
        prediction_rows = raw_anchor_rows[group]
        if [row["action_fingerprint"] for row in prediction_rows] != [row["action_fingerprint"] for row in rows]:
            raise ValueError(f"raw prediction action surface mismatch: {group}")
        raw = np.asarray([row["raw_prediction"] for row in prediction_rows], dtype=float)
        raw_scores[group] = {"values": raw, "label": labels[(group, 25000, "A")]}
        raw_anchor_normalized[group] = raw_normalized(raw)
        calibrated_scores[group] = calibrated(raw, alpha)
        old_order = np.argsort(-np.maximum(raw, 0.0), kind="stable").tolist()
        new_order = np.argsort(-calibrated_scores[group], kind="stable").tolist()
        ranking_changes.append(old_order != new_order)

    multi = {group: rows for group, rows in test.items() if len(rows) > 1}
    raw_multi = {group: raw_anchor_normalized[group] for group in multi}
    calibrated_multi = {group: calibrated_scores[group] for group in multi}
    teacher_multi = {
        group: target_shares(multi[group], labels[(group, 25000, "A")])
        for group in multi
    }
    raw_metrics = anchor_metrics(multi, raw_multi)
    calibrated_metrics = anchor_metrics(multi, calibrated_multi)
    raw_metrics["top_prior_a_agreement"] = agreement(multi, raw_multi, labels, "A")
    raw_metrics["top_prior_b_agreement"] = agreement(multi, raw_multi, labels, "B")
    calibrated_metrics["top_prior_a_agreement"] = agreement(multi, calibrated_multi, labels, "A")
    calibrated_metrics["top_prior_b_agreement"] = agreement(multi, calibrated_multi, labels, "B")
    raw_mass = prediction_summary(multi, raw_multi)
    calibrated_mass = prediction_summary(multi, calibrated_multi)
    teacher_mass = prediction_summary(multi, teacher_multi)
    raw_flat_anchor = np.concatenate([raw_scores[group]["values"] for group in sorted(multi)])
    calibrated_flat = np.concatenate([calibrated_scores[group] for group in sorted(multi)])
    multi_ranking_changes = [ranking_changes[index] for index, group in enumerate(sorted(test))
                             if group in multi]
    ranking_metrics = {
        "parents": len(multi_ranking_changes),
        "ranking_changes": sum(multi_ranking_changes),
        "ranking_unchanged": len(multi_ranking_changes) - sum(multi_ranking_changes),
        "raw_prediction_minimum": float(np.min(raw_flat_anchor)),
        "raw_prediction_maximum": float(np.max(raw_flat_anchor)),
        "raw_prediction_variance": float(np.var(raw_flat_anchor)),
        "calibrated_prediction_minimum": float(np.min(calibrated_flat)),
        "calibrated_prediction_maximum": float(np.max(calibrated_flat)),
        "calibrated_prediction_variance": float(np.var(calibrated_flat)),
    }

    output_path = args.output_dir / "silver_parent_visit_prior_calibrated_predictions.jsonl"
    with output_path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "visit_prior_schema": "silver_parent_visit_prior_predictions_v1",
            "feature_schema": header["feature_schema"],
            "feature_count": len(names),
            "target": "raw_visits_25k_A_power_calibrated",
            "alpha": alpha,
            "epsilon": EPSILON,
        }, sort_keys=True) + "\n")
        for group in sorted(test):
            for row, value in zip(test[group], calibrated_scores[group]):
                stream.write(json.dumps({
                    "group_id": group,
                    "action_fingerprint": row["action_fingerprint"],
                    "silver_order": row["silver_order"],
                    "normalized_visit_share": float(value),
                }, sort_keys=True) + "\n")

    report = {
        "schema": "silver_visit_prior_calibration_v1",
        "inputs": {
            "features": str(args.features), "features_sha256": parent.sha256(args.features),
            "relabels": str(args.relabels), "relabels_sha256": parent.sha256(args.relabels),
            "model": str(args.model), "model_sha256": parent.sha256(args.model),
            "raw_anchor_predictions": str(args.raw_anchor_predictions),
            "raw_anchor_predictions_sha256": parent.sha256(args.raw_anchor_predictions),
        },
        "split": {
            "validation_parents": len(validation),
            "validation_action_rows": len(val_rows),
            "anchor_parents": len(test),
            "multi_action_anchor_parents": len(multi),
            "anchor_leakage": False,
            "salt": parent.SPLIT_SALT,
        },
        "fit": {
            "alpha": alpha,
            "optimizer": optimizer,
            "epsilon": EPSILON,
            "best_iteration": best_iteration,
            "uses_25k_b_for_alpha": False,
            "model_training": False,
        },
        "validation": {
            "mean_kl_before": validation_kl_before,
            "mean_kl_after": validation_kl_after,
            "mean_kl_reduction": validation_kl_before - validation_kl_after,
            "entropy_and_top1_mass": validation_entropy,
        },
        "multi_action_anchor_mass": {
            "teacher_a": teacher_mass,
            "raw_learned": raw_mass,
            "calibrated": calibrated_mass,
            "raw_kl_a_to_prior": statistics.fmean(
                cross_entropy(teacher_multi[group], raw_multi[group])
                - cross_entropy(teacher_multi[group], teacher_multi[group])
                for group in multi
            ),
            "calibrated_kl_a_to_prior": statistics.fmean(
                cross_entropy(teacher_multi[group], calibrated_multi[group])
                - cross_entropy(teacher_multi[group], teacher_multi[group])
                for group in multi
            ),
        },
        "multi_action_anchor_ranking": {
            "raw_learned": raw_metrics,
            "calibrated": calibrated_metrics,
            "rank_preservation": ranking_metrics,
        },
        "output": {"path": str(output_path), "sha256": parent.sha256(output_path)},
        "coverage": {"relabels": coverage, "test_exclusions": exclusions, "raw_header": raw_header},
        "warning": "Alpha was selected only on non-anchor validation A visits; 25k-B is used only for held-out anchor diagnostics.",
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
