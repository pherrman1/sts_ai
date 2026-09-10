#!/usr/bin/env python3
"""Offline decision-level gate analysis for the frozen combat evaluator.

This tool consumes the already validated semantic-branch corpus and the
already produced held-out combat-evaluator predictions.  It never trains,
invokes the simulator, or mixes predictor scores with Silver qProduct values.
All decisions are kept intact: a gate either accepts the predictor ranking for
the complete sibling set or falls back to the complete Silver ranking.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from combat_evaluator_semantic_branch_contract import validate_manifest
from train_combat_evaluator_semantic_branch import load_corpus
from train_ooc_semantic_probe import FAMILY_NAMES, SOURCE_NAMES


MARGINS = (0.0, 0.01, 0.02, 0.05, 0.10)
SURVIVAL_THRESHOLDS = (0.0, 0.50, 0.75, 0.90, 0.95, 0.98, 0.99)
BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_SEED = 20260910
EPSILON = 1e-12
IDENTITY = ("sourceSeed", "decisionIdx", "semanticKey", "futureIdentity", "branchFightIdx")
REQUIRED_PREDICTIONS = (
    "p_win", "predicted_win_hp_frac", "predicted_loss_remaining_frac",
    "expected_signed_outcome",
)


def fail(message: str) -> None:
    raise ValueError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc
    require(math.isfinite(result), f"non-finite {name}")
    return result


def integer(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer {name}: {value!r}") from exc
    require(str(value) == str(result) or isinstance(value, (int, np.integer)),
            f"non-integral {name}: {value!r}")
    return result


def branch_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        integer(row["sourceSeed"], "sourceSeed"),
        integer(row["decisionIdx"], "decisionIdx"),
        str(row["semanticKey"]),
        integer(row["futureIdentity"], "futureIdentity"),
        integer(row.get("branchFightIdx", 0), "branchFightIdx"),
    )


def display_key(key: tuple[Any, ...]) -> str:
    return "/".join(map(str, key))


def read_csv_rows(path: Path, required: Iterable[str]) -> list[dict[str, str]]:
    require(path.is_file(), f"CSV is not a file: {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        missing = sorted(set(required) - set(header))
        require(not missing, f"{path} missing columns: {missing}")
        return list(reader)


def collect_semantic_rows(manifest_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the semantic sibling rows bound by the combat manifests."""
    semantic_paths: dict[Path, dict[str, Any]] = {}
    manifests = []
    for path in sorted(Path(p).resolve() for p in manifest_paths):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validation = validate_manifest(manifest)
        semantic_path = Path(manifest["semantic_manifest"]["path"]).resolve()
        require(semantic_path.is_file(), f"semantic manifest is not a file: {semantic_path}")
        require(sha256(semantic_path) == manifest["semantic_manifest"]["sha256"],
                f"semantic manifest hash mismatch: {semantic_path}")
        semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
        csv_path = Path(semantic["csv"]["path"]).resolve()
        require(csv_path.is_file() and sha256(csv_path) == semantic["csv"]["sha256"],
                f"semantic CSV hash mismatch: {csv_path}")
        semantic_paths[semantic_path] = semantic
        manifests.append({
            "path": str(path), "sha256": sha256(path), "validation": validation,
            "semantic_manifest": str(semantic_path),
            "semantic_manifest_sha256": sha256(semantic_path),
        })

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    required = ("sourceSeed", "decisionIdx", "semanticKey", "futureIdentity",
                "semanticActionIdx", "qProduct", "silverSimulations")
    for semantic_path, semantic in sorted(semantic_paths.items(), key=lambda item: str(item[0])):
        csv_path = Path(semantic["csv"]["path"]).resolve()
        for raw in read_csv_rows(csv_path, required):
            row = dict(raw)
            row["branchFightIdx"] = "0"
            key = branch_key(row)
            require(key not in seen, f"duplicate semantic branch identity: {display_key(key)}")
            seen.add(key)
            row["semanticActionIdx"] = integer(row["semanticActionIdx"], "semanticActionIdx")
            row["qProduct"] = finite(row["qProduct"], "qProduct")
            row["silverSimulations"] = integer(row["silverSimulations"], "silverSimulations")
            require(row["silverSimulations"] >= 0, "negative silverSimulations")
            rows.append(row)
    require(rows, "semantic corpus is empty")
    return rows, manifests


def _validate_prediction_manifest(path: Path, prediction_path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifact = manifest.get("artifacts", {}).get("heldout_predictions", {})
    if not artifact:
        artifact = manifest.get("heldout_predictions", {})
    require(Path(artifact.get("path", "")).resolve() == prediction_path.resolve(),
            "predictor manifest does not bind the supplied heldout predictions")
    require(artifact.get("sha256") == sha256(prediction_path),
            "heldout prediction hash does not match predictor manifest")
    models = manifest.get("models", {}) or manifest.get("artifacts", {}).get("models", {})
    model_hashes = {}
    for name, info in models.items():
        if isinstance(info, dict) and info.get("path") and info.get("sha256"):
            model_path = Path(info["path"]).resolve()
            require(model_path.is_file() and sha256(model_path) == info["sha256"],
                    f"predictor model hash mismatch: {name}")
            model_hashes[name] = {"path": str(model_path), "sha256": info["sha256"],
                                  "bytes": model_path.stat().st_size}
    return {
        "path": str(path.resolve()), "sha256": sha256(path),
        "heldout_predictions": {"path": str(prediction_path.resolve()),
                                 "sha256": sha256(prediction_path),
                                 "bytes": prediction_path.stat().st_size},
        "models": model_hashes,
        "analysis_sha": manifest.get("analysis_git_sha"),
    }


def join_inputs(
    semantic_rows: list[dict[str, Any]], combat: pd.DataFrame, predictions_path: Path,
    predictor_manifest: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join semantic truth, combat metadata, and predictions fail-closed."""
    pred_rows = read_csv_rows(predictions_path, [*IDENTITY, *REQUIRED_PREDICTIONS])
    require(pred_rows, "heldout predictions are empty")
    combat_rows = combat.to_dict("records")

    def keyed(rows: Iterable[dict[str, Any]], label: str) -> dict[tuple[Any, ...], dict[str, Any]]:
        result = {}
        for row in rows:
            key = branch_key(row)
            require(key not in result, f"duplicate {label} branch identity: {display_key(key)}")
            result[key] = row
        return result

    semantic_by_key = keyed(semantic_rows, "semantic")
    combat_by_key = keyed(combat_rows, "combat")
    pred_by_key = keyed(pred_rows, "prediction")
    require(set(semantic_by_key) == set(combat_by_key), "semantic/combat branch identity mismatch")
    require(set(semantic_by_key) == set(pred_by_key), "semantic/prediction branch identity mismatch")

    joined: list[dict[str, Any]] = []
    for key in sorted(semantic_by_key):
        semantic = semantic_by_key[key]
        combat_row = combat_by_key[key]
        prediction = pred_by_key[key]
        for name in ("semanticActionIdx", "act", "floor", "encounter"):
            if name in combat_row and name in semantic:
                require(str(combat_row[name]) == str(semantic[name]),
                        f"semantic/combat {name} mismatch for {display_key(key)}")
        row = {**semantic, **{f"combat_{name}": value for name, value in combat_row.items()},
               **{name: prediction[name] for name in REQUIRED_PREDICTIONS}}
        row["sourceSeed"], row["decisionIdx"] = key[0], key[1]
        row["semanticKey"], row["futureIdentity"], row["branchFightIdx"] = key[2:]
        for name in REQUIRED_PREDICTIONS:
            row[name] = finite(row[name], name)
        require(0.0 <= row["p_win"] <= 1.0, f"p_win outside [0,1] for {display_key(key)}")
        require(row["predicted_win_hp_frac"] >= 0.0 and row["predicted_loss_remaining_frac"] >= 0.0,
                f"negative predicted fraction for {display_key(key)}")
        expected = row["p_win"] * row["predicted_win_hp_frac"] - (1.0 - row["p_win"]) * row["predicted_loss_remaining_frac"]
        require(abs(expected - row["expected_signed_outcome"]) <= 1e-8,
                f"expected outcome formula mismatch for {display_key(key)}")
        row["silverSimulations"] = integer(row["silverSimulations"], "silverSimulations")
        joined.append(row)

    frame = pd.DataFrame(joined)
    frame["family"] = [
        FAMILY_NAMES.get(SOURCE_NAMES.get(integer(x, "semanticSource"), "OTHER"), "OTHER")
        for x in frame["semanticSource"]
    ]
    for name in ("sourceSeed", "decisionIdx", "futureIdentity", "branchFightIdx", "silverSimulations"):
        frame[name] = pd.to_numeric(frame[name], errors="raise").astype(int)
    for name in ("qProduct", *REQUIRED_PREDICTIONS):
        frame[name] = pd.to_numeric(frame[name], errors="raise")
    for name in ("act", "floor", "encounter", "roomClass"):
        if name not in frame:
            name = f"combat_{name}"
        require(name in frame, f"joined data lacks {name}")
    frame["act"] = pd.to_numeric(frame["act"], errors="raise").astype(int)
    frame["floor"] = pd.to_numeric(frame["floor"], errors="raise").astype(int)
    frame["actual_won"] = pd.to_numeric(frame.get("combat_won", np.nan), errors="coerce")
    frame["actual_true_death"] = pd.to_numeric(frame.get("combat_trueDeath", np.nan), errors="coerce")
    frame["actual_label_valid"] = pd.to_numeric(frame.get("combat_labelValid", np.nan), errors="coerce")
    metadata = {
        "semantic_rows": len(semantic_rows), "combat_rows": len(combat_rows),
        "prediction_rows": len(pred_rows), "decisions": int(frame.groupby(["sourceSeed", "decisionIdx"]).ngroups),
        "source_seeds": int(frame.sourceSeed.nunique()),
        "predictor_manifest": _validate_prediction_manifest(predictor_manifest, predictions_path)
        if predictor_manifest else None,
    }
    require(all(len(group) >= 2 for _, group in frame.groupby(["sourceSeed", "decisionIdx"])),
            "every semantic decision must retain at least two siblings")
    return frame, metadata


def group_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    groups = []
    for (source, decision), group in frame.groupby(["sourceSeed", "decisionIdx"], sort=True):
        group = group.sort_values(["semanticKey", "futureIdentity", "branchFightIdx"], kind="stable")
        rows = group.to_dict("records")
        scores = np.asarray([float(row["expected_signed_outcome"]) for row in rows])
        q_values = np.asarray([float(row["qProduct"]) for row in rows])
        p_values = np.asarray([float(row["p_win"]) for row in rows])
        model_order = sorted(range(len(rows)), key=lambda i: (-scores[i], str(rows[i]["semanticKey"])))
        silver_order = sorted(range(len(rows)), key=lambda i: (-q_values[i], str(rows[i]["semanticKey"])))
        model_index, silver_index = model_order[0], silver_order[0]
        model_top = {i for i, value in enumerate(q_values) if abs(value - q_values[silver_index]) <= EPSILON}
        actual = [int(row["actual_won"]) if not pd.isna(row["actual_won"]) else None for row in rows]
        labels_valid = [int(row["actual_label_valid"]) if not pd.isna(row["actual_label_valid"]) else None for row in rows]
        groups.append({
            "sourceSeed": int(source), "decisionIdx": int(decision), "rows": rows,
            "model_index": model_index, "silver_index": silver_index,
            "model_choice": rows[model_index]["semanticKey"],
            "silver_choice": rows[silver_index]["semanticKey"],
            "silver_top_tied": model_index in model_top,
            "regret": float(q_values[silver_index] - q_values[model_index]),
            "margin": float(scores[model_order[0]] - scores[model_order[1]]),
            "min_p_win": float(p_values.min()), "chosen_p_win": float(p_values[model_index]),
            "predicted_range": float(scores.max() - scores.min()),
            "silver_simulations": int(sum(int(row["silverSimulations"]) for row in rows)),
            "action_rows": len(rows), "actual_outcomes": actual,
            "all_siblings_survive": all(value == 1 for value in actual),
            "at_least_one_dies": any(int(row.get("actual_true_death", 0)) == 1 for row in rows),
            "all_outcomes_valid": all(value == 1 and outcome in (0, 1)
                                       for value, outcome in zip(labels_valid, actual)),
            "act": int(rows[0]["act"]), "floor": int(rows[0]["floor"]),
            "encounter": str(rows[0].get("combat_encounter", rows[0].get("encounter", ""))),
            "roomClass": str(rows[0].get("combat_roomClass", rows[0].get("roomClass", ""))),
            "family": str(rows[0]["family"]),
        })
    require(groups, "no decision groups")
    return groups


def quantile(values: Iterable[float], probability: float) -> float:
    values = list(map(float, values))
    require(values, "quantile of empty values")
    return float(np.percentile(values, probability * 100.0))


def arm_metrics(groups: list[dict[str, Any]], accepted: set[tuple[int, int]]) -> dict[str, Any]:
    total_simulations = sum(group["silver_simulations"] for group in groups)
    accepted_groups = [group for group in groups if (group["sourceSeed"], group["decisionIdx"]) in accepted]
    regrets = [group["regret"] if group in accepted_groups else 0.0 for group in groups]
    top = [group["silver_top_tied"] if group in accepted_groups else True for group in groups]
    avoided = sum(group["silver_simulations"] for group in accepted_groups)
    return {
        "decisions": len(groups), "accepted_decisions": len(accepted_groups),
        "rejected_decisions": len(groups) - len(accepted_groups),
        "accepted_action_rows": sum(group["action_rows"] for group in accepted_groups),
        "coverage": len(accepted_groups) / len(groups),
        "fallback_rate": 1.0 - len(accepted_groups) / len(groups),
        "avoided_silver_simulations": avoided,
        "total_silver_simulations": total_simulations,
        "simulation_savings_fraction": avoided / total_simulations if total_simulations else None,
        "mean_regret": float(statistics.fmean(regrets)), "median_regret": float(statistics.median(regrets)),
        "p90_regret": quantile(regrets, 0.90), "p95_regret": quantile(regrets, 0.95),
        "max_regret": float(max(regrets)), "top_or_tied_agreement": float(statistics.fmean(top)),
    }


def pure_model_metrics(groups: list[dict[str, Any]]) -> dict[str, Any]:
    return arm_metrics(groups, {(g["sourceSeed"], g["decisionIdx"]) for g in groups})


def candidate_gates(groups: list[dict[str, Any]], signal: str = "min_p_win") -> list[dict[str, Any]]:
    result = []
    for margin in MARGINS:
        for threshold in SURVIVAL_THRESHOLDS:
            accepted = {
                (g["sourceSeed"], g["decisionIdx"])
                for g in groups
                if g["margin"] + EPSILON >= margin and g[signal] + EPSILON >= threshold
            }
            metrics = arm_metrics(groups, accepted)
            result.append({"signal": signal, "margin": margin, "survival_threshold": threshold,
                           "accepted": sorted([list(x) for x in accepted]), **metrics})
    return result


def select_gate(validation_gates: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [gate for gate in validation_gates
                if gate["accepted_decisions"] > 0 and gate["mean_regret"] <= 0.005 + EPSILON
                and gate["p95_regret"] <= 0.025 + EPSILON]
    if not eligible:
        return None
    return max(eligible, key=lambda g: (g["simulation_savings_fraction"], -g["margin"], -g["survival_threshold"]))


def spearman(x: Iterable[float], y: Iterable[float]) -> float | None:
    x, y = np.asarray(list(x), dtype=float), np.asarray(list(y), dtype=float)
    if len(x) < 2 or np.std(x) <= EPSILON or np.std(y) <= EPSILON:
        return None
    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="stable")
        result = np.empty(len(values), dtype=float)
        i = 0
        while i < len(values):
            j = i + 1
            while j < len(values) and values[order[j]] == values[order[i]]:
                j += 1
            result[order[i:j]] = (i + j - 1) / 2.0
            i = j
        return result
    return float(np.corrcoef(ranks(x), ranks(y))[0, 1])


def pearson(x: Iterable[float], y: Iterable[float]) -> float | None:
    x, y = np.asarray(list(x), dtype=float), np.asarray(list(y), dtype=float)
    if len(x) < 2 or np.std(x) <= EPSILON or np.std(y) <= EPSILON:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def pairwise_concordance(rows: list[dict[str, Any]]) -> float | None:
    values = []
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            q_delta = float(rows[left]["qProduct"]) - float(rows[right]["qProduct"])
            if abs(q_delta) <= EPSILON:
                continue
            model_delta = float(rows[left]["expected_signed_outcome"]) - float(rows[right]["expected_signed_outcome"])
            values.append(1.0 if q_delta * model_delta > EPSILON else 0.5 if abs(model_delta) <= EPSILON else 0.0)
    return float(statistics.fmean(values)) if values else None


def ranking_metrics(groups: list[dict[str, Any]]) -> dict[str, Any]:
    regrets = [group["regret"] for group in groups]
    concordance = [pairwise_concordance(group["rows"]) for group in groups]
    concordance = [x for x in concordance if x is not None]
    return {
        "decisions": len(groups), "top_or_silver_tied_agreement": float(statistics.fmean(group["silver_top_tied"] for group in groups)),
        "mean_regret": float(statistics.fmean(regrets)), "median_regret": float(statistics.median(regrets)),
        "p90_regret": quantile(regrets, 0.90), "p95_regret": quantile(regrets, 0.95),
        "max_regret": float(max(regrets)), "fraction_regret": {
            "eq_0": float(sum(abs(x) <= EPSILON for x in regrets) / len(regrets)),
            "le_0.01": float(sum(x <= 0.01 + EPSILON for x in regrets) / len(regrets)),
            "le_0.025": float(sum(x <= 0.025 + EPSILON for x in regrets) / len(regrets)),
            "le_0.05": float(sum(x <= 0.05 + EPSILON for x in regrets) / len(regrets)),
            "gt_0.10": float(sum(x > 0.10 + EPSILON for x in regrets) / len(regrets)),
        },
        "macro_pairwise_concordance": float(statistics.fmean(concordance)) if concordance else None,
        "pairwise_decisions": len(concordance),
    }


def bootstrap_test(groups: list[dict[str, Any]], accepted: set[tuple[int, int]], *, replicates: int, seed: int) -> dict[str, Any]:
    by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        by_source[group["sourceSeed"]].append(group)
    sources = sorted(by_source)
    rng = np.random.default_rng(seed)
    mean_regrets, savings, top = [], [], []
    for draw in rng.integers(0, len(sources), size=(replicates, len(sources))):
        sample = [group for index in draw for group in by_source[sources[int(index)]]]
        metrics = arm_metrics(sample, accepted)
        mean_regrets.append(metrics["mean_regret"])
        savings.append(metrics["simulation_savings_fraction"])
        top.append(metrics["top_or_tied_agreement"])
    def interval(values: list[float], point: float) -> dict[str, Any]:
        return {"estimate": point, "ci95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]}
    point = arm_metrics(groups, accepted)
    return {
        "unit": "sourceSeed", "source_groups": len(sources), "replicates": replicates,
        "mean_regret": interval(mean_regrets, point["mean_regret"]),
        "simulation_savings_fraction": interval(savings, point["simulation_savings_fraction"]),
        "top_or_tied_agreement": interval(top, point["top_or_tied_agreement"]),
    }


def safety_slices(groups: list[dict[str, Any]], accepted: set[tuple[int, int]]) -> dict[str, Any]:
    predicates = {
        "any_sibling_p_win_lt_0.5": lambda g: min(row["p_win"] for row in g["rows"]) < 0.5,
        "any_sibling_p_win_lt_0.9": lambda g: min(row["p_win"] for row in g["rows"]) < 0.9,
        "all_siblings_p_win_ge_0.95": lambda g: min(row["p_win"] for row in g["rows"]) >= 0.95,
        "all_siblings_p_win_ge_0.99": lambda g: min(row["p_win"] for row in g["rows"]) >= 0.99,
        "BOSS": lambda g: g["roomClass"] == "BOSS",
        "ELITE": lambda g: g["roomClass"] == "ELITE",
        "NORMAL": lambda g: g["roomClass"] == "NORMAL",
    }
    for act in (1, 2, 3):
        predicates[f"Act {act}"] = lambda g, act=act: g["act"] == act
    for family in ("REWARDS", "CAMPFIRE", "SHOP", "EVENT", "TREASURE", "BOSS_RELIC", "SELECTOR"):
        predicates[family] = lambda g, family=family: g["family"] == family
    result = {}
    for name, predicate in predicates.items():
        selected = [g for g in groups if predicate(g)]
        if not selected:
            result[name] = {"decisions": 0, "unique_source_seeds": 0}
            continue
        metrics = arm_metrics(selected, accepted & {(g["sourceSeed"], g["decisionIdx"]) for g in selected})
        result[name] = {**metrics, "unique_source_seeds": len({g["sourceSeed"] for g in selected})}
    return result


def catastrophic_cases(groups: list[dict[str, Any]], accepted: set[tuple[int, int]]) -> list[dict[str, Any]]:
    cases = []
    for group in groups:
        identity = (group["sourceSeed"], group["decisionIdx"])
        if identity not in accepted or group["regret"] <= 0.05 + EPSILON:
            continue
        cases.append({
            "sourceSeed": group["sourceSeed"], "decisionIdx": group["decisionIdx"],
            "act": group["act"], "floor": group["floor"], "encounter": group["encounter"],
            "roomClass": group["roomClass"], "family": group["family"],
            "model_choice": group["model_choice"], "silver_choice": group["silver_choice"],
            "regret": group["regret"],
            "siblings": [{name: row.get(name) for name in (
                "semanticKey", "p_win", "predicted_win_hp_frac", "predicted_loss_remaining_frac",
                "expected_signed_outcome", "qProduct", "silverSimulations")}
                         for row in group["rows"]],
        })
    return cases


def target_mismatch(groups: list[dict[str, Any]]) -> dict[str, Any]:
    def report(selected: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [row for group in selected for row in group["rows"]]
        expected = [row["expected_signed_outcome"] for row in rows]
        q_values = [row["qProduct"] for row in rows]
        within = [spearman([row["expected_signed_outcome"] for row in group["rows"]],
                           [row["qProduct"] for row in group["rows"]]) for group in selected]
        within = [value for value in within if value is not None]
        concordance = [pairwise_concordance(group["rows"]) for group in selected]
        concordance = [value for value in concordance if value is not None]
        return {
            "decisions": len(selected), "action_rows": len(rows),
            "pearson": pearson(expected, q_values), "spearman": spearman(expected, q_values),
            "within_decision_spearman_macro": statistics.fmean(within) if within else None,
            "within_decision_spearman_decisions": len(within),
            "macro_pairwise_concordance": statistics.fmean(concordance) if concordance else None,
            "pairwise_decisions": len(concordance),
        }
    all_survive = [g for g in groups if g["all_outcomes_valid"] and g["all_siblings_survive"]]
    any_dies = [g for g in groups if g["all_outcomes_valid"] and g["at_least_one_dies"]]
    return {"all": report(groups), "all_siblings_survive": report(all_survive),
            "at_least_one_sibling_dies": report(any_dies),
            "outcome_slice_note": "Outcome slices require valid actual combat labels for every sibling; groups with invalid labels are omitted."}


def analyze_decisions(frame: pd.DataFrame, *, bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
                      bootstrap_seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    groups = group_rows(frame)
    by_split = {}
    # Reuse the frozen source-seed split from the evaluator trainer. Importing
    # the function keeps this analysis aligned with §219 without retraining.
    from train_combat_evaluator import stable_split
    split = stable_split(frame.sourceSeed)
    for name in ("train", "validation", "test"):
        by_split[name] = [g for g in groups if split[g["sourceSeed"]] == name]

    validation_gates = candidate_gates(by_split["validation"], "min_p_win")
    chosen = select_gate(validation_gates)
    chosen_identity = None if chosen is None else (chosen["margin"], chosen["survival_threshold"], chosen["signal"])
    test_accepted = set()
    if chosen is not None:
        test_accepted = {(g["sourceSeed"], g["decisionIdx"]) for g in by_split["test"]
                         if g["margin"] + EPSILON >= chosen["margin"]
                         and g[chosen["signal"]] + EPSILON >= chosen["survival_threshold"]}
    test = by_split["test"]
    return {
        "schema": "combat_evaluator_silver_gate_v1",
        "split": {name: {"decisions": len(value), "source_seeds": len({g["sourceSeed"] for g in value})}
                   for name, value in by_split.items()},
        "ranking": {name: ranking_metrics(value) for name, value in by_split.items() if name in ("validation", "test")},
        "always_model": {name: pure_model_metrics(value) for name, value in by_split.items()},
        "always_silver": {name: arm_metrics(value, set()) for name, value in by_split.items()},
        "validation_gate_grid": validation_gates,
        "chosen_gate": chosen,
        "chosen_gate_identity": chosen_identity,
        "test": {
            "always_model": pure_model_metrics(test), "hybrid_gate": arm_metrics(test, test_accepted),
            "accepted": sorted([list(x) for x in test_accepted]),
            "rejected": sorted([[g["sourceSeed"], g["decisionIdx"]] for g in test if (g["sourceSeed"], g["decisionIdx"]) not in test_accepted]),
            "bootstrap": bootstrap_test(test, test_accepted, replicates=bootstrap_replicates, seed=bootstrap_seed)
            if chosen is not None else None,
            "safety_slices": safety_slices(test, test_accepted) if chosen is not None else {},
            "catastrophic_accepted_cases": catastrophic_cases(test, test_accepted) if chosen is not None else [],
            "target_mismatch": target_mismatch(test),
        },
        "classification": classify_result(chosen, test, test_accepted),
        "constraints": {"simulator_called": False, "silver_called": False, "new_labels": False,
                        "retrained": False, "gameplay_integration": False},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }


def classify_result(chosen: dict[str, Any] | None, test: list[dict[str, Any]], accepted: set[tuple[int, int]]) -> str:
    if chosen is None:
        return "MODEL USEFUL BUT GATE NOT READY"
    metrics = arm_metrics(test, accepted)
    catastrophic = catastrophic_cases(test, accepted)
    if metrics["mean_regret"] <= 0.005 and metrics["p95_regret"] <= 0.025 and not catastrophic:
        if metrics["simulation_savings_fraction"] is not None and metrics["simulation_savings_fraction"] >= 0.75:
            return "GATE VERY PROMISING"
        if metrics["simulation_savings_fraction"] is not None and metrics["simulation_savings_fraction"] >= 0.50:
            return "GATE PROMISING"
    if catastrophic or metrics["mean_regret"] > 0.025:
        return "MODEL UNSAFE"
    return "MODEL USEFUL BUT GATE NOT READY"


def build_report(frame: pd.DataFrame, metadata: dict[str, Any], predictor_manifest_info: dict[str, Any] | None,
                 evidence_path: Path | None, raw_package: Path | None, result: dict[str, Any]) -> dict[str, Any]:
    result = {**result, "inputs": metadata, "artifacts": {
        "predictions": {"path": str(metadata.get("prediction_path", "")),
                        "sha256": metadata.get("prediction_sha256")},
        "predictor_manifest": predictor_manifest_info,
        "evidence": {"path": str(evidence_path.resolve()), "sha256": sha256(evidence_path)} if evidence_path else None,
        "raw_package": {"path": str(raw_package.resolve()), "sha256": sha256(raw_package)} if raw_package else None,
        "semantic_combat_manifests": metadata.get("manifests"),
    }}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs=64, type=Path, help="the 64 frozen combat sidecar manifests")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--predictor-manifest", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--raw-package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    args = parser.parse_args()
    require(args.bootstrap_replicates >= BOOTSTRAP_REPLICATES, "at least 5,000 bootstrap replicates are required")
    semantic_rows, manifests = collect_semantic_rows(args.manifests)
    combat, corpus = load_corpus(args.manifests, evidence_path=args.evidence, raw_package=args.raw_package)
    frame, metadata = join_inputs(semantic_rows, combat, args.predictions, args.predictor_manifest)
    metadata.update({"manifests": manifests, "prediction_path": str(args.predictions.resolve()),
                     "prediction_sha256": sha256(args.predictions), "corpus": corpus})
    result = analyze_decisions(frame, bootstrap_replicates=args.bootstrap_replicates, bootstrap_seed=args.bootstrap_seed)
    report = build_report(frame, metadata, metadata["predictor_manifest"], args.evidence, args.raw_package, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "classification": report["classification"],
                      "chosen_gate": report["chosen_gate_identity"], "test": report["test"]["hybrid_gate"]},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
