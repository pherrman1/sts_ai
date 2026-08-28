#!/usr/bin/env python3
"""Tie-safe offline candidate-retention audit for Silver root actions.

This is deliberately an analysis boundary.  It neither changes Silver search
nor trains a model: it scores the frozen parent-policy model once against the
stored 25k-B anchors and evaluates predeclared candidate-set rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import xgboost as xgb


DEFAULT_SEED = 20260828
DEFAULT_REPLICATES = 5000
TOP_RULES = ("top_1", "top_2", "top_3", "top_half")
TEACHER_BUDGETS = (1000, 10000, 25000)
ACTION_TYPES = {
    0: "INVALID", 1: "CARD", 2: "POTION", 3: "SINGLE_CARD_SELECT",
    4: "MULTI_CARD_SELECT", 5: "END_TURN",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"silver-action-pruning audit: {message}")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=float), q))


def action_type(fingerprint: str) -> str:
    prefix = "sa/t="
    if not fingerprint.startswith(prefix):
        return "UNKNOWN"
    try:
        value = int(fingerprint[len(prefix):].split("/", 1)[0])
    except ValueError:
        return "UNKNOWN"
    return ACTION_TYPES.get(value, f"UNKNOWN_{value}")


def load_features(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as stream:
        try:
            header = json.loads(next(stream))
        except StopIteration:
            fail("features file is empty")
        if header.get("feature_schema") != "silver_parent_policy_features_v1":
            fail("incompatible feature schema")
        names = header.get("feature_names")
        if not isinstance(names, list) or header.get("feature_count") != len(names):
            fail("feature header width mismatch")
        for number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            row = json.loads(line)
            group, fingerprint = row.get("group_id"), row.get("action_fingerprint")
            if not isinstance(group, str) or not isinstance(fingerprint, str):
                fail(f"feature row has no action identity at line {number}")
            key = (group, fingerprint)
            if key in seen:
                fail(f"duplicate feature action identity {group}/{fingerprint}")
            seen.add(key)
            if len(row.get("features", [])) != len(names):
                fail(f"feature width mismatch at line {number}")
            if not isinstance(row.get("silver_order"), int):
                fail(f"feature row has no deterministic Silver order at line {number}")
            groups[group].append(row)
    for group, rows in groups.items():
        rows.sort(key=lambda row: row["silver_order"])
        if [row["silver_order"] for row in rows] != list(range(len(rows))):
            fail(f"non-contiguous Silver order for {group}")
    return header, dict(groups)


def parent_actions(row: dict[str, Any]) -> dict[str, dict[str, float]] | None:
    if not row.get("teacher_valid", False):
        return None
    actions: dict[str, dict[str, float]] = {}
    for action in row.get("root_actions", []):
        if not action.get("leaf_root_q_valid", False):
            return None
        fingerprint = action.get("action_fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in actions:
            return None
        try:
            actions[fingerprint] = {
                "q": float(action["original_root_corrected_q"]),
                "visits": float(action["visits"]),
            }
        except (KeyError, TypeError, ValueError):
            return None
    if len(actions) != row.get("root_action_count") or not actions:
        return None
    return actions


def load_parent_labels(path: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    labels: dict[tuple[str, int, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1":
                fail(f"incompatible relabel schema at line {number}")
            if row.get("state_kind") != "parent":
                continue
            key = (row.get("group_id"), row.get("budget"), row.get("replicate"))
            if not isinstance(key[0], str) or not isinstance(key[1], int) or key[2] not in {"A", "B"}:
                fail(f"malformed parent identity at line {number}")
            if key in labels:
                fail(f"duplicate parent label {key}")
            labels[key] = row
    return labels


def feature_identity(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        encoded = json.dumps(row["features"], separators=(",", ":"), allow_nan=False)
        groups[hashlib.sha256(encoded.encode()).hexdigest()].append(row["action_fingerprint"])
    return {identity: fingerprints for identity, fingerprints in groups.items() if len(fingerprints) > 1}


def build_anchors(features: dict[str, list[dict[str, Any]]],
                  labels: dict[tuple[str, int, str], dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    anchors = sorted(group for group, budget, replicate in labels
                     if budget == 25000 and replicate == "B")
    result: dict[str, list[dict[str, Any]]] = {}
    exclusions: Counter[str] = Counter()
    for group in anchors:
        reference = parent_actions(labels[(group, 25000, "B")])
        if reference is None:
            exclusions["invalid_25k_b_reference"] += 1
            continue
        rows = features.get(group)
        if rows is None:
            exclusions["missing_complete_features"] += 1
            continue
        fingerprints = {row["action_fingerprint"] for row in rows}
        if fingerprints != set(reference):
            exclusions["feature_reference_action_set_mismatch"] += 1
            continue
        sources: dict[str, dict[str, float]] = {}
        source_error = None
        for budget in TEACHER_BUDGETS:
            source = parent_actions(labels.get((group, budget, "A"), {}))
            if source is None or set(source) != fingerprints:
                source_error = f"teacher_{budget}_a_action_set_mismatch"
                break
            sources[f"teacher_q_{budget}_a"] = {fp: source[fp]["q"] for fp in fingerprints}
            sources[f"teacher_visits_{budget}_a"] = {fp: source[fp]["visits"] for fp in fingerprints}
        if source_error:
            exclusions[source_error] += 1
            continue
        attached = []
        for row in rows:
            fingerprint = row["action_fingerprint"]
            attached.append({**row, "reference_q": reference[fingerprint]["q"],
                             "scores": sources})
        result[group] = attached
    return result, dict(sorted(exclusions.items()))


def add_model_scores(groups: dict[str, list[dict[str, Any]]], header: dict[str, Any], model_path: Path) -> None:
    model = xgb.Booster()
    model.load_model(model_path)
    names = header["feature_names"]
    flat = [row for group in sorted(groups) for row in groups[group]]
    matrix = np.asarray([row["features"] for row in flat], dtype=np.float32)
    scores = model.predict(xgb.DMatrix(matrix, feature_names=names))
    if len(scores) != len(flat):
        fail("model returned an unexpected number of scores")
    for row, score in zip(flat, scores, strict=True):
        if not math.isfinite(float(score)):
            fail("model produced a non-finite score")
        row["model_score"] = float(score)


def rank_scores(rows: list[dict[str, Any]], source: str) -> list[float]:
    if source == "current_silver_order":
        return [-float(row["silver_order"]) for row in rows]
    if source == "frozen_model":
        return [float(row["model_score"]) for row in rows]
    return [float(row["scores"][source][row["action_fingerprint"]]) for row in rows]


def rule_size(rule: str, actions: int) -> int:
    if rule == "top_1":
        return 1
    if rule == "top_2":
        return min(2, actions)
    if rule == "top_3":
        return min(3, actions)
    if rule == "top_half":
        return math.ceil(actions / 2)
    raise ValueError(f"unknown candidate rule {rule}")


def candidate_indices(scores: list[float], rule: str) -> tuple[set[int], list[list[int]]]:
    """Return all actions through the boundary score, preserving exact ties."""
    if not scores:
        fail("empty candidate score vector")
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    cutoff = scores[order[rule_size(rule, len(scores)) - 1]]
    retained = {index for index, score in enumerate(scores) if score >= cutoff}
    tie_groups: list[list[int]] = []
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and scores[order[end]] == scores[order[position]]:
            end += 1
        if end - position > 1:
            tie_groups.append(order[position:end])
        position = end
    return retained, tie_groups


def one_parent(rows: list[dict[str, Any]], source: str, rule: str) -> dict[str, Any]:
    scores = rank_scores(rows, source)
    retained, tie_groups = candidate_indices(scores, rule)
    truth = [float(row["reference_q"]) for row in rows]
    best = max(truth)
    best_indices = {index for index, q in enumerate(truth) if q == best}
    retained_best = max(truth[index] for index in retained)
    boundary_score = min(scores[index] for index in retained)
    boundary_group = sorted(index for index, score in enumerate(scores) if score == boundary_score)
    return {
        "retained": sorted(retained), "best_retained": bool(best_indices & retained),
        "retained_fraction": len(retained) / len(rows), "regret": best - retained_best,
        "boundary_tie_size": len(boundary_group), "boundary_tie_group": boundary_group,
        "score_tie_groups": tie_groups,
    }


def summarize(rows_by_group: dict[str, list[dict[str, Any]]], source: str, rule: str,
              ids: Iterable[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    selected = sorted(ids)
    parents = {group: one_parent(rows_by_group[group], source, rule) for group in selected}
    regrets = [parent["regret"] for parent in parents.values()]
    retained_actions = sum(len(parent["retained"]) for parent in parents.values())
    actions = sum(len(rows_by_group[group]) for group in selected)
    return {
        "parents": len(selected),
        "actions": actions,
        "best_action_retention": statistics.fmean(parent["best_retained"] for parent in parents.values()),
        "retained_action_fraction": retained_actions / actions if actions else 0.0,
        "best_retained_regret": {
            "mean": statistics.fmean(regrets) if regrets else 0.0,
            "median": statistics.median(regrets) if regrets else 0.0,
            "p90": percentile(regrets, .90), "p95": percentile(regrets, .95),
            "max": max(regrets, default=0.0),
        },
        "regret_exclusion_rate": {
            ">=0.25": statistics.fmean(regret >= .25 for regret in regrets) if regrets else 0.0,
            ">=1": statistics.fmean(regret >= 1 for regret in regrets) if regrets else 0.0,
            ">=3": statistics.fmean(regret >= 3 for regret in regrets) if regrets else 0.0,
        },
        "boundary_tie_parents": sum(parent["boundary_tie_size"] > 1 for parent in parents.values()),
        "mean_boundary_tie_size": statistics.fmean(parent["boundary_tie_size"] for parent in parents.values()),
    }, parents


def bootstrap_delta(candidate: dict[str, dict[str, Any]], control: dict[str, dict[str, Any]],
                    replicates: int, seed: int) -> dict[str, Any]:
    ids = sorted(candidate)
    if ids != sorted(control):
        fail("bootstrap candidate/control parent identity mismatch")
    rng = np.random.default_rng(seed)
    retention, regret, fraction = [], [], []
    for _ in range(replicates):
        sample = rng.choice(ids, len(ids), replace=True)
        candidate_rows = [candidate[group] for group in sample]
        control_rows = [control[group] for group in sample]
        retention.append(statistics.fmean(row["best_retained"] for row in candidate_rows)
                         - statistics.fmean(row["best_retained"] for row in control_rows))
        regret.append(statistics.fmean(row["regret"] for row in control_rows)
                      - statistics.fmean(row["regret"] for row in candidate_rows))
        fraction.append(statistics.fmean(row["retained_fraction"] for row in control_rows)
                        - statistics.fmean(row["retained_fraction"] for row in candidate_rows))
    def summary(values: list[float]) -> dict[str, float]:
        return {"p05": percentile(values, .05), "p50": percentile(values, .50),
                "p95": percentile(values, .95),
                "probability_positive": statistics.fmean(value > 0 for value in values)}
    return {"replicates": replicates, "seed": seed,
            "candidate_minus_current_order_best_retention": summary(retention),
            "current_order_minus_candidate_mean_regret": summary(regret),
            "current_order_minus_candidate_parent_retained_fraction": summary(fraction)}


def slices(groups: dict[str, list[dict[str, Any]]], source: str, rule: str,
           population: list[str]) -> dict[str, Any]:
    dimensions: dict[str, dict[str, list[str]]] = {
        "act": defaultdict(list), "encounter_category": defaultdict(list),
        "action_count": defaultdict(list), "best_action_type": defaultdict(list),
    }
    for group in population:
        rows = groups[group]
        dimensions["act"][str(rows[0]["act"])].append(group)
        dimensions["encounter_category"][str(rows[0]["encounter_category"])].append(group)
        dimensions["action_count"][str(len(rows))].append(group)
        best = max(float(row["reference_q"]) for row in rows)
        kinds = sorted({action_type(row["action_fingerprint"]) for row in rows if row["reference_q"] == best})
        dimensions["best_action_type"]["|".join(kinds)].append(group)
    result: dict[str, Any] = {}
    for dimension, buckets in dimensions.items():
        result[dimension] = {}
        for name, ids in sorted(buckets.items()):
            result[dimension][name] = summarize(groups, source, rule, ids)[0]
    return result


def q_visit_agreement(groups: dict[str, list[dict[str, Any]]], population: list[str]) -> dict[str, Any]:
    result = {}
    for budget in TEACHER_BUDGETS:
        overlap = all_q_retained = 0
        for group in population:
            rows = groups[group]
            q = rank_scores(rows, f"teacher_q_{budget}_a")
            visits = rank_scores(rows, f"teacher_visits_{budget}_a")
            q_best = {index for index, value in enumerate(q) if value == max(q)}
            visit_best = {index for index, value in enumerate(visits) if value == max(visits)}
            overlap += bool(q_best & visit_best)
            all_q_retained += q_best <= visit_best
        result[str(budget)] = {
            "parents": len(population),
            "any_max_q_max_visit_overlap": overlap / len(population),
            "all_max_q_are_max_visit": all_q_retained / len(population),
        }
    return result


def tie_audit(groups: dict[str, list[dict[str, Any]]], population: list[str]) -> dict[str, Any]:
    feature_groups = []
    for group in population:
        for identity, fingerprints in feature_identity(groups[group]).items():
            feature_groups.append({"group_id": group, "identity": identity, "actions": fingerprints})
    model_groups = []
    for group in population:
        rows = groups[group]
        scores = rank_scores(rows, "frozen_model")
        by_score: dict[str, list[str]] = defaultdict(list)
        for row, score in zip(rows, scores, strict=True):
            by_score[float(score).hex()].append(row["action_fingerprint"])
        for score, fingerprints in sorted(by_score.items()):
            if len(fingerprints) > 1:
                model_groups.append({"group_id": group, "identity": f"{group}:model:{score}",
                                     "score_hex": score, "actions": fingerprints})
    return {
        "feature_identical_groups": feature_groups,
        "feature_identical_group_count": len(feature_groups),
        "model_tied_groups": model_groups,
        "model_tied_group_count": len(model_groups),
        "rule": "all tied actions at a candidate boundary are retained; ties are never split by stable order",
    }


def source_names() -> tuple[str, ...]:
    return ("current_silver_order", "frozen_model",
            *(f"teacher_q_{budget}_a" for budget in TEACHER_BUDGETS),
            *(f"teacher_visits_{budget}_a" for budget in TEACHER_BUDGETS))


def run_audit(features_path: Path, relabels_path: Path, model_path: Path, output: Path,
              selected_corpus_path: Path, manifest_path: Path,
              replicates: int, seed: int) -> dict[str, Any]:
    if replicates <= 0:
        fail("bootstrap replicate count must be positive")
    header, features = load_features(features_path)
    labels = load_parent_labels(relabels_path)
    groups, exclusions = build_anchors(features, labels)
    if len(groups) != 93:
        fail(f"expected 93 complete independent 25k-B anchors, found {len(groups)}")
    add_model_scores(groups, header, model_path)
    primary = [group for group in sorted(groups) if len(groups[group]) > 1]
    secondary = [group for group in sorted(groups) if len(groups[group]) == 1]
    if len(primary) != 63 or len(secondary) != 30:
        fail(f"expected 63 multi-action and 30 single-action anchors, found {len(primary)}/{len(secondary)}")
    populations = {"primary_multi_action": primary, "secondary_single_action": secondary,
                   "all_anchors_integrity": sorted(groups)}
    report: dict[str, Any] = {
        "schema": "silver_action_pruning_retention_v1",
        "decision": "PHASE_1_COMPLETE_PHASE_2_AUTHORIZED",
        "inputs": {
            "relabels_sha256": sha256(relabels_path),
            "selected_corpus_sha256": sha256(selected_corpus_path),
            "manifest_sha256": sha256(manifest_path), "features_sha256": sha256(features_path),
            "model_sha256": sha256(model_path),
        },
        "rules": {"top_1": "top 1 score group", "top_2": "top 2 score positions plus boundary ties",
                  "top_3": "top 3 score positions plus boundary ties",
                  "top_half": "ceil(action_count / 2) score positions plus boundary ties"},
        "primary_population": {"definition": "25k-B anchors with root_action_count > 1",
                               "parents": len(primary), "actions": sum(len(groups[group]) for group in primary)},
        "secondary_population": {"definition": "25k-B anchors with root_action_count == 1; excluded from candidate claims",
                                 "parents": len(secondary), "actions": len(secondary)},
        "exclusions": exclusions,
        "tie_audit": tie_audit(groups, primary),
        "max_q_vs_max_visit_agreement": q_visit_agreement(groups, primary),
        "ranking_sources": list(source_names()),
        "metrics": {},
    }
    controls: dict[str, dict[str, dict[str, Any]]] = {}
    for population_name, ids in populations.items():
        controls[population_name] = {}
        for rule in TOP_RULES:
            _, parent = summarize(groups, "current_silver_order", rule, ids)
            controls[population_name][rule] = parent
    for source in source_names():
        source_report: dict[str, Any] = {}
        for rule in TOP_RULES:
            by_population: dict[str, Any] = {}
            for population_name, ids in populations.items():
                summary, parent = summarize(groups, source, rule, ids)
                item: dict[str, Any] = {"summary": summary}
                if population_name == "primary_multi_action":
                    item["slices"] = slices(groups, source, rule, ids)
                    item["bootstrap_vs_current_order"] = bootstrap_delta(
                        parent, controls[population_name][rule], replicates, seed)
                by_population[population_name] = item
            source_report[rule] = by_population
        report["metrics"][source] = source_report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> None:
    scores = [3.0, 2.0, 2.0, 1.0]
    retained, ties = candidate_indices(scores, "top_2")
    assert retained == {0, 1, 2} and ties == [[1, 2]]
    rows = [
        {"silver_order": 0, "model_score": 3.0, "reference_q": 0.0,
         "action_fingerprint": "sa/t=1/x=a", "scores": {}},
        {"silver_order": 1, "model_score": 2.0, "reference_q": 3.0,
         "action_fingerprint": "sa/t=1/x=b", "scores": {}},
        {"silver_order": 2, "model_score": 2.0, "reference_q": 2.0,
         "action_fingerprint": "sa/t=5/x=c", "scores": {}},
    ]
    outcome = one_parent(rows, "frozen_model", "top_1")
    assert not outcome["best_retained"] and outcome["regret"] == 3.0
    assert outcome["retained"] == [0]
    outcome = one_parent(rows, "frozen_model", "top_2")
    assert outcome["best_retained"] and outcome["retained"] == [0, 1, 2]
    candidate = {"a": {"best_retained": True, "regret": 0.0, "retained_fraction": .5},
                 "b": {"best_retained": False, "regret": 1.0, "retained_fraction": .5}}
    control = {"a": {"best_retained": False, "regret": 1.0, "retained_fraction": 1.0},
               "b": {"best_retained": False, "regret": 2.0, "retained_fraction": 1.0}}
    assert bootstrap_delta(candidate, control, 25, 7) == bootstrap_delta(candidate, control, 25, 7)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path, nargs="?")
    parser.add_argument("relabels", type=Path, nargs="?")
    parser.add_argument("model", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--bootstrap-replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--selected-corpus", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("silver-action-pruning analyzer self-test: PASS")
        return
    if None in (args.features, args.relabels, args.model, args.output,
                args.selected_corpus, args.manifest):
        parser.error("features, relabels, model, output, --selected-corpus, and --manifest are required unless --self-test is used")
    report = run_audit(args.features, args.relabels, args.model, args.output,
                       args.selected_corpus, args.manifest,
                       args.bootstrap_replicates, args.bootstrap_seed)
    print("silver-action-pruning audit: PASS "
          f"primary={report['primary_population']['parents']} output={args.output}")


if __name__ == "__main__":
    main()
