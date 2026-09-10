#!/usr/bin/env python3
"""Train and evaluate the first frozen semantic OOC action scorer.

The ``train`` command consumes only the already-confirmed 1,024-decision
development corpus.  It writes XGBoost JSON models and a hash-bound feature
manifest.  The ``evaluate`` command consumes a separate, untouched holdout
and never fits, recalibrates, or extends the feature vocabulary.

This is deliberately an offline experiment tool.  The artifacts are not a
C++ compact-tree export and are not loaded by the live OOC policy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from tools import train_ooc_semantic_probe as probe
    from tools.ooc_semantic_pipeline_contract import validate_corpus
except ModuleNotFoundError:
    import train_ooc_semantic_probe as probe
    from ooc_semantic_pipeline_contract import validate_corpus


MODEL_VERSION = "semantic_ooc_xgb_v1"
SEMANTIC_ACTION_SCHEMA_VERSION = 1
STATE_SCHEMA = "rich_state_masked_hidden_v1"
TRAIN_FIRST_SEED = 992000
TRAIN_STOP_SEED = 993024
HOLDOUT_FIRST_SEED = 993024
HOLDOUT_STOP_SEED = 993152
TRAIN_SHARDS = 64
HOLDOUT_SHARDS = 8
SHARD_DECISIONS = 16
SPLIT_SEED = 20260910
BOOTSTRAP_SEED = 20260911
BOOTSTRAP_SAMPLES = 5000

MODEL_PARAMS: dict[str, Any] = {
    "n_estimators": 160,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "n_jobs": 1,
    "random_state": 20260910,
    "verbosity": 0,
}

FAMILIES = ("REWARDS", "CAMPFIRE", "SHOP", "EVENT", "TREASURE", "BOSS_RELIC", "SELECTOR")
SOURCE_TO_FAMILY = {
    0: "CAMPFIRE", 1: "CAMPFIRE", 2: "CAMPFIRE", 3: "SHOP", 4: "SHOP",
    5: "EVENT", 6: "SELECTOR", 7: "REWARDS", 8: "TREASURE", 9: "BOSS_RELIC",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(value), allow_nan=False, indent=2, sort_keys=True) + "\n")


def load_rows(manifest_paths: Iterable[Path], expected_shards: int,
              expected_first_seed: int, expected_stop_seed: int,
              expected_rows: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = sorted(Path(path) for path in manifest_paths)
    require(len(paths) == expected_shards, f"expected exactly {expected_shards} semantic manifests")
    rows: list[dict[str, Any]] = []
    groups: set[tuple[int, int]] = set()
    seeds: set[int] = set()
    shard_info = []
    provenance: dict[str, Any] | None = None
    for path in paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validation = validate_corpus(manifest)
        require(validation["decisions"] == SHARD_DECISIONS and validation["quarantined"] == 0,
                f"invalid or incomplete semantic shard {path}: {validation}")
        identity = {
            key: manifest[key]
            for key in ("producer_git_sha", "producer_executable_sha256", "combat_teacher",
                        "stateFeatures", "evaluation", "runtime")
        }
        if provenance is None:
            provenance = identity
        require(identity == provenance, f"mixed frozen provenance in {path}")
        shard_seeds = set(manifest["sampling"]["sourceSeeds"])
        require(len(shard_seeds) == SHARD_DECISIONS and not shard_seeds & seeds,
                f"duplicate or incomplete source-seed shard {path}")
        seeds.update(shard_seeds)
        csv_path = Path(manifest["csv"]["path"])
        with csv_path.open(newline="", encoding="utf-8") as stream:
            shard_rows = list(csv.DictReader(stream))
        require(len(shard_rows) == validation["rows"], f"CSV row count mismatch in {path}")
        shard_groups: set[tuple[int, int]] = set()
        for row in shard_rows:
            group = (int(row["sourceSeed"]), int(row["decisionIdx"]))
            row["_group"] = group
            row["_manifest"] = str(path)
            rows.append(row)
            shard_groups.add(group)
        require(len(shard_groups) == SHARD_DECISIONS,
                f"expected {SHARD_DECISIONS} decisions in {path}, found {len(shard_groups)}")
        require({group[0] for group in shard_groups} == shard_seeds and
                len({group[0] for group in shard_groups}) == SHARD_DECISIONS,
                f"expected exactly one decision per source seed in {path}")
        require(not shard_groups & groups, f"duplicate decision group across shards: {path}")
        groups.update(shard_groups)
        shard_info.append({
            "manifest": str(path),
            "manifest_sha256": sha256(path),
            "csv": str(csv_path),
            "csv_sha256": sha256(csv_path),
            "validation": validation,
            "source_seeds": sorted(shard_seeds),
        })
    require(seeds == set(range(expected_first_seed, expected_stop_seed)),
            "semantic source-seed cohort is not the exact requested range")
    require(len(groups) == expected_shards * SHARD_DECISIONS,
            "expected one complete decision per source seed")
    if expected_rows is not None:
        require(len(rows) == expected_rows, f"expected {expected_rows} rows, found {len(rows)}")
    require(provenance is not None, "missing corpus provenance")
    return rows, {
        "manifest_count": len(paths),
        "decisions": len(groups),
        "rows": len(rows),
        "source_seed_range": [expected_first_seed, expected_stop_seed - 1],
        "shards": shard_info,
        "provenance": provenance,
    }


def state_matrix(rows: list[dict[str, Any]], state_names: list[str]) -> np.ndarray:
    values = np.asarray([[float(value) for value in row["richRow"].split(",")] for row in rows], dtype=np.float32)
    require(values.shape == (len(rows), len(state_names)),
            f"richRow has shape {values.shape}, expected {(len(rows), len(state_names))}")
    require(np.isfinite(values).all(), "state features contain nonfinite values")
    by_group: dict[tuple[int, int], int] = {}
    for index, row in enumerate(rows):
        previous = by_group.setdefault(row["_group"], index)
        require(np.array_equal(values[index], values[previous]),
                f"state features differ within decision {row['_group']}")
    return values


def grouped_delta(rows: list[dict[str, Any]]) -> np.ndarray:
    target = np.asarray([float(row["qProduct"]) for row in rows], dtype=np.float64)
    require(np.isfinite(target).all(), "qProduct contains nonfinite values")
    delta = np.empty_like(target)
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["_group"]].append(index)
    for indices in groups.values():
        require(len(indices) >= 2, "decision group must contain at least two siblings")
        delta[indices] = target[indices] - np.mean(target[indices])
    return delta


def family(rows: list[dict[str, Any]], indices: list[int]) -> str:
    names = {SOURCE_TO_FAMILY[int(rows[index]["semanticSource"])] for index in indices}
    require(len(names) == 1, f"mixed semantic family in decision {rows[indices[0]]['_group']}")
    return next(iter(names))


def compound(rows: list[dict[str, Any]], indices: list[int]) -> bool:
    return any(len(json.loads(rows[index]["executedPrimitiveBits"])) > 1 for index in indices)


def vectorize_frozen(dicts: list[dict[str, float]], keys: list[str]) -> np.ndarray:
    """Apply a training vocabulary, dropping (and separately reporting) unknown keys."""
    index = {key: position for position, key in enumerate(keys)}
    out = np.zeros((len(dicts), len(keys)), dtype=np.float32)
    for row_index, item in enumerate(dicts):
        for key, value in item.items():
            position = index.get(key)
            if position is not None:
                out[row_index, position] = value
    return out


def matrices(rows: list[dict[str, Any]], state_names: list[str],
             semantic_keys: list[str], primitive_keys: list[str]) -> dict[str, np.ndarray]:
    state = state_matrix(rows, state_names)
    semantic_dicts = [probe.semantic_features(row) for row in rows]
    primitive_dicts = [probe.primitive_features(row) for row in rows]
    semantic = vectorize_frozen(semantic_dicts, semantic_keys)
    primitive = vectorize_frozen(primitive_dicts, primitive_keys)
    return {
        "SEMANTIC": np.concatenate([state, semantic], axis=1),
        "PRIMITIVE": np.concatenate([state, primitive], axis=1),
        "ACTION_AGNOSTIC": state,
    }


def feature_keys(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    semantic = [probe.semantic_features(row) for row in rows]
    primitive = [probe.primitive_features(row) for row in rows]
    _, semantic_keys = probe.vectorize(semantic)
    _, primitive_keys = probe.vectorize(primitive)
    return semantic_keys, primitive_keys


def unseen_feature_counts(rows: list[dict[str, Any]], allowed: set[str]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for row in rows:
        for key in probe.semantic_features(row):
            if key not in allowed:
                counts[key] += 1
    categorical = {key: value for key, value in sorted(counts.items()) if key.startswith("cat:")}
    numeric = {key: value for key, value in sorted(counts.items()) if not key.startswith("cat:")}
    return {
        "total_feature_mentions": int(sum(counts.values())),
        "distinct_features": len(counts),
        "categorical": categorical,
        "categorical_distinct": len(categorical),
        "numeric": numeric,
    }


def train_model(x: np.ndarray, y: np.ndarray):
    import xgboost as xgb
    model = xgb.XGBRegressor(**MODEL_PARAMS)
    model.fit(x, y, verbose=False)
    return model


def train_metrics(rows: list[dict[str, Any]], delta: np.ndarray,
                  prediction: np.ndarray) -> dict[str, Any]:
    ranking = probe.decision_metrics(rows, prediction)
    error = prediction - delta
    return {
        "deltaQ_rmse": float(np.sqrt(np.mean(error * error))),
        "deltaQ_mae": float(np.mean(np.abs(error))),
        "macro_pairwise": ranking["macro"]["pairwise_concordance"],
        "mean_selected_regret": ranking["macro"]["mean_regret"],
        "top_or_tied": ranking["macro"]["top_or_tied"],
        "median_selected_regret": ranking["macro"]["median_regret"],
    }


def fit_artifacts(rows: list[dict[str, Any]], corpus: dict[str, Any], output: Path) -> dict[str, Any]:
    manifest = json.loads(Path(corpus["shards"][0]["manifest"]).read_text(encoding="utf-8"))
    state_names = manifest["stateFeatures"]["header"].split(",")
    require(manifest["stateFeatures"]["schema"] == STATE_SCHEMA, "unexpected state feature schema")
    semantic_keys, primitive_keys = feature_keys(rows)
    x = matrices(rows, state_names, semantic_keys, primitive_keys)
    delta = grouped_delta(rows)
    models = {}
    metrics = {}
    for name in ("SEMANTIC", "PRIMITIVE"):
        model = train_model(x[name], delta)
        artifact = output / ("semantic_model.json" if name == "SEMANTIC" else "primitive_control.json")
        model.save_model(str(artifact))
        models[name] = {"path": artifact.name, "sha256": sha256(artifact)}
        metrics[name] = train_metrics(rows, delta, model.predict(x[name]))

    encoder_path = Path(probe.__file__).resolve()
    feature_manifest = {
        "schema_version": "semantic_ooc_feature_manifest_v1",
        "model_family": MODEL_VERSION,
        "state_features": {
            "version": STATE_SCHEMA,
            "header": state_names,
            "header_sha256": text_sha256(",".join(state_names)),
            "feature_count": len(state_names),
        },
        "semantic_action_schema_version": SEMANTIC_ACTION_SCHEMA_VERSION,
        "semantic_encoder": {"source": str(encoder_path), "sha256": sha256(encoder_path)},
        "semantic_action_feature_names": semantic_keys,
        "primitive_action_feature_names": primitive_keys,
        "feature_count": {
            "semantic": int(x["SEMANTIC"].shape[1]),
            "primitive": int(x["PRIMITIVE"].shape[1]),
            "action_agnostic": int(x["ACTION_AGNOSTIC"].shape[1]),
        },
        "ordered_feature_names": {
            "semantic": state_names + [f"action:{key}" for key in semantic_keys],
            "primitive": state_names + [f"action:{key}" for key in primitive_keys],
            "action_agnostic": state_names,
        },
        "training": {
            "source_seed_range": [TRAIN_FIRST_SEED, TRAIN_STOP_SEED - 1],
            "decision_count": corpus["decisions"],
            "row_count": corpus["rows"],
            "target": "deltaQ",
            "raw_target": "qProduct",
            "group_key": ["sourceSeed", "decisionIdx"],
            "row_weighting": "uniform",
        },
    }
    feature_path = output / "feature_manifest.json"
    write_json(feature_path, feature_manifest)
    report = {
        "schema_version": "semantic_ooc_training_report_v1",
        "experiment": "semantic_ooc_action_model_v1",
        "model_family": MODEL_VERSION,
        "git_baseline": git_sha(),
        "training_script_sha256": sha256(Path(__file__).resolve()),
        "training_corpus": corpus,
        "training": {
            "decision_count": corpus["decisions"],
            "row_count": corpus["rows"],
            "source_seed_range": [TRAIN_FIRST_SEED, TRAIN_STOP_SEED - 1],
            "target": "deltaQ = qProduct - mean(qProduct within decision)",
            "feature_manifest": feature_path.name,
            "feature_manifest_sha256": sha256(feature_path),
            "hyperparameters": MODEL_PARAMS,
            "metrics": metrics,
        },
        "models": models,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "constraints": {
            "holdout_used": False,
            "simulator_called": False,
            "runtime_policy_modified": False,
            "production_exported": False,
        },
    }
    try:
        import xgboost
        report["software"]["xgboost"] = xgboost.__version__
    except ImportError:
        pass
    write_json(output / "training_report.json", report)
    return report


def load_frozen_model(path: Path, expected_sha: str):
    require(path.is_file() and sha256(path) == expected_sha, f"frozen model hash mismatch: {path}")
    import xgboost as xgb
    model = xgb.XGBRegressor()
    model.load_model(str(path))
    return model


def ranking_with_slices(rows: list[dict[str, Any]], predictions: dict[str, np.ndarray]) -> dict[str, Any]:
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["_group"]].append(index)
    slices: dict[str, list[int]] = {family_name: [] for family_name in FAMILIES}
    slices.update({"compound_containing": [], "non_compound": []})
    for indices in groups.values():
        slices[family(rows, indices)].extend(indices)
        slices["compound_containing" if compound(rows, indices) else "non_compound"].extend(indices)
    result = {}
    for name, prediction in predictions.items():
        result[name] = {"overall": probe.decision_metrics(rows, prediction)}
        for slice_name, indices in slices.items():
            if indices:
                result[name][slice_name] = probe.decision_metrics(
                    [rows[index] for index in indices], prediction[indices]
                )
    return result


def paired_bootstrap(semantic: list[dict[str, Any]], primitive: list[dict[str, Any]],
                     null: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "mean_selected_regret": "regret",
        "macro_pairwise": "pairwise_concordance",
        "top_or_tied": "top_or_tied",
    }
    result = {}
    for offset, (name, field) in enumerate(fields.items()):
        result[name] = probe.bootstrap_difference(
            semantic, primitive, field, BOOTSTRAP_SEED + offset, BOOTSTRAP_SAMPLES
        )
    result["semantic_minus_action_agnostic_pairwise"] = probe.bootstrap_difference(
        semantic, null, "pairwise_concordance", BOOTSTRAP_SEED + 10, BOOTSTRAP_SAMPLES
    )
    return result


def manual_examples(rows: list[dict[str, Any]], predictions: dict[str, np.ndarray], limit: int = 8) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["_group"]].append(index)
    by_family: dict[str, list[tuple[int, int]]] = defaultdict(list)
    compounds: list[tuple[int, int]] = []
    for group, indices in sorted(groups.items()):
        by_family[family(rows, indices)].append(group)
        if compound(rows, indices):
            compounds.append(group)
    selected: list[tuple[int, int]] = []
    # Fixed family order makes this a coverage sample, not a performance sample.
    if compounds:
        selected.append(compounds[0])
    for family_name in FAMILIES:
        if by_family[family_name]:
            candidate = by_family[family_name][0]
            if candidate not in selected:
                selected.append(candidate)
        if len(selected) >= limit:
            break
    selected.extend(group for group in sorted(groups) if group not in selected)
    selected = selected[:limit]
    examples = []
    for group in selected:
        indices = groups[group]
        truth = np.asarray([float(rows[index]["qProduct"]) for index in indices])
        semantic_order = sorted(indices, key=lambda index: (-predictions["SEMANTIC"][index], index))
        primitive_order = sorted(indices, key=lambda index: (-predictions["PRIMITIVE"][index], index))
        best = float(np.max(truth))
        best_indices = [indices[index] for index in np.flatnonzero(np.isclose(truth, best, rtol=0, atol=1e-12))]
        sem_rank = {index: rank for rank, index in enumerate(semantic_order, 1)}
        prim_rank = {index: rank for rank, index in enumerate(primitive_order, 1)}
        actions = []
        for index in sorted(indices, key=lambda item: (-float(rows[item]["qProduct"]), item)):
            payload = json.loads(rows[index]["semanticPayload"])
            actions.append({
                "semanticActionIdx": int(rows[index]["semanticActionIdx"]),
                "effect": probe.EFFECT_NAMES[int(rows[index]["semanticEffect"])],
                "source": probe.SOURCE_NAMES[int(rows[index]["semanticSource"])],
                "payload_type": payload["type"],
                "true_q": float(rows[index]["qProduct"]),
                "true_deltaQ": float(rows[index]["qProduct"]) - float(np.mean(truth)),
                "semantic_predicted_deltaQ": float(predictions["SEMANTIC"][index]),
                "primitive_predicted_deltaQ": float(predictions["PRIMITIVE"][index]),
                "semantic_rank": sem_rank[index],
                "primitive_rank": prim_rank[index],
            })
        examples.append({
            "group": list(group),
            "family": family(rows, indices),
            "compound": compound(rows, indices),
            "siblings": len(indices),
            "semantic_selected_action": int(rows[semantic_order[0]]["semanticActionIdx"]),
            "primitive_selected_action": int(rows[primitive_order[0]]["semanticActionIdx"]),
            "true_best_actions": [int(rows[index]["semanticActionIdx"]) for index in best_indices],
            "semantic_regret": best - float(rows[semantic_order[0]]["qProduct"]),
            "primitive_regret": best - float(rows[primitive_order[0]]["qProduct"]),
            "actions": actions,
        })
    return examples


def evaluate_artifacts(rows: list[dict[str, Any]], corpus: dict[str, Any], model_dir: Path) -> dict[str, Any]:
    report = json.loads((model_dir / "training_report.json").read_text(encoding="utf-8"))
    features = json.loads((model_dir / report["training"]["feature_manifest"]).read_text(encoding="utf-8"))
    require(report["model_family"] == MODEL_VERSION and features["model_family"] == MODEL_VERSION,
            "wrong frozen model family")
    require(report["training"]["decision_count"] == 1024 and report["training"]["row_count"] == 7652,
            "training artifact is not the required 1,024-decision corpus")
    feature_path = model_dir / report["training"]["feature_manifest"]
    require(sha256(feature_path) == report["training"]["feature_manifest_sha256"], "feature manifest changed after freeze")
    state_names = features["state_features"]["header"]
    semantic_keys = features["semantic_action_feature_names"]
    primitive_keys = features["primitive_action_feature_names"]
    x = matrices(rows, state_names, semantic_keys, primitive_keys)
    require(x["SEMANTIC"].shape[1] == features["feature_count"]["semantic"], "semantic feature shape changed")
    require(x["PRIMITIVE"].shape[1] == features["feature_count"]["primitive"], "primitive feature shape changed")
    semantic_model = load_frozen_model(model_dir / report["models"]["SEMANTIC"]["path"], report["models"]["SEMANTIC"]["sha256"])
    primitive_model = load_frozen_model(model_dir / report["models"]["PRIMITIVE"]["path"], report["models"]["PRIMITIVE"]["sha256"])
    predictions = {
        "SEMANTIC": semantic_model.predict(x["SEMANTIC"]),
        "PRIMITIVE": primitive_model.predict(x["PRIMITIVE"]),
        # A state-only model cannot distinguish siblings.  Zero is the exact
        # mean-centered null prediction, with row order resolving argmax ties.
        "ACTION_AGNOSTIC": np.zeros(len(rows), dtype=np.float32),
    }
    require(all(np.isfinite(value).all() for value in predictions.values()), "nonfinite frozen prediction")
    delta = grouped_delta(rows)
    rankings = ranking_with_slices(rows, predictions)
    arms = {}
    for name, prediction in predictions.items():
        arms[name] = {
            **rankings[name]["overall"],
            "regression": {
                "deltaQ_rmse": float(np.sqrt(np.mean((prediction - delta) ** 2))),
                "deltaQ_mae": float(np.mean(np.abs(prediction - delta))),
            },
        }
    sem_groups = arms["SEMANTIC"]["per_group"]
    prim_groups = arms["PRIMITIVE"]["per_group"]
    null_groups = arms["ACTION_AGNOSTIC"]["per_group"]
    family_reports = {}
    for family_name in FAMILIES:
        family_reports[family_name] = {}
        for arm_name in predictions:
            slice_value = rankings[arm_name].get(family_name)
            if slice_value is not None:
                family_reports[family_name][arm_name] = slice_value["macro"]
    compound_reports = {}
    for slice_name in ("compound_containing", "non_compound"):
        compound_reports[slice_name] = {
            arm_name: rankings[arm_name][slice_name]["macro"]
            for arm_name in predictions if slice_name in rankings[arm_name]
        }
    null_pairwise = [{**item, "pairwise_concordance": 0.5} for item in sem_groups]
    bootstrap = paired_bootstrap(sem_groups, prim_groups, null_pairwise)
    unseen = unseen_feature_counts(rows, set(semantic_keys))
    pairwise = arms["SEMANTIC"]["macro"]["pairwise_concordance"]
    semantic_null = bootstrap["semantic_minus_action_agnostic_pairwise"]
    classification = "SEMANTIC MODEL V1 PASS"
    if not (pairwise is not None and pairwise > 0.5 and
            arms["SEMANTIC"]["macro"]["mean_regret"] <= arms["PRIMITIVE"]["macro"]["mean_regret"] and
            pairwise > arms["PRIMITIVE"]["macro"]["pairwise_concordance"] and
            semantic_null["ci95"][0] > 0):
        classification = "SEMANTIC MODEL VIABLE BUT HOLDOUT NOISY"
    return json_safe({
        "schema_version": "semantic_ooc_evaluation_report_v1",
        "experiment": "semantic_ooc_action_model_v1",
        "model_family": MODEL_VERSION,
        "model_dir": str(model_dir),
        "holdout_corpus": corpus,
        "holdout": {
            "source_seed_range": [HOLDOUT_FIRST_SEED, HOLDOUT_STOP_SEED - 1],
            "decision_count": corpus["decisions"],
            "row_count": corpus["rows"],
            "target": "deltaQ = qProduct - mean(qProduct within decision)",
            "family_distribution": {
                family_name: sum(1 for item in rankings["SEMANTIC"].get(family_name, {}).get("per_group", []))
                for family_name in FAMILIES
            },
        },
        "frozen_model": {
            "training_report_sha256": sha256(model_dir / "training_report.json"),
            "feature_manifest_sha256": sha256(feature_path),
            "hyperparameters": MODEL_PARAMS,
            "feature_count": features["feature_count"],
        },
        "arms": arms,
        "semantic_minus_primitive_bootstrap": bootstrap,
        "family_diagnostics": family_reports,
        "compound_diagnostics": compound_reports,
        "unseen_semantic_features": unseen,
        "manual_examples": manual_examples(rows, predictions),
        "classification": classification,
        "classification_basis": "Frozen point-estimate rule plus semantic-minus-null pairwise bootstrap; family slices are descriptive and require manual catastrophic-failure review.",
        "constraints": {
            "holdout_fit": False,
            "feature_vocabulary_extended": False,
            "hyperparameters_changed": False,
            "calibration": False,
            "runtime_policy_modified": False,
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    })


def train_command(args: argparse.Namespace) -> None:
    manifests = [Path(value) for value in args.manifests]
    rows, corpus = load_rows(manifests, TRAIN_SHARDS, TRAIN_FIRST_SEED, TRAIN_STOP_SEED, 7652)
    report = fit_artifacts(rows, corpus, args.output)
    print(json.dumps({"output": str(args.output), "decisions": len({row['_group'] for row in rows}),
                      "rows": len(rows), "training_script_sha256": report["training_script_sha256"]}, sort_keys=True))


def evaluate_command(args: argparse.Namespace) -> None:
    manifests = [Path(value) for value in args.manifests]
    rows, corpus = load_rows(manifests, HOLDOUT_SHARDS, HOLDOUT_FIRST_SEED, HOLDOUT_STOP_SEED)
    result = evaluate_artifacts(rows, corpus, args.model_dir)
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "classification": result["classification"],
                      "decisions": result["holdout"]["decision_count"], "rows": result["holdout"]["row_count"]}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("manifests", nargs="+", help="64 validated semantic CSV manifests")
    train.set_defaults(function=train_command)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--model-dir", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("manifests", nargs="+", help="8 validated semantic holdout manifests")
    evaluate.set_defaults(function=evaluate_command)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
