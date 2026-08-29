#!/usr/bin/env python3
"""Fit a parent-macro linear softmax policy to frozen Silver 25k-A visits.

This is intentionally an offline-only consumer of the frozen 1,788-column
parent-action feature artifact.  It neither regenerates features nor touches
Silver runtime/replay code.  A parent is the indivisible example: all of its
legal siblings receive one softmax and one equally weighted loss term.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize


SEED = 20260829
SPLIT_SALT = "silver-parent-policy-val-v1/"
L2 = 1.0e-4
MAXITER = 500
EPSILON = 1.0e-12
BOOTSTRAP_REPLICATES = 10_000
FROZEN_ACTION_SUFFIX_WIDTH = 20
ARCHIVED_MULTI_ACTION_METRICS = {
    "raw_count_xgboost": {"kl": 1.2347181775827583, "entropy": 1.4032573456696695,
                          "max_mass": 0.3413307749719532},
    "rankshape_calibrated": {"kl": 1.1995325095655576, "entropy": 1.294995340352022,
                               "max_mass": 0.4108398801463227},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()


def stable_softmax(logits: np.ndarray) -> np.ndarray:
    if logits.ndim != 1 or not len(logits) or not np.all(np.isfinite(logits)):
        raise ValueError("softmax requires a non-empty finite legal sibling vector")
    shifted = logits - np.max(logits)
    weights = np.exp(shifted)
    total = float(np.sum(weights))
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("softmax normalization failed")
    result = weights / total
    if (not np.all(np.isfinite(result)) or np.any(result <= 0.0)
            or not np.isclose(float(np.sum(result)), 1.0, rtol=0.0, atol=1e-12)):
        raise ValueError("softmax emitted a non-normalized legal distribution")
    return result


def target_visit_share(rows: list[dict], label: dict) -> np.ndarray:
    visits: dict[str, int] = {}
    for action in label["root_actions"]:
        fingerprint = action["action_fingerprint"]
        if fingerprint in visits:
            raise ValueError(f"duplicate legal action in 25k-A label: {label['group_id']}")
        visits[fingerprint] = int(action["visits"])
    fingerprints = [row["action_fingerprint"] for row in rows]
    if len(set(fingerprints)) != len(fingerprints) or set(fingerprints) != set(visits):
        raise ValueError(f"missing/duplicate legal action surface: {label['group_id']}")
    if any(value < 0 for value in visits.values()):
        raise ValueError(f"negative 25k-A visit count: {label['group_id']}")
    total = sum(visits.values())
    if total <= 0:
        raise ValueError(f"non-positive 25k-A visit total: {label['group_id']}")
    target = np.asarray([visits[fingerprint] / total for fingerprint in fingerprints], dtype=np.float64)
    if (np.any(target < 0.0) or not np.isclose(float(np.sum(target)), 1.0,
                                                 rtol=0.0, atol=1e-12)):
        raise ValueError(f"non-normalized 25k-A visit target: {label['group_id']}")
    return target


def load_features(path: Path) -> tuple[dict, list[str], dict[str, list[dict]]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as stream:
        try:
            header = json.loads(next(stream))
        except StopIteration as exc:
            raise ValueError("empty feature artifact") from exc
        if header.get("feature_schema") != "silver_parent_policy_features_v1":
            raise ValueError("incompatible feature schema")
        names = header.get("feature_names")
        if not isinstance(names, list) or header.get("feature_count") != len(names):
            raise ValueError("invalid feature header width")
        if len(names) != 1788:
            raise ValueError(f"expected frozen 1788-feature schema, got {len(names)}")
        for line_number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            row = json.loads(line)
            group, fingerprint = row.get("group_id"), row.get("action_fingerprint")
            if not isinstance(group, str) or not group or not isinstance(fingerprint, str) or not fingerprint:
                raise ValueError(f"missing parent/action key at feature line {line_number}")
            key = (group, fingerprint)
            if key in seen:
                raise ValueError(f"duplicate feature legal action at line {line_number}: {key}")
            seen.add(key)
            values = row.get("features")
            if not isinstance(values, list) or len(values) != len(names):
                raise ValueError(f"feature width mismatch at line {line_number}")
            if not np.all(np.isfinite(np.asarray(values, dtype=np.float64))):
                raise ValueError(f"non-finite feature at line {line_number}")
            groups[group].append(row)
    for group, rows in groups.items():
        rows.sort(key=lambda row: row["silver_order"])
        orders = [row["silver_order"] for row in rows]
        if len(rows) == 0 or len(set(orders)) != len(orders):
            raise ValueError(f"empty or duplicate sibling order: {group}")
    return header, names, dict(groups)


def load_relabels(path: Path) -> tuple[dict[tuple[str, int, str], dict], set[str], dict]:
    labels: dict[tuple[str, int, str], dict] = {}
    anchors: set[str] = set()
    coverage: Counter = Counter()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1" or row.get("state_kind") != "parent":
                continue
            key = (row["group_id"], int(row["budget"]), row["replicate"])
            if key in labels:
                raise ValueError(f"duplicate parent label at line {line_number}: {key}")
            labels[key] = row
            coverage[f"{key[1]}-{key[2]}-rows"] += 1
            if row.get("teacher_valid", False):
                coverage[f"{key[1]}-{key[2]}-valid"] += 1
            if key[1:] == (25000, "B"):
                anchors.add(key[0])
    if len(anchors) != 93:
        raise ValueError(f"expected exactly 93 frozen 25k-B anchors, got {len(anchors)}")
    return labels, anchors, dict(sorted(coverage.items()))


def b_q(rows: list[dict], label: dict) -> np.ndarray:
    values: dict[str, float] = {}
    if not label.get("teacher_valid", False):
        raise ValueError(f"invalid frozen 25k-B anchor: {label.get('group_id')}")
    for action in label["root_actions"]:
        if not action.get("leaf_root_q_valid", False):
            raise ValueError(f"invalid frozen B action: {label['group_id']}")
        fingerprint = action["action_fingerprint"]
        if fingerprint in values:
            raise ValueError(f"duplicate B legal action: {label['group_id']}")
        values[fingerprint] = float(action["original_root_corrected_q"])
    fingerprints = [row["action_fingerprint"] for row in rows]
    if set(fingerprints) != set(values) or len(fingerprints) != len(values):
        raise ValueError(f"B/action surface mismatch: {label['group_id']}")
    return np.asarray([values[fingerprint] for fingerprint in fingerprints], dtype=np.float64)


def partition(groups: dict[str, list[dict]], anchors: set[str]) -> tuple[set[str], set[str]]:
    nonanchors = set(groups) - anchors
    validation = {group for group in nonanchors if int(hashlib.sha256(
        (SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15}
    train = nonanchors - validation
    if not train or not validation or (train | validation) & anchors or train & validation:
        raise ValueError("invalid parent-level split / anchor leakage")
    return train, validation


def split_name(group: str, train: set[str], validation: set[str]) -> str:
    if group in train:
        return "train"
    if group in validation:
        return "validation"
    return "anchor"


def cross_split_duplicates(values: dict[str, set[str]]) -> dict[str, int]:
    return {f"{left}__{right}": len(values[left] & values[right])
            for left, right in (("train", "validation"), ("train", "anchor"),
                                ("validation", "anchor"))}


def preflight_audit(corpus: Path, names: list[str], groups: dict[str, list[dict]],
                    train: set[str], validation: set[str], anchors: set[str]) -> dict:
    if len(names) != 1788 or len(names) - FROZEN_ACTION_SUFFIX_WIDTH != 1768:
        raise ValueError("unexpected frozen state/action schema partition")
    relevant = set(groups)
    corpus_parent: dict[str, str] = {}
    corpus_seed: dict[str, int] = {}
    with corpus.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("corpus_schema") != "silver_leaf_corpus_v1":
                raise ValueError(f"incompatible corpus schema at line {line_number}")
            group = row.get("group_id")
            if group not in relevant:
                continue
            canonical = json.dumps(row["parent_state"], sort_keys=True, separators=(",", ":"))
            old = corpus_parent.setdefault(group, canonical)
            if old != canonical:
                raise ValueError(f"duplicate parent ID has conflicting canonical state: {group}")
            seed = int(row["run_seed"])
            old_seed = corpus_seed.setdefault(group, seed)
            if old_seed != seed:
                raise ValueError(f"duplicate parent ID has conflicting run seed: {group}")
    missing = sorted(relevant - set(corpus_parent))
    if missing:
        raise ValueError(f"frozen feature parents missing from corpus: {missing[:3]}")
    state_hashes = {name: set() for name in ("train", "validation", "anchor")}
    feature_hashes = {name: set() for name in ("train", "validation", "anchor")}
    seed_sets = {name: set() for name in ("train", "validation", "anchor")}
    varying = []
    for group, rows in groups.items():
        part = split_name(group, train, validation)
        state_hashes[part].add(hashlib.sha256(corpus_parent[group].encode()).hexdigest())
        seed_sets[part].add(corpus_seed[group])
        matrix = np.asarray([row["features"] for row in rows], dtype=np.float64)
        varying.append(int(np.sum(np.any(matrix != matrix[0], axis=0))))
        for row in rows:
            encoded = json.dumps(row["features"], separators=(",", ":"))
            feature_hashes[part].add(hashlib.sha256(encoded.encode()).hexdigest())
    return {"corpus": {"path": str(corpus), "sha256": sha256(corpus), "schema": "silver_leaf_corpus_v1",
                         "parents_found": len(corpus_parent), "duplicate_parent_ids_with_conflicting_state_or_seed": 0},
            "schema": {"feature_schema": "silver_parent_policy_features_v1", "feature_count": len(names),
                       "state_prefix_features": len(names) - FROZEN_ACTION_SUFFIX_WIDTH,
                       "action_suffix_features": FROZEN_ACTION_SUFFIX_WIDTH,
                       "parent_key": "group_id", "explicit_state_action_interaction_features": False},
            "group_assignment": {"all_siblings_assigned_by_parent": True, "parent_counts": {
                "all": len(groups), "train": len(train), "validation": len(validation), "anchors": len(anchors)}},
            "within_parent_varying_features": {"minimum": min(varying), "median": float(np.median(varying)),
                                                "mean": float(np.mean(varying)), "maximum": max(varying),
                                                "histogram": dict(sorted(Counter(varying).items()))},
            "exact_duplicates_across_splits": {"canonical_state": cross_split_duplicates(state_hashes),
                                                 "full_feature_row": cross_split_duplicates(feature_hashes)},
            "seed_overlap": {"train_validation": len(seed_sets["train"] & seed_sets["validation"]),
                             "train_anchor": len(seed_sets["train"] & seed_sets["anchor"]),
                             "validation_anchor": len(seed_sets["validation"] & seed_sets["anchor"]),
                             "unique_seeds": {name: len(values) for name, values in seed_sets.items()}}}


def parent_arrays(groups: dict[str, list[dict]], ids: set[str], labels: dict) -> list[tuple[str, np.ndarray, np.ndarray]]:
    result = []
    for group in sorted(ids):
        label = labels.get((group, 25000, "A"))
        if label is None or not label.get("teacher_valid", False):
            raise ValueError(f"missing valid 25k-A label: {group}")
        rows = groups[group]
        result.append((group, np.asarray([row["features"] for row in rows], dtype=np.float64),
                       target_visit_share(rows, label)))
    return result


def train_scaler(parents: list[tuple[str, np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.concatenate([values for _, values, _ in parents], axis=0)
    mean = np.mean(x, axis=0)
    scale = np.std(x, axis=0)
    active = scale > 1.0e-12
    # Constants have no learned effect.  A finite scale keeps stored inference
    # well-defined even if a held-out row differs in a train-constant column.
    scale = np.where(active, scale, 1.0)
    return mean, scale, active


def scaled(parents: list[tuple[str, np.ndarray, np.ndarray]], mean: np.ndarray,
           scale: np.ndarray, active: np.ndarray) -> list[tuple[str, np.ndarray, np.ndarray]]:
    return [(group, ((x - mean) / scale)[:, active], target) for group, x, target in parents]


def grouped_objective(weights: np.ndarray, parents: list[tuple[str, np.ndarray, np.ndarray]],
                      l2: float = L2) -> tuple[float, np.ndarray]:
    loss = 0.0
    gradient = np.zeros_like(weights)
    for _, x, target in parents:
        prediction = stable_softmax(x @ weights)
        log_prediction = np.log(prediction)
        loss += -float(np.dot(target, log_prediction))
        gradient += x.T @ (prediction - target)
    count = len(parents)
    return loss / count + 0.5 * l2 * float(np.dot(weights, weights)), gradient / count + l2 * weights


def fit_linear(train: list[tuple[str, np.ndarray, np.ndarray]],
               validation: list[tuple[str, np.ndarray, np.ndarray]]) -> tuple[np.ndarray, dict]:
    initial = np.zeros(train[0][1].shape[1], dtype=np.float64)
    history: list[dict] = []
    candidates: list[tuple[np.ndarray, float, int]] = []

    def objective(weights):
        return grouped_objective(weights, train)

    def callback(weights):
        train_loss, _ = grouped_objective(weights, train)
        validation_loss, _ = grouped_objective(weights, validation, l2=0.0)
        history.append({"iteration": len(history) + 1, "train_objective": float(train_loss),
                        "validation_cross_entropy": float(validation_loss)})
        candidates.append((weights.copy(), float(validation_loss), len(history)))

    result = minimize(objective, initial, method="L-BFGS-B", jac=True, callback=callback,
                      options={"maxiter": MAXITER, "gtol": 1e-7, "ftol": 1e-12,
                               "maxls": 50})
    if not np.all(np.isfinite(result.x)):
        raise ValueError("optimizer emitted non-finite weights")
    # Selection is limited to non-anchor validation parents.  L-BFGS-B exposes
    # an iterate through every callback; include the final vector defensively
    # in case its final callback was suppressed by the optimizer.
    initial_validation, _ = grouped_objective(initial, validation, l2=0.0)
    candidates.append((initial.copy(), float(initial_validation), 0))
    final_validation, _ = grouped_objective(result.x, validation, l2=0.0)
    candidates.append((result.x.copy(), float(final_validation), int(result.nit)))
    best, selected_validation, selected_iteration = min(candidates, key=lambda item: item[1])
    return best, {"success": bool(result.success), "status": int(result.status),
                  "message": str(result.message), "iterations": int(result.nit),
                  "function_evaluations": int(result.nfev), "gradient_evaluations": int(result.njev),
                  "callback_history": history,
                  "selected_iteration": int(selected_iteration),
                  "selected_validation_cross_entropy": float(selected_validation),
                  "selected_by": "minimum non-anchor validation cross-entropy among deterministic L-BFGS-B iterates"}


def probabilities(parents: list[tuple[str, np.ndarray, np.ndarray]], weights: np.ndarray) -> dict[str, np.ndarray]:
    return {group: stable_softmax(x @ weights) for group, x, _ in parents}


def entropy(values: np.ndarray) -> float:
    # 0 * log(0) is defined as zero.  Clipped scalar baseline artifacts can
    # contain exact zero prediction mass, unlike the new softmax policy.
    positive = values[values > 0.0]
    return float(-np.sum(positive * np.log(positive)))


def parent_metric(target: np.ndarray, prediction: np.ndarray, b_values: np.ndarray) -> dict:
    if (len(target) != len(prediction) or np.any(prediction < 0.0)
            or not np.isclose(float(np.sum(prediction)), 1.0, rtol=0.0, atol=1e-12)):
        raise ValueError("malformed/non-normalized prediction")
    ce = -float(np.dot(target, np.log(np.maximum(prediction, EPSILON))))
    target_entropy, predicted_entropy = entropy(target), entropy(prediction)
    b_pairs = b_concordance = b_prediction_ties = b_truth_ties = 0.0
    for left in range(len(b_values)):
        for right in range(left + 1, len(b_values)):
            truth_delta = b_values[left] - b_values[right]
            if truth_delta == 0.0:
                b_truth_ties += 1
                continue
            b_pairs += 1
            predicted_delta = prediction[left] - prediction[right]
            if predicted_delta == 0.0:
                b_prediction_ties += 1
                b_concordance += 0.5
            elif (predicted_delta > 0.0) == (truth_delta > 0.0):
                b_concordance += 1.0
    return {
        "cross_entropy": ce,
        "kl": ce - entropy(target),
        "total_variation": 0.5 * float(np.sum(np.abs(target - prediction))),
        "entropy": predicted_entropy,
        "entropy_mae": abs(predicted_entropy - target_entropy),
        "max_mass": float(np.max(prediction)),
        "max_mass_mae": abs(float(np.max(prediction)) - float(np.max(target))),
        "a_max_visit_agreement": float(np.argmax(prediction) == np.argmax(target)),
        "top2_mass_error": abs(float(np.sum(np.sort(prediction)[-min(2, len(prediction)):]))
                               - float(np.sum(np.sort(target)[-min(2, len(target)):]))),
        "top3_mass_error": abs(float(np.sum(np.sort(prediction)[-min(3, len(prediction)):]))
                               - float(np.sum(np.sort(target)[-min(3, len(target)):]))),
        "b_max_q_agreement": float(np.argmax(prediction) == np.argmax(b_values)),
        "b_pairwise_concordance": b_concordance / b_pairs if b_pairs else None,
        "b_pairwise_concordant_credit": b_concordance,
        "prediction_ties": b_prediction_ties,
        "b_q_ties": b_truth_ties,
        "b_q_pairs": b_pairs,
        "legal_actions": len(target),
    }


METRIC_KEYS = ("cross_entropy", "kl", "total_variation", "entropy", "entropy_mae", "max_mass",
               "max_mass_mae", "a_max_visit_agreement", "top2_mass_error", "top3_mass_error",
               "b_max_q_agreement", "b_pairwise_concordance")


def aggregate(per_parent: dict[str, dict]) -> dict:
    summary = {key: float(np.mean([row[key] for row in per_parent.values() if row[key] is not None]))
               for key in METRIC_KEYS}
    pooled_pairs = sum(row["b_q_pairs"] for row in per_parent.values())
    pooled_credit = sum(row["b_pairwise_concordant_credit"] for row in per_parent.values())
    # Historical Silver primary reporting pools pair credit over all 981
    # non-tied B-Q pairs. Preserve the former parent-macro value explicitly.
    summary["b_pairwise_concordance_parent_macro"] = summary["b_pairwise_concordance"]
    summary["b_pairwise_concordance"] = pooled_credit / pooled_pairs if pooled_pairs else None
    summary["b_pairwise_concordance_pooled"] = summary["b_pairwise_concordance"]
    summary.update({"parents": len(per_parent),
                    "legal_action_counts": dict(sorted(Counter(row["legal_actions"] for row in per_parent.values()).items())),
                    "prediction_ties": int(sum(row["prediction_ties"] for row in per_parent.values())),
                    "b_q_ties": int(sum(row["b_q_ties"] for row in per_parent.values())),
                    "b_q_pairs": int(sum(row["b_q_pairs"] for row in per_parent.values())),
                    "malformed_or_missing_rows": 0})
    return summary


def bootstrap_delta(new: dict[str, dict], baseline: dict[str, dict], seed: int) -> dict:
    ids = sorted(new)
    if ids != sorted(baseline):
        raise ValueError("paired bootstrap parent mismatch")
    rng = np.random.default_rng(seed)
    values = {key: [] for key in METRIC_KEYS}
    for _ in range(BOOTSTRAP_REPLICATES):
        selected = rng.choice(ids, size=len(ids), replace=True)
        for key in METRIC_KEYS:
            differences = [new[group][key] - baseline[group][key] for group in selected
                           if new[group][key] is not None and baseline[group][key] is not None]
            values[key].append(float(np.mean(differences)))
    return {key: {"point": float(np.mean([new[group][key] - baseline[group][key] for group in ids
                                           if new[group][key] is not None and baseline[group][key] is not None])),
                  "p025": float(np.quantile(values[key], .025)), "p50": float(np.quantile(values[key], .5)),
                  "p975": float(np.quantile(values[key], .975))}
            for key in METRIC_KEYS}


def load_prediction_artifact(path: Path, anchor_rows: dict[str, list[dict]]) -> dict[str, np.ndarray]:
    with path.open(encoding="utf-8") as stream:
        try:
            header = json.loads(next(stream))
        except StopIteration as exc:
            raise ValueError(f"empty prediction artifact: {path}") from exc
        if header.get("visit_prior_schema") != "silver_parent_visit_prior_predictions_v1":
            raise ValueError(f"incompatible prediction schema: {path}")
        rows = [json.loads(line) for line in stream if line.strip()]
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_parent[row.get("group_id")].append(row)
    if set(by_parent) != set(anchor_rows):
        raise ValueError(f"prediction parent surface mismatch: {path}")
    result = {}
    for group, expected in anchor_rows.items():
        actual = sorted(by_parent[group], key=lambda row: row["silver_order"])
        if ([row["action_fingerprint"] for row in actual]
                != [row["action_fingerprint"] for row in expected]):
            raise ValueError(f"prediction legal action mismatch: {path} / {group}")
        values = np.asarray([row.get("normalized_visit_share") for row in actual], dtype=np.float64)
        if (len(values) != len(expected) or not np.all(np.isfinite(values)) or np.any(values < 0.0)
                or not np.isclose(float(np.sum(values)), 1.0, rtol=0.0, atol=1e-9)):
            raise ValueError(f"prediction is not normalized: {path} / {group}")
        result[group] = values
    return result


def evaluate(anchor: list[tuple[str, np.ndarray, np.ndarray]], b_labels: dict[str, np.ndarray],
             scores: dict[str, np.ndarray]) -> dict[str, dict]:
    return {group: parent_metric(target, scores[group], b_labels[group])
            for group, _, target in anchor}


def archived_reproduction(metrics: dict[str, dict]) -> dict:
    result = {}
    for method, expected in ARCHIVED_MULTI_ACTION_METRICS.items():
        observed = {key: metrics[method][key] for key in expected}
        matches = {key: bool(np.isclose(observed[key], value, rtol=0.0, atol=1e-10))
                   for key, value in expected.items()}
        result[method] = {"expected": expected, "observed": observed, "matches": matches,
                          "pass": all(matches.values())}
    if not all(entry["pass"] for entry in result.values()):
        raise ValueError("frozen raw-count/rank-shape baseline provenance mismatch")
    return result


def report_markdown(report: dict) -> str:
    methods = report["anchor_metrics"]
    lines = ["# Silver grouped linear visit-policy offline report", "",
             f"HEAD: `{report['head']}`  ", f"Fixed L2: `{L2}`; deterministic seed: `{SEED}`.", "",
             "| Method | KL(A || p) | entropy MAE | max-mass MAE | A-top agreement | B pairwise |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, metrics in methods.items():
        lines.append("| {} | {:.6f} | {:.6f} | {:.6f} | {:.2%} | {:.2%} |".format(
            name, metrics["kl"], metrics["entropy_mae"], metrics["max_mass_mae"],
            metrics["a_max_visit_agreement"], metrics["b_pairwise_concordance"]))
    diagnostics = report["offline_diagnostics"]
    lines.extend(["", f"Replay status: **{diagnostics['replay_status']}**.", "",
                  "Offline metrics are diagnostic only. B metrics are reporting-only.", ""])
    return "\n".join(lines)


def a_only_metrics(parents: list[tuple[str, np.ndarray, np.ndarray]],
                   scores: dict[str, np.ndarray]) -> dict[str, float]:
    rows = []
    for group, _, target in parents:
        prediction = scores[group]
        ce = -float(np.dot(target, np.log(np.maximum(prediction, EPSILON))))
        rows.append({"cross_entropy": ce, "kl": ce - entropy(target)})
    return {key: float(np.mean([row[key] for row in rows])) for key in ("cross_entropy", "kl")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("raw_count_predictions", type=Path)
    parser.add_argument("rankshape_predictions", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--corpus", type=Path, required=True,
                        help="immutable selected silver_leaf_corpus_v1 JSONL (audited, never fitted)")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    np.random.seed(SEED)

    header, names, groups = load_features(args.features)
    labels, anchors, coverage = load_relabels(args.relabels)
    train_ids, validation_ids = partition(groups, anchors)
    preflight = preflight_audit(args.corpus, names, groups, train_ids, validation_ids, anchors)
    anchor_ids = set(anchors)
    for group in anchor_ids:
        if group not in groups:
            raise ValueError(f"anchor absent from frozen features: {group}")
        if (group, 25000, "A") not in labels or (group, 25000, "B") not in labels:
            raise ValueError(f"missing 25k A/B anchor label: {group}")
    train_raw = parent_arrays(groups, train_ids, labels)
    validation_raw = parent_arrays(groups, validation_ids, labels)
    all_anchor_raw = parent_arrays(groups, anchor_ids, labels)
    anchor_raw = [row for row in all_anchor_raw if len(row[1]) > 1]
    if len(anchor_raw) != 63:
        raise ValueError(f"expected exactly 63 multi-action anchors, got {len(anchor_raw)}")
    b_labels = {group: b_q(groups[group], labels[(group, 25000, "B")]) for group, _, _ in anchor_raw}
    all_anchor_rows = {group: groups[group] for group, _, _ in all_anchor_raw}
    raw_all_scores = load_prediction_artifact(args.raw_count_predictions, all_anchor_rows)
    rank_all_scores = load_prediction_artifact(args.rankshape_predictions, all_anchor_rows)
    raw_scores = {group: raw_all_scores[group] for group, _, _ in anchor_raw}
    rank_scores = {group: rank_all_scores[group] for group, _, _ in anchor_raw}
    baseline_anchor_metrics = {
        "raw_count_xgboost": aggregate(evaluate(anchor_raw, b_labels, raw_scores)),
        "rankshape_calibrated": aggregate(evaluate(anchor_raw, b_labels, rank_scores)),
    }
    reproduction = archived_reproduction(baseline_anchor_metrics)
    mean, scale, active = train_scaler(train_raw)
    train = scaled(train_raw, mean, scale, active)
    validation = scaled(validation_raw, mean, scale, active)
    anchor = scaled(anchor_raw, mean, scale, active)
    weights_active, optimizer = fit_linear(train, validation)
    weights = np.zeros(len(names), dtype=np.float64)
    weights[active] = weights_active
    train_scores, validation_scores, new_scores = (probabilities(train, weights_active),
                                                    probabilities(validation, weights_active),
                                                    probabilities(anchor, weights_active))
    uniform_scores = {group: np.full(len(target), 1.0 / len(target)) for group, _, target in anchor}
    oracle_scores = {group: target for group, _, target in anchor}
    per_method = {"uniform": evaluate(anchor, b_labels, uniform_scores),
                  "raw_count_xgboost": evaluate(anchor, b_labels, raw_scores),
                  "rankshape_calibrated": evaluate(anchor, b_labels, rank_scores),
                  "linear_grouped_policy": evaluate(anchor, b_labels, new_scores),
                  "oracle_a_visit": evaluate(anchor, b_labels, oracle_scores)}
    anchor_metrics = {name: aggregate(values) for name, values in per_method.items()}
    train_metrics = a_only_metrics(train, train_scores)
    validation_metrics = a_only_metrics(validation, validation_scores)
    bootstrap_raw = bootstrap_delta(per_method["linear_grouped_policy"], per_method["raw_count_xgboost"], SEED + 1)
    bootstrap_rank = bootstrap_delta(per_method["linear_grouped_policy"], per_method["rankshape_calibrated"], SEED + 2)
    rank_ci = bootstrap_rank
    offline_diagnostics = {
        "offline_metrics_are_diagnostic_only": True,
        "replay_status": "REPLAY_PENDING",
        "integrity_and_provenance_checks_passed": True,
        "offline_metrics_block_replay": False,
        "note": "Only an integrity or compatibility failure blocks the frozen replay; do not infer replay eligibility from these diagnostics.",
    }
    prediction_path = args.output_dir / "linear_grouped_policy_anchor_probabilities.jsonl"
    with prediction_path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"schema": "silver_grouped_linear_policy_predictions_v1", "feature_schema": header["feature_schema"],
                                 "feature_count": len(names), "parent_key": "group_id", "target": "normalized_25k_A_visits"}, sort_keys=True) + "\n")
        for group, _, target in anchor:
            for row, value, truth in zip(groups[group], new_scores[group], target):
                stream.write(json.dumps({"group_id": group, "action_fingerprint": row["action_fingerprint"],
                                         "silver_order": row["silver_order"], "probability": float(value),
                                         "a_visit_share": float(truth)}, sort_keys=True) + "\n")
    model_path = args.output_dir / "linear_grouped_policy_model.npz"
    np.savez(model_path, feature_names=np.asarray(names), weights=weights, mean=mean, scale=scale,
             active=active.astype(np.uint8), l2=np.asarray([L2]), seed=np.asarray([SEED]))
    report = {"schema": "silver_grouped_linear_policy_report_v1", "head": git_head(), "seed": SEED,
              "fixed_l2": L2, "optimizer": {"method": "scipy.optimize.minimize/L-BFGS-B", **optimizer},
              "dimensions": {"frozen_feature_count": len(names), "active_train_scaled_features": int(np.sum(active)), "bias": False},
              "parent_key": "group_id", "target": "exact normalized 25k-A root visits", "inputs": {
                  "features": str(args.features), "features_sha256": sha256(args.features), "corpus": str(args.corpus), "corpus_sha256": sha256(args.corpus), "relabels": str(args.relabels), "relabels_sha256": sha256(args.relabels),
                  "raw_count_predictions": str(args.raw_count_predictions), "raw_count_predictions_sha256": sha256(args.raw_count_predictions),
                  "rankshape_predictions": str(args.rankshape_predictions), "rankshape_predictions_sha256": sha256(args.rankshape_predictions)},
              "split": {"salt": SPLIT_SALT, "train_parents": len(train), "validation_parents": len(validation), "anchor_parents": len(anchors), "multi_action_anchors": len(anchor),
                        "train_action_rows": int(sum(len(x) for _, x, _ in train)), "validation_action_rows": int(sum(len(x) for _, x, _ in validation)), "anchor_action_rows": int(sum(len(x) for _, x, _ in anchor)),
                        "anchor_excluded_from_training_scaling_validation_and_tuning": True},
              "preflight": preflight, "archived_baseline_reproduction": reproduction,
              "coverage": {"relabels": coverage, "malformed_or_missing_anchor_rows": 0}, "underfit_evidence": {
                  "training_cross_entropy": train_metrics["cross_entropy"], "training_kl": train_metrics["kl"],
                  "validation_cross_entropy": validation_metrics["cross_entropy"], "validation_kl": validation_metrics["kl"],
                  "validation_minus_training_cross_entropy": validation_metrics["cross_entropy"] - train_metrics["cross_entropy"],
                  "validation_minus_training_kl": validation_metrics["kl"] - train_metrics["kl"]},
              "anchor_metrics": anchor_metrics, "paired_bootstrap_95_ci": {"new_minus_raw_count": bootstrap_raw, "new_minus_rankshape": bootstrap_rank},
              "offline_diagnostics": offline_diagnostics,
              "artifacts": {"model": {"path": str(model_path), "sha256": sha256(model_path)}, "anchor_probabilities": {"path": str(prediction_path), "sha256": sha256(prediction_path)}}}
    report_path = args.output_dir / "aggregate_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    human_path = args.output_dir / "report.md"
    human_path.write_text(report_markdown(report), encoding="utf-8")
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"head": report["head"], "command": " ".join(map(str, __import__('sys').argv)),
                                         "seed": SEED, "fixed_l2": L2, "dimensions": report["dimensions"], "split": report["split"],
                                         "inputs": report["inputs"], "outputs": {"aggregate_report": sha256(report_path), "human_report": sha256(human_path),
                                         "model": sha256(model_path), "anchor_probabilities": sha256(prediction_path)}}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
