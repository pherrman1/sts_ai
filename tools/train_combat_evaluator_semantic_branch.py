#!/usr/bin/env python3
"""Train and audit the frozen semantic-branch pre-combat combat evaluator.

This is deliberately a thin, offline adapter around the V1 XGBoost recipe.
It consumes the 64 validated semantic-branch sidecars directly, keeps the
existing source-seed split, and never invokes the simulator or Silver.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

# Keep parity with the existing V1 script, which imports its sibling helpers
# as top-level modules when invoked directly or through the test suite.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:
    from combat_evaluator_contract import sha256
    from combat_evaluator_semantic_branch_contract import (
        RICH_NAMES,
        SCHEMA_VERSION,
        validate_manifest,
    )
    from train_combat_evaluator import binary, calibration, reg, stable_split
except ModuleNotFoundError:
    from tools.combat_evaluator_contract import sha256
    from tools.combat_evaluator_semantic_branch_contract import (
        RICH_NAMES,
        SCHEMA_VERSION,
        validate_manifest,
    )
    from tools.train_combat_evaluator import binary, calibration, reg, stable_split


EXPECTED_PRODUCER = "a6c2abbc9db542ea1fc8933087f81c1de96c4f8a"
EXPECTED_FIRST_SEED = 992000
EXPECTED_LAST_SEED = 993023
EXPECTED_SOURCE_SEEDS = 1024
EXPECTED_SHARDS = 64
EXPECTED_ROWS = 7652
EXPECTED_VALID = 7599
EXPECTED_WINS = 7238
EXPECTED_TRUE_DEATHS = 361
EXPECTED_NONAMBIGUOUS_DEATHS = 348
EXPECTED_PACKAGE_SHA256 = "705bd2c970f52759dd7541052f56536eb5c53470aa0fe37b2674abdfd1ba7ec9"
BOOTSTRAP_SEED = 20260910
DEFAULT_BOOTSTRAP_REPLICATES = 5000
STATE_FEATURES = list(RICH_NAMES)
PROVENANCE_COLUMNS = [
    "sourceSeed", "decisionIdx", "semanticActionIdx", "semanticKey",
    "semanticSource", "futureIdentity", "branchFightIdx", "continuationSeed",
    "hiddenSeed", "teacherId",
]
LABEL_COLUMNS = [
    "won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous",
    "labelValid", "terminalCombatHp", "terminalCombatMaxHp",
    "terminalNonMinionCurHp", "terminalNonMinionMaxHp", "winHpFrac",
    "lossRemainingFrac", "signedOutcome", "quarantineReason",
]


def fail(message: str) -> None:
    raise ValueError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def audit_evidence(path: Path) -> dict[str, Any]:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    require(evidence.get("producer_sha") == EXPECTED_PRODUCER, "evidence producer mismatch")
    integrity = evidence.get("integrity", {})
    expected = {
        "capture_shards_validated": EXPECTED_SHARDS,
        "combat_shards_validated": EXPECTED_SHARDS,
        "semantic_shards_validated": EXPECTED_SHARDS,
        "source_seeds": EXPECTED_SOURCE_SEEDS,
        "combat_rows": EXPECTED_ROWS,
        "feature_count": len(STATE_FEATURES),
    }
    for key, value in expected.items():
        require(integrity.get(key) == value, f"evidence {key} mismatch")
    counts = evidence.get("combat", {}).get("counts", {})
    for key, value in {
        "total": EXPECTED_ROWS,
        "valid": EXPECTED_VALID,
        "wins": EXPECTED_WINS,
        "true_deaths": EXPECTED_TRUE_DEATHS,
        "nonambiguous_deaths": EXPECTED_NONAMBIGUOUS_DEATHS,
    }.items():
        require(counts.get(key) == value, f"evidence combat.{key} mismatch")
    package = evidence.get("preservation", {}).get("raw_package", {})
    require(package.get("sha256") == EXPECTED_PACKAGE_SHA256, "evidence raw package hash mismatch")
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "producer_sha": evidence["producer_sha"],
        "raw_package_sha256": package["sha256"],
    }


def load_corpus(
    manifest_paths: Iterable[Path],
    *,
    evidence_path: Path | None = None,
    raw_package: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    paths = sorted(Path(p).resolve() for p in manifest_paths)
    require(len(paths) == EXPECTED_SHARDS, f"expected exactly {EXPECTED_SHARDS} manifests")
    require(len(set(paths)) == EXPECTED_SHARDS, "duplicate manifest path")
    if evidence_path is not None:
        evidence_info = audit_evidence(evidence_path)
    else:
        evidence_info = None
    if raw_package is not None:
        require(raw_package.is_file(), f"raw package is not a file: {raw_package}")
        package_hash = sha256(raw_package)
        require(package_hash == EXPECTED_PACKAGE_SHA256, "raw package hash mismatch")
    else:
        package_hash = None

    cohort = set(range(EXPECTED_FIRST_SEED, EXPECTED_LAST_SEED + 1))
    seen_sources: set[int] = set()
    seen_rows: set[tuple[int, int, str, int, int]] = set()
    rows: list[dict[str, Any]] = []
    manifest_info: list[dict[str, Any]] = []
    aggregate = {"rows": 0, "valid": 0, "wins": 0, "true_deaths": 0, "nonambiguous_deaths": 0}
    producer_executables: set[str] = set()
    teacher_ids: set[str] = set()

    for manifest_path in paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validate_manifest(manifest)
        require(manifest.get("schema_version") == SCHEMA_VERSION, "semantic schema mismatch")
        require(manifest.get("producer_git_sha") == EXPECTED_PRODUCER, "manifest producer mismatch")
        source_seeds = {int(x) for x in manifest["seed_spec"]["sourceSeeds"]}
        require(len(source_seeds) == 16, f"manifest does not contain 16 source seeds: {manifest_path}")
        require(not seen_sources.intersection(source_seeds), "overlapping source-seed shards")
        require(source_seeds <= cohort, "source seed outside frozen cohort")
        seen_sources.update(source_seeds)
        producer_executables.add(manifest["producer_executable_sha256"])
        teacher_ids.add(manifest["teacher"]["teacher_id"])
        require(result["features"] == STATE_FEATURES, "state feature order mismatch")
        csv_path = Path(manifest["csv"]["path"])
        with csv_path.open(newline="", encoding="utf-8") as stream:
            shard_rows = list(csv.DictReader(stream))
        for row in shard_rows:
            key = (
                int(row["sourceSeed"]), int(row["decisionIdx"]),
                row["semanticKey"], int(row["futureIdentity"]),
                int(row["branchFightIdx"]),
            )
            require(key not in seen_rows, "duplicate global combat branch identity")
            seen_rows.add(key)
            rows.append(row)
        aggregate["rows"] += len(shard_rows)
        aggregate["valid"] += result["counts"]["valid"]
        aggregate["wins"] += result["counts"]["wins"]
        aggregate["true_deaths"] += result["counts"]["deaths"]
        aggregate["nonambiguous_deaths"] += result["counts"]["deaths"] - result["counts"]["ambiguous"]
        manifest_info.append({
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "csv": str(csv_path.resolve()),
            "csv_sha256": manifest["csv"]["sha256"],
            "source_seeds": sorted(source_seeds),
            "validation": result,
        })

    require(seen_sources == cohort, "manifest source-seed cohort mismatch")
    require(len(producer_executables) == 1 and len(teacher_ids) == 1, "mixed producer provenance")
    require(aggregate == {
        "rows": EXPECTED_ROWS,
        "valid": EXPECTED_VALID,
        "wins": EXPECTED_WINS,
        "true_deaths": EXPECTED_TRUE_DEATHS,
        "nonambiguous_deaths": EXPECTED_NONAMBIGUOUS_DEATHS,
    }, f"corpus counts mismatch: {aggregate}")

    frame = pd.DataFrame(rows)
    for column in STATE_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    for column in (
        "sourceSeed", "decisionIdx", "semanticActionIdx", "futureIdentity",
        "branchFightIdx", "continuationSeed", "hiddenSeed", "semanticSource",
        "act", "floor", "won", "trueDeath", "escaped", "turnCapLoss",
        "progressAmbiguous", "labelValid",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    for column in ("winHpFrac", "lossRemainingFrac", "signedOutcome"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame, {
        "schema_version": SCHEMA_VERSION,
        "producer_git_sha": EXPECTED_PRODUCER,
        "producer_executable_sha256": next(iter(producer_executables)),
        "teacher_id": next(iter(teacher_ids)),
        "manifests": manifest_info,
        "manifest_count": len(paths),
        "source_seeds": len(seen_sources),
        "counts": aggregate,
        "evidence": evidence_info,
        "raw_package": {"path": str(raw_package.resolve()), "sha256": package_hash}
        if raw_package is not None else None,
    }


def valid_mask(frame: pd.DataFrame) -> pd.Series:
    return frame.labelValid.eq(1) & (frame.won.eq(1) | frame.trueDeath.eq(1))


def build_features(frame: pd.DataFrame, split: pd.Series) -> tuple[list[str], dict[str, Any]]:
    valid = valid_mask(frame)
    train_valid = split.eq("train") & valid
    encounters = sorted(frame.loc[train_valid, "encounter"].astype(str).unique())
    require(encounters, "TRAIN has no represented encounters")
    encounter_columns = [f"encounter__{name}" for name in encounters]
    for name, column in zip(encounters, encounter_columns):
        frame[column] = (frame.encounter.astype(str) == name).astype(float)
    all_features = STATE_FEATURES + encounter_columns
    # Match the V1 semantics: the vocabulary and variance filter are learned
    # from TRAIN only; invalid rows are retained for the variance calculation.
    variance = frame.loc[split.eq("train"), all_features].var(ddof=0)
    features = [column for column in all_features if float(variance[column]) > 1e-12]
    require(features, "no nonconstant TRAIN features")
    unseen = {
        name: int((~frame.loc[split.eq(name), "encounter"].astype(str).isin(encounters)).sum())
        for name in ("validation", "test")
    }
    return features, {
        "state_features": STATE_FEATURES,
        "encounter_vocabulary_train": encounters,
        "encounter_features": encounter_columns,
        "model_features": features,
        "variance_filter": {"source": "TRAIN", "threshold": 1e-12},
        "unseen_encounter_rows": unseen,
        "excluded_columns": PROVENANCE_COLUMNS + LABEL_COLUMNS,
    }


def fit_models(
    frame: pd.DataFrame, split: pd.Series, features: list[str], *, rounds: int, threads: int
) -> dict[str, Any]:
    import xgboost as xgb

    valid = valid_mask(frame)
    train = split.eq("train")
    params = {
        "max_depth": 6, "eta": 0.05, "subsample": 0.8,
        "colsample_bytree": 0.8, "seed": 20260902, "nthread": threads,
        "tree_method": "hist",
    }

    def fit(mask: pd.Series, label: str, objective: str) -> Any:
        require(bool(mask.any()), f"TRAIN lacks rows for {label}")
        return xgb.train(
            {**params, "objective": objective,
             "eval_metric": "logloss" if objective == "binary:logistic" else "rmse"},
            xgb.DMatrix(frame.loc[mask, features], label=frame.loc[mask, label]),
            num_boost_round=rounds,
        )

    models = {
        "survival": fit(train & valid, "won", "binary:logistic"),
        "conditional_win_hp": fit(train & valid & frame.won.eq(1), "winHpFrac", "reg:squarederror"),
        "conditional_loss_remaining": fit(
            train & valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1),
            "lossRemainingFrac", "reg:squarederror",
        ),
    }
    dm = xgb.DMatrix(frame[features])
    predictions = {
        "p_win": np.clip(models["survival"].predict(dm), 0.0, 1.0),
        "predicted_win_hp_frac": np.clip(models["conditional_win_hp"].predict(dm), 1e-3, 1.0),
        "predicted_loss_remaining_frac": np.clip(
            models["conditional_loss_remaining"].predict(dm), 1e-3, 1.0
        ),
    }
    predictions["expected_signed_outcome"] = (
        predictions["p_win"] * predictions["predicted_win_hp_frac"]
        - (1.0 - predictions["p_win"]) * predictions["predicted_loss_remaining_frac"]
    )
    predictions["thresholded_signed_outcome"] = np.where(
        predictions["p_win"] >= 0.5,
        predictions["predicted_win_hp_frac"],
        -predictions["predicted_loss_remaining_frac"],
    )
    return {"models": models, "predictions": predictions, "parameters": params}


def evaluate_split(
    frame: pd.DataFrame,
    mask: pd.Series,
    predictions: dict[str, np.ndarray],
    baselines: dict[str, float],
) -> dict[str, Any]:
    valid = valid_mask(frame) & mask
    winner = valid & frame.won.eq(1)
    death = valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1)
    y = frame.loc[valid, "won"].to_numpy()
    p = predictions["p_win"][valid.to_numpy()]
    expected = predictions["expected_signed_outcome"][valid.to_numpy()]
    truth_signed = frame.loc[valid, "signedOutcome"].to_numpy()
    sign_truth = (truth_signed >= 0).astype(int)
    sign_pred = (expected >= 0).astype(int)
    result = {
        "rows": int(mask.sum()), "valid": int(valid.sum()),
        "source_seeds": int(frame.loc[mask, "sourceSeed"].nunique()),
        "counts": {
            "wins": int(winner.sum()), "true_deaths": int((valid & frame.trueDeath.eq(1)).sum()),
            "nonambiguous_deaths": int(death.sum()), "ambiguous": int((valid & frame.progressAmbiguous.eq(1)).sum()),
        },
        "survival": {
            "model": binary(y, p),
            "train_prior_baseline": binary(y, np.full(len(y), baselines["survival_prior"])),
            "calibration": calibration(y, p),
        },
        "winning_hp": {
            "model": reg(frame.loc[winner, "winHpFrac"], predictions["predicted_win_hp_frac"][winner.to_numpy()]),
            "train_winner_mean_baseline": reg(
                frame.loc[winner, "winHpFrac"], np.full(int(winner.sum()), baselines["win_hp_mean"])
            ),
        },
        "loss_severity": {
            "model": reg(frame.loc[death, "lossRemainingFrac"], predictions["predicted_loss_remaining_frac"][death.to_numpy()]),
            "train_death_mean_baseline": reg(
                frame.loc[death, "lossRemainingFrac"], np.full(int(death.sum()), baselines["loss_mean"])
            ),
        },
        "expected_signed_outcome": {
            "model": reg(frame.loc[valid, "signedOutcome"], expected),
            "train_signed_mean_baseline": reg(
                frame.loc[valid, "signedOutcome"], np.full(int(valid.sum()), baselines["signed_mean"])
            ),
        },
        "sign": {
            "accuracy": float((sign_pred == sign_truth).mean()) if len(sign_truth) else None,
            "confusion": [[int(((sign_truth == actual) & (sign_pred == predicted)).sum())
                           for predicted in (0, 1)] for actual in (0, 1)],
        },
    }
    return result


def source_macro(
    frame: pd.DataFrame, mask: pd.Series, predictions: dict[str, np.ndarray], baselines: dict[str, float]
) -> dict[str, Any]:
    valid = valid_mask(frame) & mask
    per_source = []
    for source, group in frame.loc[valid].groupby("sourceSeed"):
        indices = group.index.to_numpy()
        model_signed = predictions["expected_signed_outcome"][indices]
        truth = group["signedOutcome"].to_numpy()
        model_brier = (predictions["p_win"][indices] - group["won"].to_numpy()) ** 2
        per_source.append({
            "sourceSeed": int(source), "rows": len(group),
            "survival_brier_model": float(model_brier.mean()),
            "survival_brier_baseline": float(np.mean((baselines["survival_prior"] - group.won.to_numpy()) ** 2)),
            "expected_signed_abs_model": float(np.abs(model_signed - truth).mean()),
            "expected_signed_abs_baseline": float(np.abs(baselines["signed_mean"] - truth).mean()),
        })
    require(per_source, "source macro view has no valid rows")
    return {
        "source_seeds": len(per_source),
        "survival_brier_model": float(np.mean([x["survival_brier_model"] for x in per_source])),
        "survival_brier_baseline": float(np.mean([x["survival_brier_baseline"] for x in per_source])),
        "expected_signed_abs_model": float(np.mean([x["expected_signed_abs_model"] for x in per_source])),
        "expected_signed_abs_baseline": float(np.mean([x["expected_signed_abs_baseline"] for x in per_source])),
    }


def slice_reports(
    frame: pd.DataFrame, mask: pd.Series, predictions: dict[str, np.ndarray],
    baselines: dict[str, float], minimum: int
) -> list[dict[str, Any]]:
    reports = []
    valid = valid_mask(frame) & mask
    for dimension in ("act", "roomClass", "encounter"):
        for value, group in frame.loc[valid].groupby(dimension):
            if len(group) < minimum:
                continue
            group_mask = pd.Series(False, index=frame.index)
            group_mask.loc[group.index] = True
            metrics = evaluate_split(frame, group_mask, predictions, baselines)
            reports.append({
                "dimension": dimension, "value": str(value), "rows": len(group),
                "source_seeds": int(group.sourceSeed.nunique()),
                "survival": metrics["survival"]["model"],
                "winning_hp": metrics["winning_hp"]["model"],
                "loss_severity": metrics["loss_severity"]["model"],
                "expected_signed_outcome": metrics["expected_signed_outcome"]["model"],
            })
    return reports


def bootstrap_metric_difference(
    frame: pd.DataFrame,
    mask: pd.Series,
    predictions: dict[str, np.ndarray],
    baseline: float,
    metric: str,
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    valid = valid_mask(frame) & mask
    if metric == "survival_logloss":
        indices = np.flatnonzero(valid.to_numpy())
        truth = frame.loc[valid, "won"].to_numpy(dtype=float)
        model_values = -(truth * np.log(np.clip(predictions["p_win"][indices], 1e-15, 1 - 1e-15))
                         + (1 - truth) * np.log(np.clip(1 - predictions["p_win"][indices], 1e-15, 1 - 1e-15)))
        baseline_values = -(truth * math.log(np.clip(baseline, 1e-15, 1 - 1e-15))
                            + (1 - truth) * math.log(np.clip(1 - baseline, 1e-15, 1 - 1e-15)))
    elif metric == "survival_brier":
        indices = np.flatnonzero(valid.to_numpy())
        truth = frame.loc[valid, "won"].to_numpy(dtype=float)
        model_values = (predictions["p_win"][indices] - truth) ** 2
        baseline_values = (baseline - truth) ** 2
    elif metric == "win_hp_mae":
        selected = valid & frame.won.eq(1)
        indices = np.flatnonzero(selected.to_numpy())
        truth = frame.loc[selected, "winHpFrac"].to_numpy(dtype=float)
        model_values = np.abs(predictions["predicted_win_hp_frac"][indices] - truth)
        baseline_values = np.abs(baseline - truth)
    elif metric == "expected_signed_mae":
        indices = np.flatnonzero(valid.to_numpy())
        truth = frame.loc[valid, "signedOutcome"].to_numpy(dtype=float)
        model_values = np.abs(predictions["expected_signed_outcome"][indices] - truth)
        baseline_values = np.abs(baseline - truth)
    elif metric == "loss_severity_mae":
        selected = valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1)
        indices = np.flatnonzero(selected.to_numpy())
        truth = frame.loc[selected, "lossRemainingFrac"].to_numpy(dtype=float)
        model_values = np.abs(predictions["predicted_loss_remaining_frac"][indices] - truth)
        baseline_values = np.abs(baseline - truth)
    else:
        fail(f"unknown bootstrap metric: {metric}")
    require(len(indices) > 0, f"no rows for bootstrap metric: {metric}")
    sources = frame.iloc[indices].sourceSeed.to_numpy(dtype=int)
    unique_sources = np.unique(sources)
    model_sum = np.array([model_values[sources == source].sum() for source in unique_sources])
    baseline_sum = np.array([baseline_values[sources == source].sum() for source in unique_sources])
    counts = np.array([(sources == source).sum() for source in unique_sources], dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(unique_sources), size=(replicates, len(unique_sources)))
    model_drawn = model_sum[draws].sum(axis=1) / counts[draws].sum(axis=1)
    baseline_drawn = baseline_sum[draws].sum(axis=1) / counts[draws].sum(axis=1)
    deltas = model_drawn - baseline_drawn
    return {
        "metric": metric, "unit": "sourceSeed", "source_groups": int(len(unique_sources)),
        "replicates_requested": int(replicates), "effective_replicates": int(np.isfinite(deltas).sum()),
        "difference": float(model_values.mean() - baseline_values.mean()),
        "ci95": [float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))],
    }


def leave_one_source_out_loss(
    frame: pd.DataFrame, mask: pd.Series, predictions: dict[str, np.ndarray], baseline: float
) -> dict[str, Any]:
    selected = valid_mask(frame) & mask & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1)
    source_values = sorted(int(x) for x in frame.loc[selected, "sourceSeed"].unique())
    values = []
    for source in source_values:
        keep = selected & frame.sourceSeed.ne(source)
        truth = frame.loc[keep, "lossRemainingFrac"].to_numpy()
        indices = np.flatnonzero(keep.to_numpy())
        values.append({
            "removed_sourceSeed": source,
            "rows": int(keep.sum()),
            "difference": float(np.abs(predictions["predicted_loss_remaining_frac"][indices] - truth).mean() - np.abs(baseline - truth).mean()),
        })
    require(values, "loss leave-one-source-out has no death sources")
    deltas = [x["difference"] for x in values]
    return {
        "source_groups": len(values), "evaluations": values,
        "difference_range": [float(min(deltas)), float(max(deltas))],
    }


def alias_audit(frame: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    selected = frame.loc[valid_mask(frame) & mask]
    groups: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for row in selected[STATE_FEATURES + ["encounter", "signedOutcome"]].itertuples(index=False, name=None):
        groups[row[:-1]].append(float(row[-1]))
    duplicate_groups = [values for values in groups.values() if len(values) > 1]
    conflicting = [values for values in duplicate_groups if max(values) - min(values) > 1e-12]
    spreads = [max(values) - min(values) for values in conflicting]
    return {
        "rows": int(len(selected)), "unique_inputs": len(groups),
        "duplicated_input_groups": len(duplicate_groups),
        "largest_duplicate_group": max((len(x) for x in duplicate_groups), default=1),
        "duplicate_groups_with_different_signedOutcome": len(conflicting),
        "within_identical_input_signedOutcome_spread": {
            "max": float(max(spreads)) if spreads else 0.0,
            "mean": float(np.mean(spreads)) if spreads else 0.0,
        },
    }


def benchmark_latency(models: dict[str, Any], frame: pd.DataFrame, features: list[str], repeats: int) -> dict[str, Any]:
    import xgboost as xgb

    row = frame[features].iloc[[0]]
    matrices = {name: xgb.DMatrix(row) for name in models}
    for name, model in models.items():
        for _ in range(100):
            model.predict(matrices[name])
    values = {}
    for name, model in models.items():
        samples = []
        for _ in range(repeats):
            start = time.perf_counter_ns()
            model.predict(matrices[name])
            samples.append((time.perf_counter_ns() - start) / 1e6)
        values[name] = {
            "median_ms": float(np.percentile(samples, 50)),
            "p95_ms": float(np.percentile(samples, 95)),
        }
    return {"batch_size": 1, "repeats": repeats, "cpu": platform.processor(), "heads": values}


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def classify(metrics: dict[str, Any], bootstrap: dict[str, Any], loss_sources: int) -> str:
    test = metrics["test"]
    survival_better = (
        test["survival"]["model"]["logloss"] < test["survival"]["train_prior_baseline"]["logloss"]
        and test["survival"]["model"]["brier"] < test["survival"]["train_prior_baseline"]["brier"]
    )
    win_better = test["winning_hp"]["model"]["mae"] < test["winning_hp"]["train_winner_mean_baseline"]["mae"]
    loss_better = test["loss_severity"]["model"]["mae"] < test["loss_severity"]["train_death_mean_baseline"]["mae"]
    signed_better = test["expected_signed_outcome"]["model"]["mae"] < test["expected_signed_outcome"]["train_signed_mean_baseline"]["mae"]
    if survival_better and win_better and signed_better:
        if loss_better:
            return "COMBAT PREDICTOR PROMISING"
        if loss_sources < 30:
            return "COMBAT PREDICTOR PROMISING - LOSS TAIL INCONCLUSIVE"
        return "COMBAT PREDICTOR WEAK"
    if not survival_better or not signed_better:
        return "COMBAT PREDICTOR FAILED" if not survival_better else "COMBAT PREDICTOR WEAK"
    return "COMBAT PREDICTOR WEAK"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs=EXPECTED_SHARDS, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--raw-package", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=300)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--bootstrap-replicates", type=int, default=DEFAULT_BOOTSTRAP_REPLICATES)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--latency-repeats", type=int, default=2000)
    parser.add_argument("--minimum-slice", type=int, default=1)
    args = parser.parse_args()
    require(args.rounds == 300, "the frozen recipe requires exactly 300 rounds")
    require(args.threads == 1, "the frozen scientific run requires one CPU thread")
    require(args.bootstrap_replicates >= 5000, "at least 5,000 bootstrap replicates are required")

    frame, corpus = load_corpus(args.manifests, evidence_path=args.evidence, raw_package=args.raw_package)
    groups = stable_split(frame.sourceSeed)
    split = frame.sourceSeed.map(groups)
    features, feature_contract = build_features(frame, split)
    train_valid = split.eq("train") & valid_mask(frame)
    baselines = {
        "survival_prior": float(frame.loc[train_valid, "won"].mean()),
        "win_hp_mean": float(frame.loc[train_valid & frame.won.eq(1), "winHpFrac"].mean()),
        "loss_mean": float(frame.loc[train_valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1), "lossRemainingFrac"].mean()),
        "signed_mean": float(frame.loc[train_valid, "signedOutcome"].mean()),
    }
    fitted = fit_models(frame, split, features, rounds=args.rounds, threads=args.threads)
    predictions = fitted["predictions"]
    split_metrics = {}
    source_macro_metrics = {}
    for name in ("train", "validation", "test"):
        mask = split.eq(name)
        split_metrics[name] = evaluate_split(frame, mask, predictions, baselines)
        source_macro_metrics[name] = source_macro(frame, mask, predictions, baselines)

    test_mask = split.eq("test")
    bootstrap = {
        "survival_logloss": bootstrap_metric_difference(frame, test_mask, predictions, baselines["survival_prior"], "survival_logloss", replicates=args.bootstrap_replicates, seed=args.bootstrap_seed),
        "survival_brier": bootstrap_metric_difference(frame, test_mask, predictions, baselines["survival_prior"], "survival_brier", replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 1),
        "win_hp_mae": bootstrap_metric_difference(frame, test_mask, predictions, baselines["win_hp_mean"], "win_hp_mae", replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 2),
        "expected_signed_mae": bootstrap_metric_difference(frame, test_mask, predictions, baselines["signed_mean"], "expected_signed_mae", replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 3),
        "loss_severity_mae": bootstrap_metric_difference(frame, test_mask, predictions, baselines["loss_mean"], "loss_severity_mae", replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 4),
    }
    leave_one = leave_one_source_out_loss(frame, test_mask, predictions, baselines["loss_mean"])
    alias = alias_audit(frame, pd.Series(True, index=frame.index))
    slices = slice_reports(frame, test_mask, predictions, baselines, args.minimum_slice)

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    heldout = frame.copy()
    for name, values in predictions.items():
        heldout[name] = values
    heldout_path = output / "heldout_predictions.csv"
    heldout.to_csv(heldout_path, index=False)
    artifacts = {
        "heldout_predictions": {
            "path": str(heldout_path.resolve()),
            "sha256": sha256(heldout_path),
            "bytes": heldout_path.stat().st_size,
        }
    }
    model_paths = {}
    for name, model in fitted["models"].items():
        path = output / f"{name}.json"
        model.save_model(path)
        model_paths[name] = {
            "path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size,
        }
    artifacts["models"] = model_paths
    latency = benchmark_latency(fitted["models"], frame, features, args.latency_repeats)
    report = {
        "experiment": "semantic_branch_precombat_combat_evaluator_v1",
        "classification": classify(split_metrics, bootstrap, leave_one["source_groups"]),
        "analysis_git_sha": git_sha(),
        "constraints": {
            "simulator_called": False, "silver_called": False,
            "gameplay_integration": False, "new_labels": False,
        },
        "corpus": corpus,
        "split": {
            "function": "tools/train_combat_evaluator.py::stable_split(sourceSeed)",
            "source_seed_counts": {name: int(sum(value == name for value in groups.values())) for name in ("train", "validation", "test")},
            "row_counts": {name: int(split.eq(name).sum()) for name in ("train", "validation", "test")},
        },
        "feature_contract": feature_contract,
        "training": {"heads": fitted["parameters"], "rounds": args.rounds, "threads": args.threads, "baselines": baselines},
        "metrics": split_metrics,
        "source_macro_metrics": source_macro_metrics,
        "bootstrap": bootstrap,
        "loss_tail_leave_one_source_out": leave_one,
        "input_alias_noise_audit": alias,
        "slices_test": slices,
        "artifacts": artifacts,
        "models": model_paths,
        "latency": latency,
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    (output / "manifest.json").write_text(json.dumps(json_safe(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(json_safe({"output": str(output), "classification": report["classification"], "counts": corpus["counts"], "split": report["split"], "models": model_paths}), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
