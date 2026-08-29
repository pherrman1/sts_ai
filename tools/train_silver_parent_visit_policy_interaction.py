#!/usr/bin/env python3
"""Fit the fixed rank-4 state x action residual on frozen grouped logits.

The grouped-linear artifact is the immutable zero-residual submodel.  This
script deliberately imports its feature loading, parent split, scaler, target,
and metric contracts instead of reimplementing a second policy pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch


BASE = Path(__file__).with_name("train_silver_parent_visit_policy.py")
_spec = importlib.util.spec_from_file_location("silver_grouped_linear", BASE)
linear = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(linear)

SEED = 20260830
RANK = 4
L2 = 1.0e-4
MAX_ITER = 500
HISTORY_SIZE = 50
FEATURE_HASH = "0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd"
CORPUS_HASH = "bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7"
RELABEL_HASH = "abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c"
LINEAR_MODEL_HASH = "a9276d735669f9ff28b83d95c5bcd57d1dcb135b97eb55d1cd774aa2c4782eab"
LINEAR_PROBABILITY_HASH = "51534736ce59c62d92841867ceac0f4f06e03023997aaba7404f75f6412e9b2a"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path: Path, expected: str, name: str) -> str:
    observed = sha256(path)
    if observed != expected:
        raise ValueError(f"immutable {name} hash mismatch: {observed} != {expected}")
    return observed


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def deterministic_torch() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_default_dtype(torch.float64)
    if torch.get_num_threads() != 1:
        torch.set_num_threads(1)


def load_linear_model(path: Path, names: list[str]) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as model:
        required = {"feature_names", "weights", "mean", "scale", "active", "l2", "seed"}
        if set(model.files) != required:
            raise ValueError("unexpected frozen grouped-linear model fields")
        result = {key: np.asarray(model[key]) for key in model.files}
    if list(result["feature_names"].astype(str)) != names:
        raise ValueError("frozen grouped-linear feature names differ from feature artifact")
    for key in ("weights", "mean", "scale", "active"):
        if result[key].shape != (len(names),):
            raise ValueError(f"frozen grouped-linear {key} shape mismatch")
    if not np.all(np.isfinite(result["weights"])) or not np.all(np.isfinite(result["mean"])):
        raise ValueError("non-finite grouped-linear arrays")
    if np.any(result["scale"] <= 0.0) or not np.array_equal(result["active"], result["active"].astype(bool)):
        raise ValueError("invalid grouped-linear scaler arrays")
    if not np.array_equal(result["weights"][~result["active"].astype(bool)],
                          np.zeros(np.sum(~result["active"].astype(bool)))):
        raise ValueError("inactive grouped-linear coefficient is non-zero")
    if float(result["l2"][0]) != L2:
        raise ValueError("frozen grouped-linear L2 differs from fixed interaction contract")
    return result


def full_standardize(parents, mean, scale, active):
    """Reuse the grouped scaler exactly and hard-mask train-inactive columns."""
    mask = active.astype(np.float64)
    return [(group, ((x - mean) / scale) * mask, target) for group, x, target in parents]


def load_grouped_probabilities(path: Path, anchor_rows: dict[str, list[dict]]) -> dict[str, np.ndarray]:
    """Read the immutable grouped-policy probability artifact without conversion."""
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if (header.get("schema") != "silver_grouped_linear_policy_predictions_v1"
            or header.get("feature_count") != 1788 or header.get("parent_key") != "group_id"):
        raise ValueError("incompatible frozen grouped probability schema")
    by_parent = defaultdict(list)
    for row in rows:
        if set(row) != {"group_id", "action_fingerprint", "silver_order", "probability", "a_visit_share"}:
            raise ValueError("malformed frozen grouped probability row")
        by_parent[row["group_id"]].append(row)
    if set(by_parent) != set(anchor_rows):
        raise ValueError("frozen grouped probability parent surface mismatch")
    result = {}
    for group, expected in anchor_rows.items():
        actual = sorted(by_parent[group], key=lambda row: row["silver_order"])
        if [row["action_fingerprint"] for row in actual] != [row["action_fingerprint"] for row in expected]:
            raise ValueError(f"frozen grouped probability legal ordering mismatch: {group}")
        probabilities = np.asarray([row["probability"] for row in actual], dtype=np.float64)
        if (not np.all(np.isfinite(probabilities)) or np.any(probabilities < 0.0)
                or not np.isclose(probabilities.sum(), 1.0, rtol=0.0, atol=1e-12)):
            raise ValueError(f"frozen grouped probability normalization mismatch: {group}")
        result[group] = probabilities
    return result


def linear_logits(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return x @ weights


def interaction_probabilities(parents, weights, u, v) -> dict[str, np.ndarray]:
    result = {}
    split = linear.FROZEN_STATE_PREFIX_WIDTH
    for group, x, _ in parents:
        state = x[:, :split]
        action = x[:, split:]
        residual = (state @ u * (action @ v)).sum(axis=1)
        result[group] = linear.stable_softmax(linear_logits(x, weights) + residual)
    return result


def assert_zero_interaction_parity(parents, weights, reference, tolerance=1.0e-12) -> dict:
    predicted = interaction_probabilities(
        parents, weights,
        np.zeros((linear.FROZEN_STATE_PREFIX_WIDTH, RANK), dtype=np.float64),
        np.zeros((linear.FROZEN_ACTION_SUFFIX_WIDTH, RANK), dtype=np.float64))
    max_error = 0.0
    for group, value in predicted.items():
        error = float(np.max(np.abs(value - reference[group])))
        max_error = max(max_error, error)
        if error > tolerance:
            raise ValueError(f"zero-interaction grouped-linear parity failed: {group} / {error}")
    return {"parents": len(parents), "max_absolute_probability_error": max_error,
            "tolerance": tolerance, "legal_action_order_and_fingerprints": "validated by shared feature rows"}


def tensor_parents(parents):
    return [(group, torch.from_numpy(x), torch.from_numpy(target)) for group, x, target in parents]


def objective(parents, weights, u, v):
    total = torch.zeros((), dtype=torch.float64)
    split = linear.FROZEN_STATE_PREFIX_WIDTH
    for _, x, target in parents:
        logits = x @ weights + ((x[:, :split] @ u) * (x[:, split:] @ v)).sum(dim=1)
        total = total - torch.sum(target * torch.log_softmax(logits, dim=0))
    return total / len(parents) + 0.5 * L2 * (torch.sum(u * u) + torch.sum(v * v))


def fit_interaction(train, baseline_weights):
    deterministic_torch()
    data = tensor_parents(train)
    frozen = torch.from_numpy(baseline_weights.copy())
    u = torch.empty((linear.FROZEN_STATE_PREFIX_WIDTH, RANK), dtype=torch.float64)
    u.normal_(mean=0.0, std=1.0e-3)
    v = torch.zeros((linear.FROZEN_ACTION_SUFFIX_WIDTH, RANK), dtype=torch.float64)
    u.requires_grad_(True)
    v.requires_grad_(True)
    initial = float(objective(data, frozen, u, v).detach())
    optimizer = torch.optim.LBFGS([u, v], lr=1.0, max_iter=MAX_ITER,
                                  history_size=HISTORY_SIZE, line_search_fn="strong_wolfe")
    calls = 0

    def closure():
        nonlocal calls
        optimizer.zero_grad()
        loss = objective(data, frozen, u, v)
        if not torch.isfinite(loss):
            raise ValueError("non-finite interaction objective")
        loss.backward()
        calls += 1
        return loss

    optimizer.step(closure)
    final = float(objective(data, frozen, u, v).detach())
    if not math.isfinite(final) or not torch.isfinite(u).all() or not torch.isfinite(v).all():
        raise ValueError("non-finite final interaction model")
    if final > initial + 1.0e-12:
        raise ValueError(f"final penalized objective worsened: {final} > {initial}")
    state = optimizer.state[u]
    return u.detach().numpy().copy(), v.detach().numpy().copy(), {
        "method": "torch.optim.LBFGS", "device": "cpu", "dtype": "float64",
        "deterministic_algorithms": True, "max_iter": MAX_ITER, "history_size": HISTORY_SIZE,
        "line_search_fn": "strong_wolfe", "closure_calls": calls,
        "iterations": int(state.get("n_iter", 0)), "initial_penalized_objective": initial,
        "final_penalized_objective": final,
    }


def fit_twice_and_require_parity(train, weights, anchors):
    first_u, first_v, optimizer = fit_interaction(train, weights)
    second_u, second_v, _ = fit_interaction(train, weights)
    if not np.array_equal(first_u, second_u) or not np.array_equal(first_v, second_v):
        raise ValueError("deterministic rerun did not reproduce interaction arrays")
    first = interaction_probabilities(anchors, weights, first_u, first_v)
    second = interaction_probabilities(anchors, weights, second_u, second_v)
    if any(not np.array_equal(first[group], second[group]) for group in first):
        raise ValueError("deterministic rerun did not reproduce anchor predictions")
    return first_u, first_v, optimizer, {"model_arrays_byte_equal": True, "anchor_predictions_byte_equal": True}


def a_metrics(parents, scores):
    return linear.a_only_metrics(parents, scores)


def write_predictions(path, header, groups, anchor, scores):
    with path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(header, sort_keys=True) + "\n")
        for group, _, target in anchor:
            for row, value, truth in zip(groups[group], scores[group], target):
                stream.write(json.dumps({"group_id": group, "action_fingerprint": row["action_fingerprint"],
                    "silver_order": row["silver_order"], "probability": float(value),
                    "a_visit_share": float(truth)}, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("grouped_model", type=Path)
    parser.add_argument("grouped_probabilities", type=Path)
    parser.add_argument("raw_count_predictions", type=Path)
    parser.add_argument("rankshape_predictions", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {"features": require_hash(args.features, FEATURE_HASH, "features"),
              "relabels": require_hash(args.relabels, RELABEL_HASH, "relabels"),
              "corpus": require_hash(args.corpus, CORPUS_HASH, "corpus"),
              "grouped_model": require_hash(args.grouped_model, LINEAR_MODEL_HASH, "grouped model"),
              "grouped_probabilities": require_hash(args.grouped_probabilities, LINEAR_PROBABILITY_HASH, "grouped probabilities")}
    header, names, groups = linear.load_features(args.features)
    labels, anchors, coverage = linear.load_relabels(args.relabels)
    train_ids, validation_ids = linear.partition(groups, anchors)
    preflight = linear.preflight_audit(args.corpus, names, groups, train_ids, validation_ids, anchors)
    train_raw = linear.parent_arrays(groups, train_ids, labels)
    validation_raw = linear.parent_arrays(groups, validation_ids, labels)
    all_anchor = linear.parent_arrays(groups, set(anchors), labels)
    anchor_raw = [item for item in all_anchor if len(item[1]) > 1]
    if len(anchor_raw) != 63:
        raise ValueError(f"expected 63 frozen multi-action anchors, got {len(anchor_raw)}")
    model = load_linear_model(args.grouped_model, names)
    mean, scale, active = model["mean"].astype(np.float64), model["scale"].astype(np.float64), model["active"].astype(bool)
    weights = model["weights"].astype(np.float64)
    # This must equal the prior trainer's stored train-only scaler exactly.
    check_mean, check_scale, check_active = linear.train_scaler(train_raw)
    if not (np.array_equal(mean, check_mean) and np.array_equal(scale, check_scale) and np.array_equal(active, check_active)):
        raise ValueError("frozen grouped-linear scaler/active mask is not exactly train-only reconstruction")
    train = full_standardize(train_raw, mean, scale, active)
    validation = full_standardize(validation_raw, mean, scale, active)
    anchor = full_standardize(anchor_raw, mean, scale, active)
    grouped_active = linear.scaled(anchor_raw, mean, scale, active)
    reference = linear.probabilities(grouped_active, weights[active])
    exported = load_grouped_probabilities(args.grouped_probabilities, {group: groups[group] for group, _, _ in anchor_raw})
    parity = assert_zero_interaction_parity(anchor, weights, exported)
    # This second assertion isolates any mismatch between the frozen model and frozen probability artifact.
    if any(np.max(np.abs(reference[group] - exported[group])) > 1.0e-12 for group in reference):
        raise ValueError("frozen grouped model cannot reconstruct frozen anchor probabilities")
    u, v, optimizer, deterministic = fit_twice_and_require_parity(train, weights, anchor)
    scores = interaction_probabilities(anchor, weights, u, v)
    variation = [0.5 * float(np.sum(np.abs(scores[group] - exported[group]))) for group in scores]
    if max(variation) <= 1.0e-8:
        raise ValueError("interaction model is unchanged from grouped linear on every frozen root")
    b_labels = {group: linear.b_q(groups[group], labels[(group, 25000, "B")]) for group, _, _ in anchor_raw}
    raw_all = linear.load_prediction_artifact(args.raw_count_predictions, {group: groups[group] for group, _, _ in all_anchor})
    rank_all = linear.load_prediction_artifact(args.rankshape_predictions, {group: groups[group] for group, _, _ in all_anchor})
    raw_scores = {group: raw_all[group] for group, _, _ in anchor_raw}
    rank_scores = {group: rank_all[group] for group, _, _ in anchor_raw}
    per_method = {"grouped_linear": linear.evaluate(anchor_raw, b_labels, exported),
                  "rankshape_calibrated": linear.evaluate(anchor_raw, b_labels, rank_scores),
                  "interaction_rank4": linear.evaluate(anchor_raw, b_labels, scores),
                  "oracle_a_visit": linear.evaluate(anchor_raw, b_labels, {group: target for group, _, target in anchor_raw})}
    metrics = {name: linear.aggregate(value) for name, value in per_method.items()}
    model_path = args.output_dir / "rank4_interaction_policy_model.npz"
    np.savez(model_path, feature_names=np.asarray(names), baseline_weights=weights, mean=mean, scale=scale,
             active=active.astype(np.uint8), u=u, v=v, rank=np.asarray([RANK]), l2=np.asarray([L2]),
             seed=np.asarray([SEED]), state_width=np.asarray([linear.FROZEN_STATE_PREFIX_WIDTH]),
             action_width=np.asarray([linear.FROZEN_ACTION_SUFFIX_WIDTH]))
    prediction_path = args.output_dir / "rank4_interaction_anchor_probabilities.jsonl"
    write_predictions(prediction_path, {"schema": "silver_rank4_interaction_policy_predictions_v1",
        "feature_schema": header["feature_schema"], "feature_count": len(names), "parent_key": "group_id",
        "rank": RANK, "target": "normalized_25k_A_visits"}, groups, anchor_raw, scores)
    report = {"schema": "silver_rank4_interaction_policy_report_v1", "head": git_head(), "seed": SEED,
        "model": {"equation": "z_linear(s,a) + sum_k (u_k^T s)(v_k^T a)", "rank": RANK,
                  "bias": False, "temperature_or_calibration": False, "linear_model_frozen": True},
        "optimizer": optimizer, "inputs": {**hashes, "raw_count_predictions": str(args.raw_count_predictions),
                  "rankshape_predictions": str(args.rankshape_predictions)}, "dimensions": {"state": 1766, "action": 22,
                  "total": 1788, "active_features": int(active.sum())}, "split": {"train_parents": len(train),
                  "validation_parents": len(validation), "anchor_parents": len(anchors), "multi_action_anchors": len(anchor),
                  "anchors_excluded_from_fitting_and_preprocessing": True}, "preflight": preflight, "coverage": coverage,
        "zero_interaction_parity": parity, "deterministic_rerun": deterministic,
        "objective": {"parent_macro": True, "target": "exact normalized 25k-A visits", "l2": L2},
        "train_metrics": a_metrics(train, interaction_probabilities(train, weights, u, v)),
        "validation_metrics": a_metrics(validation, interaction_probabilities(validation, weights, u, v)),
        "anchor_metrics": metrics, "offline_diagnostics": {"offline_metrics_are_diagnostic_only": True,
                  "mean_total_variation_from_grouped_linear": float(np.mean(variation)),
                  "max_total_variation_from_grouped_linear": float(max(variation)),
                  "prior_argmax_differs_from_grouped_linear": int(sum(np.argmax(scores[g]) != np.argmax(exported[g]) for g in scores)),
                  "replay_status": "REPLAY_REQUIRED"},
        "artifacts": {"model": {"path": str(model_path), "sha256": sha256(model_path)},
                      "anchor_probabilities": {"path": str(prediction_path), "sha256": sha256(prediction_path)}}}
    report_path = args.output_dir / "offline_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"head": report["head"], "command": " ".join(map(str, __import__("sys").argv)),
        "seed": SEED, "rank": RANK, "optimizer": optimizer, "inputs": report["inputs"], "outputs": {
        "model": sha256(model_path), "anchor_probabilities": sha256(prediction_path), "offline_report": sha256(report_path)}},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
