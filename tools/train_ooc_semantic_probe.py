#!/usr/bin/env python3
"""Probe whether semantic OOC action features learn sibling preferences.

This is an offline research diagnostic.  It consumes already validated semantic
OOC manifests, never invokes the simulator, and does not export a runtime model.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


EFFECT_NAMES = {
    0: "UPGRADE_CARD", 1: "REMOVE_CARD", 2: "TRANSFORM_CARD",
    3: "TRANSFORM_UPGRADE_CARD", 4: "DUPLICATE_CARD", 5: "TAKE_CARD",
    6: "BOTTLE_CARD", 7: "SACRIFICE_CARD", 8: "TAKE_RELIC",
    9: "TAKE_GOLD", 10: "TAKE_POTION", 11: "TAKE_KEY",
    12: "SKIP_CARD_REWARD", 13: "SINGING_BOWL", 14: "LEAVE_REWARDS",
    15: "OPEN_CHEST", 16: "LEAVE_TREASURE", 17: "REST",
    18: "TAKE_RUBY_KEY", 19: "LIFT", 20: "DIG", 21: "LEAVE_CAMPFIRE",
    22: "BUY_CARD", 23: "BUY_RELIC", 24: "BUY_POTION",
    25: "LEAVE_SHOP", 26: "EVENT_CHOICE", 27: "TAKE_BOSS_RELIC",
    28: "SKIP_BOSS_RELIC", 29: "DISCARD_POTION",
}
SOURCE_NAMES = {
    0: "CAMPFIRE_SMITH", 1: "CAMPFIRE", 2: "CAMPFIRE_PEACE_PIPE",
    3: "SHOP", 4: "SHOP_REMOVE", 5: "EVENT", 6: "SELECTOR",
    7: "REWARDS", 8: "TREASURE", 9: "BOSS_RELIC",
}
FAMILY_NAMES = {
    "REWARDS": "REWARDS",
    "CAMPFIRE_SMITH": "CAMPFIRE",
    "CAMPFIRE": "CAMPFIRE",
    "CAMPFIRE_PEACE_PIPE": "CAMPFIRE",
    "SHOP": "SHOP",
    "SHOP_REMOVE": "SHOP",
    "EVENT": "EVENT",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def add_num(out: dict[str, float], name: str, value: Any) -> None:
    out[f"num:{name}"] = float(value)


def add_cat(out: dict[str, float], name: str, value: Any) -> None:
    out[f"cat:{name}={value}"] = 1.0


def set_card(out: dict[str, float], card: dict[str, Any], prefix: str = "card") -> None:
    if not isinstance(card, dict):
        return
    for name, default in (("id", -1), ("misc", -1), ("bottle", -1), ("occurrence", -1)):
        add_num(out, f"{prefix}_{name}", card.get(name, default))
    add_num(out, f"{prefix}_upgraded", int(card.get("upgraded", False)))
    if "id" in card:
        add_cat(out, f"{prefix}_id", card["id"])


def set_entity(out: dict[str, float], entity: Any, prefix: str = "entity") -> None:
    if not isinstance(entity, dict):
        return
    kind = entity.get("type", "none")
    add_cat(out, f"{prefix}_type", kind)
    if kind == "card":
        set_card(out, entity.get("value", {}), prefix=f"{prefix}_card")
    elif kind != "none" and "value" in entity:
        add_num(out, f"{prefix}_value", entity["value"])
        add_cat(out, f"{prefix}_id", entity["value"])


def semantic_features(row: dict[str, str]) -> dict[str, float]:
    """Decode the typed payload into small numeric and one-hot features.

    The canonical semantic key is intentionally not consumed.  Numeric IDs are
    retained for ordered split generalization, while categorical one-hot copies
    prevent unrelated IDs from being treated as a serialized string.
    """
    payload = json.loads(row["semanticPayload"])
    out: dict[str, float] = {}
    effect = int(row["semanticEffect"])
    source = int(row["semanticSource"])
    add_num(out, "effect_id", effect)
    add_num(out, "source_id", source)
    add_cat(out, "effect", EFFECT_NAMES[effect])
    add_cat(out, "source", SOURCE_NAMES[source])
    kind = payload["type"]
    add_cat(out, "payload_type", kind)

    # Initialize the requested scalar fields with explicit non-applicable
    # sentinels.  This keeps all arms on one fixed feature contract.
    defaults = {
        "card_id": -1, "card_misc": -1, "card_upgraded": -1,
        "card_bottle": -1, "card_occurrence": -1, "relic_id": -1,
        "potion_id": -1, "key_id": -1, "gold_amount": -1,
        "shop_price": -1, "event_id": -1, "event_option": -1,
        "selector_type": -1, "selector_required_picks": -1,
        "selector_completed_picks": -1, "reward_group_size": -1,
        "reward_group_occurrence": -1, "reward_occurrence": -1,
        "reward_sapphire_paired": -1, "payload_occurrence": -1,
    }
    for name, value in defaults.items():
        add_num(out, name, value)

    def copy_card(card: Any) -> None:
        if not isinstance(card, dict):
            return
        add_num(out, "card_id", card.get("id", -1))
        add_num(out, "card_misc", card.get("misc", -1))
        add_num(out, "card_upgraded", int(card.get("upgraded", False)))
        add_num(out, "card_bottle", card.get("bottle", -1))
        add_num(out, "card_occurrence", card.get("occurrence", -1))
        if "id" in card:
            add_cat(out, "card_id", card["id"])

    def copy_entity_scalars(entity: Any) -> None:
        if not isinstance(entity, dict):
            return
        kind = entity.get("type", "none")
        value = entity.get("value")
        if kind == "card":
            copy_card(value)
        elif kind == "relic":
            add_num(out, "relic_id", value if value is not None else -1)
            add_cat(out, "relic_id", value if value is not None else -1)
        elif kind == "potion":
            add_num(out, "potion_id", value if value is not None else -1)
            add_cat(out, "potion_id", value if value is not None else -1)
        elif kind == "key":
            add_num(out, "key_id", value if value is not None else -1)
            add_cat(out, "key_id", value if value is not None else -1)
        elif kind == "gold":
            add_num(out, "gold_amount", value if value is not None else -1)

    if kind == "deck_card":
        copy_card(payload.get("card"))
    elif kind == "transaction":
        copy_card(payload.get("card"))
        add_num(out, "event_id", payload.get("event", -1))
        add_num(out, "event_option", payload.get("option", -1))
        add_num(out, "shop_price", payload.get("expectedGoldCost", -1))
        add_cat(out, "event_id", payload.get("event", -1))
    elif kind == "selector":
        add_num(out, "selector_type", payload.get("selectorType", -1))
        add_num(out, "selector_required_picks", payload.get("requiredPicks", -1))
        add_num(out, "selector_completed_picks", payload.get("completedPicks", -1))
        add_cat(out, "selector_type", payload.get("selectorType", -1))
        target = payload.get("target", {})
        add_cat(out, "selector_target_type", target.get("type", "none"))
        if target.get("type") in ("deck_card", "candidate"):
            copy_card(target.get("card"))
            add_num(out, "payload_occurrence", target.get("occurrence", -1))
    elif kind == "reward":
        group = payload.get("cardGroup", [])
        add_num(out, "reward_group_size", len(group))
        add_num(out, "reward_group_occurrence", payload.get("groupOccurrence", -1))
        add_num(out, "reward_occurrence", payload.get("occurrence", -1))
        add_num(out, "reward_sapphire_paired", int(payload.get("sapphirePaired", False)))
        add_cat(out, "reward_entity_type", payload.get("entity", {}).get("type", "none"))
        set_entity(out, payload.get("entity", {}), prefix="reward_entity")
        copy_entity_scalars(payload.get("entity", {}))
        # Preserve small group information without serializing the full group.
        if group:
            add_num(out, "reward_first_card_id", group[0].get("id", -1))
            add_num(out, "reward_upgraded_count", sum(int(c.get("upgraded", False)) for c in group))
            add_cat(out, "reward_first_card_id", group[0].get("id", -1))
    elif kind == "shop":
        add_num(out, "shop_price", payload.get("expectedPrice", -1))
        add_num(out, "payload_occurrence", payload.get("occurrence", -1))
        set_entity(out, payload.get("entity", {}), prefix="shop_entity")
        copy_entity_scalars(payload.get("entity", {}))
        add_cat(out, "shop_entity_type", payload.get("entity", {}).get("type", "none"))
    elif kind == "event":
        add_num(out, "event_id", payload.get("event", -1))
        add_num(out, "event_option", payload.get("option", -1))
        add_cat(out, "event_id", payload.get("event", -1))
    elif kind == "relic":
        add_num(out, "relic_id", payload.get("relic", -1))
        add_num(out, "payload_occurrence", payload.get("occurrence", -1))
        add_cat(out, "relic_id", payload.get("relic", -1))
    return out


def primitive_features(row: dict[str, str]) -> dict[str, float]:
    trace = json.loads(row["executedPrimitiveBits"])
    require(isinstance(trace, list) and 1 <= len(trace) <= 2, "probe expects one or two primitive trace entries")
    out: dict[str, float] = {}
    add_num(out, "trace_length", len(trace))
    for index in range(2):
        value = int(trace[index]) if index < len(trace) else 0
        add_num(out, f"primitive_{index}_value", value)
        for bit in range(32):
            add_num(out, f"primitive_{index}_bit_{bit}", (value >> bit) & 1)
    return out


def vectorize(dicts: list[dict[str, float]], keys: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    if keys is None:
        keys = sorted({key for item in dicts for key in item})
    index = {key: i for i, key in enumerate(keys)}
    out = np.zeros((len(dicts), len(keys)), dtype=np.float32)
    for row_index, item in enumerate(dicts):
        for key, value in item.items():
            out[row_index, index[key]] = value
    return out, keys


def grouped_folds(groups: list[tuple[int, int]], seed: int, folds: int = 5) -> dict[tuple[int, int], int]:
    ordered = list(groups)
    rng = np.random.default_rng(seed)
    rng.shuffle(ordered)
    return {group: index % folds for index, group in enumerate(ordered)}


def percentile(values: list[float], fraction: float) -> float | None:
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return None
    return float(np.percentile(values, fraction * 100.0))


def json_safe(value: Any) -> Any:
    """Convert internal NaN sentinels to JSON null and reject other odd values."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def regression_metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = prediction - y
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "mae": float(np.mean(np.abs(error))),
    }


def decision_metrics(rows: list[dict[str, Any]], prediction: np.ndarray) -> dict[str, Any]:
    by_group: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_group[(int(row["sourceSeed"]), int(row["decisionIdx"]))].append(index)
    per_group = []
    pair_correct = 0.0
    pair_total = 0
    for group, indices in sorted(by_group.items()):
        truth = np.asarray([float(rows[index]["qProduct"]) for index in indices])
        pred = prediction[indices]
        selected = int(np.argmax(pred))
        maximum = float(np.max(truth))
        maxima = np.flatnonzero(np.isclose(truth, maximum, rtol=0.0, atol=1e-12))
        regret = maximum - float(truth[selected])
        exact = int(selected == int(maxima[0]))
        tied = int(selected in set(map(int, maxima)))
        pair_c = 0.0
        pair_n = 0
        for left in range(len(indices)):
            for right in range(left + 1, len(indices)):
                truth_delta = truth[left] - truth[right]
                if abs(truth_delta) <= 1e-12:
                    continue
                pair_n += 1
                pred_delta = pred[left] - pred[right]
                if abs(pred_delta) <= 1e-12:
                    pair_c += 0.5
                elif (truth_delta > 0) == (pred_delta > 0):
                    pair_c += 1.0
        if pair_n:
            pair_correct += pair_c
            pair_total += pair_n
            pair_value = pair_c / pair_n
        else:
            pair_value = float("nan")
        try:
            from scipy.stats import spearmanr
            if np.allclose(truth, truth[0]) or np.allclose(pred, pred[0]):
                spearman = float("nan")
            else:
                spearman = float(spearmanr(truth, pred).statistic)
                if not math.isfinite(spearman):
                    spearman = float("nan")
        except (ImportError, ValueError):
            spearman = float("nan")
        per_group.append({
            "group": [group[0], group[1]],
            "family": group_family(rows, indices),
            "rows": len(indices),
            "top1": exact,
            "top_or_tied": tied,
            "regret": regret,
            "pairwise_concordance": pair_value,
            "spearman": spearman,
        })
    regrets = [item["regret"] for item in per_group]
    pair_values = [item["pairwise_concordance"] for item in per_group if math.isfinite(item["pairwise_concordance"])]
    spearmans = [item["spearman"] for item in per_group if math.isfinite(item["spearman"])]
    return {
        "macro": {
            "decisions": len(per_group),
            "top1": float(np.mean([item["top1"] for item in per_group])),
            "top_or_tied": float(np.mean([item["top_or_tied"] for item in per_group])),
            "mean_regret": float(np.mean(regrets)),
            "median_regret": float(np.median(regrets)),
            "pairwise_concordance": float(np.mean(pair_values)) if pair_values else None,
            "spearman": float(np.mean(spearmans)) if spearmans else None,
            "spearman_defined_decisions": len(spearmans),
        },
        "pair_weighted": {
            "concordant_pairs": pair_correct,
            "non_tied_pairs": pair_total,
            "pairwise_concordance": pair_correct / pair_total if pair_total else None,
        },
        "per_group": per_group,
    }


def group_family(rows: list[dict[str, Any]], indices: list[int]) -> str:
    names = {SOURCE_NAMES[int(rows[index]["semanticSource"])] for index in indices}
    mapped = {FAMILY_NAMES.get(name, "OTHER") for name in names}
    return next(iter(mapped)) if len(mapped) == 1 else "OTHER"


def train_model(x_train: np.ndarray, y_train: np.ndarray, params: dict[str, Any]):
    import xgboost as xgb
    model = xgb.XGBRegressor(**params)
    model.fit(x_train, y_train, verbose=False)
    return model


def bootstrap_difference(
    semantic: list[dict[str, Any]], primitive: list[dict[str, Any]], field: str,
    seed: int, samples: int,
) -> dict[str, float | int | None]:
    left = {tuple(item["group"]): item[field] for item in semantic}
    right = {tuple(item["group"]): item[field] for item in primitive}
    keys = [key for key in left if math.isfinite(left[key]) and math.isfinite(right[key])]
    if not keys:
        return {"decisions": 0, "difference": None, "ci95": [None, None]}
    differences = np.asarray([float(left[key]) - float(right[key]) for key in keys])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(differences), size=(samples, len(differences)))
    distribution = differences[draws].mean(axis=1)
    return {
        "decisions": len(keys),
        "difference": float(differences.mean()),
        "ci95": [float(np.percentile(distribution, 2.5)), float(np.percentile(distribution, 97.5))],
    }


def disagreement_examples(
    rows: list[dict[str, Any]], semantic_prediction: np.ndarray,
    primitive_prediction: np.ndarray, fold_by_group: dict[tuple[int, int], int],
    limit: int = 5,
) -> list[dict[str, Any]]:
    by_group: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_group[row["_group"]].append(index)
    candidates = []
    for group, indices in sorted(by_group.items()):
        semantic_order = sorted(indices, key=lambda index: (-semantic_prediction[index], index))
        primitive_order = sorted(indices, key=lambda index: (-primitive_prediction[index], index))
        if semantic_order[0] == primitive_order[0]:
            continue
        truth = [float(rows[index]["qProduct"]) for index in indices]
        semantic_regret = max(truth) - float(rows[semantic_order[0]]["qProduct"])
        primitive_regret = max(truth) - float(rows[primitive_order[0]]["qProduct"])
        semantic_rank = {index: rank for rank, index in enumerate(semantic_order, 1)}
        primitive_rank = {index: rank for rank, index in enumerate(primitive_order, 1)}
        actions = []
        for index in sorted(indices, key=lambda item: (-float(rows[item]["qProduct"]), item)):
            payload = json.loads(rows[index]["semanticPayload"])
            actions.append({
                "semanticActionIdx": int(rows[index]["semanticActionIdx"]),
                "effect": EFFECT_NAMES[int(rows[index]["semanticEffect"])],
                "source": SOURCE_NAMES[int(rows[index]["semanticSource"])],
                "payload_type": payload["type"],
                "true_q": float(rows[index]["qProduct"]),
                "true_deltaQ": float(rows[index]["qProduct"]) - float(np.mean(truth)),
                "semantic_predicted_deltaQ": float(semantic_prediction[index]),
                "primitive_predicted_deltaQ": float(primitive_prediction[index]),
                "semantic_rank": semantic_rank[index],
                "primitive_rank": primitive_rank[index],
            })
        candidates.append({
            "group": [group[0], group[1]],
            "fold": fold_by_group[group],
            "family": group_family(rows, indices),
            "siblings": len(indices),
            "semantic_selected_action": int(rows[semantic_order[0]]["semanticActionIdx"]),
            "primitive_selected_action": int(rows[primitive_order[0]]["semanticActionIdx"]),
            "semantic_regret": semantic_regret,
            "primitive_regret": primitive_regret,
            "actions": actions,
        })
    candidates.sort(key=lambda item: (-abs(item["semantic_regret"] - item["primitive_regret"]), item["group"]))
    return candidates[:limit]


def load_data(manifest_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from tools.ooc_semantic_pipeline_contract import validate_corpus
    except ModuleNotFoundError:
        from ooc_semantic_pipeline_contract import validate_corpus
    all_rows: list[dict[str, Any]] = []
    manifest_info = []
    seen_groups: set[tuple[int, int]] = set()
    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text())
        validation = validate_corpus(manifest)
        require(validation["decisions"] == 16 and validation["quarantined"] == 0,
                f"unexpected validation result for {manifest_path}: {validation}")
        csv_path = Path(manifest["csv"]["path"])
        with csv_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            group = (int(row["sourceSeed"]), int(row["decisionIdx"]))
            require(group not in seen_groups, f"duplicate decision group across shards: {group}")
            row["_group"] = group
            row["_manifest"] = str(manifest_path)
            all_rows.append(row)
        seen_groups.update((int(row["sourceSeed"]), int(row["decisionIdx"])) for row in rows)
        manifest_info.append({
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "csv": str(csv_path),
            "csv_sha256": sha256(csv_path),
            "validation": validation,
        })
    require(len(all_rows) == 1018 and len(seen_groups) == 128, "unexpected semantic corpus size")
    return all_rows, {"shards": manifest_info, "rows": len(all_rows), "decisions": len(seen_groups)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs=8, type=Path, help="the eight validated semantic evaluation manifests")
    parser.add_argument("--output", type=Path, required=True, help="JSON report path")
    parser.add_argument("--split-seed", type=int, default=20260910)
    parser.add_argument("--bootstrap-seed", type=int, default=20260911)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--rounds", type=int, default=160)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    require(args.bootstrap_samples > 0 and args.threads > 0, "bootstrap samples and threads must be positive")

    rows, corpus = load_data(sorted(args.manifests))
    groups = sorted({row["_group"] for row in rows})
    fold_by_group = grouped_folds(groups, args.split_seed)
    fold_rows = {
        str(fold): sum(1 for row in rows if fold_by_group[row["_group"]] == fold)
        for fold in range(5)
    }
    fold_groups = {
        str(fold): sum(1 for group in groups if fold_by_group[group] == fold)
        for fold in range(5)
    }

    state_names = json.loads(Path(corpus["shards"][0]["manifest"]).read_text())["stateFeatures"]["header"].split(",")
    state = np.asarray([[float(value) for value in row["richRow"].split(",")] for row in rows], dtype=np.float32)
    require(state.shape[1] == len(state_names), "richRow/state header mismatch")
    semantic_dicts = [semantic_features(row) for row in rows]
    primitive_dicts = [primitive_features(row) for row in rows]
    semantic_action, semantic_keys = vectorize(semantic_dicts)
    primitive_action, primitive_keys = vectorize(primitive_dicts)
    x = {
        "SEMANTIC": np.concatenate([state, semantic_action], axis=1),
        "PRIMITIVE": np.concatenate([state, primitive_action], axis=1),
        "ACTION_AGNOSTIC": state,
    }
    y = np.asarray([float(row["qProduct"]) for row in rows], dtype=np.float64)
    y_delta = np.empty_like(y)
    by_group: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_group[row["_group"]].append(index)
    for indices in by_group.values():
        y_delta[indices] = y[indices] - np.mean(y[indices])

    model_params = {
        "n_estimators": args.rounds,
        "max_depth": 3,
        "learning_rate": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.8,
        "min_child_weight": 2,
        "reg_lambda": 1.0,
        "objective": "reg:squarederror",
        "tree_method": "hist",
        "n_jobs": args.threads,
        "random_state": args.split_seed,
        "verbosity": 0,
    }
    oof: dict[str, np.ndarray] = {name: np.full(len(rows), np.nan) for name in x}
    fold_reports: dict[str, dict[str, Any]] = {}
    for fold in range(5):
        test_indices = np.asarray([i for i, row in enumerate(rows) if fold_by_group[row["_group"]] == fold])
        train_indices = np.asarray([i for i, row in enumerate(rows) if fold_by_group[row["_group"]] != fold])
        for name, features in x.items():
            model = train_model(features[train_indices], y_delta[train_indices], model_params)
            oof[name][test_indices] = model.predict(features[test_indices])
        fold_reports[str(fold)] = {
            name: {
                "regression": regression_metrics(y_delta[test_indices], oof[name][test_indices]),
                "ranking": decision_metrics([rows[i] for i in test_indices], oof[name][test_indices]),
            }
            for name in x
        }

    cv_metrics = {}
    for name in x:
        ranking = decision_metrics(rows, oof[name])
        ranking["regression"] = regression_metrics(y_delta, oof[name])
        cv_metrics[name] = ranking

    full_fit = {}
    for name, features in x.items():
        model = train_model(features, y_delta, model_params)
        prediction = model.predict(features)
        ranking = decision_metrics(rows, prediction)
        ranking["regression"] = regression_metrics(y_delta, prediction)
        full_fit[name] = ranking

    semantic_groups = cv_metrics["SEMANTIC"]["per_group"]
    primitive_groups = cv_metrics["PRIMITIVE"]["per_group"]
    bootstrap = {
        "mean_selected_regret": bootstrap_difference(semantic_groups, primitive_groups, "regret", args.bootstrap_seed, args.bootstrap_samples),
        "pairwise_concordance": bootstrap_difference(semantic_groups, primitive_groups, "pairwise_concordance", args.bootstrap_seed + 1, args.bootstrap_samples),
        "top_or_truth_tied": bootstrap_difference(semantic_groups, primitive_groups, "top_or_tied", args.bootstrap_seed + 2, args.bootstrap_samples),
    }
    examples = disagreement_examples(rows, oof["SEMANTIC"], oof["PRIMITIVE"], fold_by_group)

    family_reports: dict[str, Any] = {}
    for family in ("REWARDS", "CAMPFIRE", "SHOP", "EVENT", "OTHER"):
        indices = [i for i, row in enumerate(rows) if group_family(rows, by_group[row["_group"]]) == family]
        if not indices:
            continue
        family_reports[family] = {
            "decisions": len({rows[i]["_group"] for i in indices}),
            "rows": len(indices),
            "arms": {
                name: (lambda ranking: {key: value for key, value in ranking["macro"].items() if key != "decisions"})(
                    decision_metrics([rows[i] for i in indices], oof[name][indices])
                ) for name in x
            },
        }
    primitive_kind_reports = {}
    for kind, selector in {
        "one_primitive": lambda row: len(json.loads(row["executedPrimitiveBits"])) == 1,
        "two_primitive_compound": lambda row: len(json.loads(row["executedPrimitiveBits"])) == 2,
    }.items():
        selected = [i for i, row in enumerate(rows) if selector(row)]
        primitive_kind_reports[kind] = {
            "decisions": len({rows[i]["_group"] for i in selected}),
            "rows": len(selected),
            "arms": {
                name: {key: value for key, value in decision_metrics([rows[i] for i in selected], oof[name][selected])["macro"].items() if key != "decisions"}
                for name in x
            },
        }

    report = {
        "experiment": "semantic_ooc_action_representation_learnability",
        "classification": "REPRESENTATIONS_COMPARABLE",
        "classification_basis": "Semantic improves macro pairwise concordance but has slightly higher aggregate selected regret than primitive; the decision-level bootstrap intervals include zero, top-or-tied gain is small, and fold/family results are mixed.",
        "constraints": {"new_labels": False, "runtime_policy_modified": False, "simulator_called": False, "production_model_exported": False},
        "corpus": corpus,
        "producer_git_sha": "0034ce8038f1a7229bc4f993a0001a72ddfd10e9",
        "evaluation": {"target": "qProduct", "target_transform": "q - mean(q within decision)", "H": 1, "futureIdentities": [0], "budgetSchedule": [10000]},
        "folds": {"key": ["sourceSeed", "decisionIdx"], "fold_count": 5, "seed": args.split_seed, "groups": fold_groups, "rows": fold_rows, "membership": {str(fold): [list(group) for group in groups if fold_by_group[group] == fold] for fold in range(5)}},
        "feature_contract": {"state": "masked richRow", "state_features": len(state_names), "semantic_action_features": len(semantic_keys), "primitive_action_features": len(primitive_keys), "semantic_keys": semantic_keys, "primitive_keys": primitive_keys},
        "model_parameters": model_params,
        "cross_validation": {"arms": cv_metrics, "folds": fold_reports},
        "semantic_minus_primitive_bootstrap": {"seed": args.bootstrap_seed, "samples": args.bootstrap_samples, **bootstrap},
        "held_out_disagreements": examples,
        "family_breakdown": family_reports,
        "primitive_trace_breakdown": primitive_kind_reports,
        "full_training_fit_diagnostic": full_fit,
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(json_safe(report), allow_nan=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "decisions": len(groups), "folds": fold_groups}, indent=2))


if __name__ == "__main__":
    main()
