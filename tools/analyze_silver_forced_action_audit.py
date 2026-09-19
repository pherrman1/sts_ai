#!/usr/bin/env python3
"""Select and analyze the frozen Silver forced-action target audit."""

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

SCHEMA = "silver_forced_action_target_v1"
TARGET = "forced_action_continuation_value_v1"
RESAMPLES = 10000
BOOTSTRAP_SEED = 20260919
HARMFUL_REGRET = 3.0
MATERIAL_REGRET_DELTA = 0.1


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select(rows, expected_sources=16, roots_per_source=2):
    by_source = defaultdict(list)
    identities = set()
    for row in rows:
        root = row.get("root_id")
        source = row.get("source_seed")
        if not isinstance(root, str) or not root or type(source) is not int or source < 0:
            raise ValueError("invalid root identity")
        if root in identities:
            raise ValueError("duplicate root")
        identities.add(root)
        by_source[source].append(row)
    if len(by_source) != expected_sources or any(len(group) < roots_per_source for group in by_source.values()):
        raise ValueError("need at least two eligible roots from exactly 16 source seeds")
    selected = []
    for source in sorted(by_source):
        selected.extend(sorted(by_source[source], key=lambda row: (
            hashlib.sha256(row["root_id"].encode()).hexdigest(), row["root_id"]))[:roots_per_source])
    return selected


def percentile(values, probability):
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def cluster_ci(values_by_source):
    sources = sorted(values_by_source)
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(RESAMPLES):
        chosen = [rng.choice(sources) for _ in sources]
        samples.append(statistics.fmean(
            value for source in chosen for value in values_by_source[source]))
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def _validate(rows, expected_roots, replicates, l_budget, j_budget, fixture,
              population="primary"):
    indexed = {}
    root_meta = {}
    global_meta = None
    for row in rows:
        required = ("population", "root_id", "source_seed", "state_hash", "root_snapshot_hash",
                    "action_fingerprint", "native_order", "estimator", "replicate", "value",
                    "continuation_budget", "simulations", "rng_identity", "stochastic",
                    "root_outcome_rng_identity", "immediate_rng_counter_before",
                    "immediate_rng_counter_after", "continuation_rng_identity",
                    "continuation_rng_counter",
                    "teacher_a_selected_action", "teacher_a_rng_identity", "teacher_a_budget",
                    "teacher_a_q", "teacher_a_visits", "master_seed", "utility_definition",
                    "evaluator_config", "executable_git_sha", "source_executable_git_sha",
                    "silver_upstream_sha", "fixture_only")
        if row.get("schema") != SCHEMA or row.get("target_definition") != TARGET \
                or row.get("population") != population \
                or any(field not in row for field in required):
            raise ValueError("incomplete schema")
        root, action, estimator, replicate = (row["root_id"], row["action_fingerprint"],
                                               row["estimator"], row["replicate"])
        budget = l_budget if estimator == "L" else j_budget if estimator == "J" else None
        if (not isinstance(root, str) or not root or not isinstance(action, str) or not action
                or budget is None or type(replicate) is not int or replicate not in range(replicates)
                or type(row["source_seed"]) is not int or row["source_seed"] < 0
                or type(row["stochastic"]) is not bool
                or type(row["value"]) not in (int, float) or not math.isfinite(row["value"])
                or row["continuation_budget"] != budget or row["simulations"] != budget
                or type(row["rng_identity"]) is not int or row["rng_identity"] <= 0
                or row["root_outcome_rng_identity"] != row["rng_identity"]
                or row["continuation_rng_identity"] != row["rng_identity"]
                or row["continuation_rng_counter"] != row["immediate_rng_counter_after"]
                or type(row["immediate_rng_counter_before"]) is not int
                or type(row["immediate_rng_counter_after"]) is not int
                or row["teacher_a_budget"] != (j_budget if fixture else 10000)
                or row["fixture_only"] is not fixture):
            raise ValueError("invalid audit row")
        key = root, action, estimator, replicate
        if key in indexed:
            raise ValueError("duplicate audit row")
        indexed[key] = row
        metadata = tuple(json.dumps(row[field], sort_keys=True) for field in (
            "source_seed", "state_hash", "root_snapshot_hash", "native_order",
            "teacher_a_selected_action", "teacher_a_rng_identity", "teacher_a_budget",
            "master_seed", "utility_definition", "evaluator_config", "executable_git_sha",
            "source_executable_git_sha", "silver_upstream_sha", "fixture_only"))
        if root_meta.setdefault(root, metadata) != metadata:
            raise ValueError("root provenance differs across observations")
        current_global = metadata[7:13]
        if global_meta is None:
            global_meta = current_global
        elif current_global != global_meta:
            raise ValueError("global provenance differs")
        if action not in row["native_order"] or row["teacher_a_selected_action"] not in row["native_order"]:
            raise ValueError("action outside native surface")
    roots = sorted(root_meta)
    if len(roots) != expected_roots:
        raise ValueError("unexpected root count")
    for root in roots:
        native = json.loads(root_meta[root][3])
        if len(native) < 2 or len(native) != len(set(native)):
            raise ValueError("invalid native action surface")
        expected = {(root, action, estimator, replicate) for action in native
                    for estimator in ("L", "J") for replicate in range(replicates)}
        if not expected.issubset(indexed):
            raise ValueError("incomplete root/action/estimator population")
        if any(key[0] == root and key not in expected for key in indexed):
            raise ValueError("extra root observation")
        for estimator in ("L", "J"):
            for replicate in range(replicates):
                identities = {indexed[root, action, estimator, replicate]["rng_identity"]
                              for action in native}
                if len(identities) != 1:
                    raise ValueError("sibling CRN identity differs")
            identities = {indexed[root, native[0], estimator, replicate]["rng_identity"]
                          for replicate in range(replicates)}
            if len(identities) != replicates:
                raise ValueError("replicate RNG identities are not independent")
        if {indexed[root, native[0], "L", r]["rng_identity"] for r in range(replicates)} & \
                {indexed[root, native[0], "J", r]["rng_identity"] for r in range(replicates)}:
            raise ValueError("L/J RNG identities overlap")
        for action in native:
            stochastic = {indexed[root, action, estimator, replicate]["stochastic"]
                          for estimator in ("L", "J") for replicate in range(replicates)}
            if len(stochastic) != 1:
                raise ValueError("stochastic classification differs across estimators")
            teacher = {(indexed[root, action, estimator, replicate]["teacher_a_q"],
                        indexed[root, action, estimator, replicate]["teacher_a_visits"])
                       for estimator in ("L", "J") for replicate in range(replicates)}
            if len(teacher) != 1:
                raise ValueError("Teacher-A action values differ")
    return indexed, roots, root_meta


def _root_measurements(indexed, roots, metadata, replicates):
    results = []
    for root in roots:
        native = json.loads(metadata[root][3])
        source = json.loads(metadata[root][0])
        means = {estimator: {action: statistics.fmean(
                    indexed[root, action, estimator, r]["value"] for r in range(replicates))
                    for action in native} for estimator in ("L", "J")}
        standard_errors = {estimator: {action: statistics.stdev(
                    indexed[root, action, estimator, r]["value"] for r in range(replicates))
                    / math.sqrt(replicates) for action in native} for estimator in ("L", "J")}
        centers = {estimator: statistics.fmean(means[estimator].values())
                   for estimator in ("L", "J")}
        a_values = {action: indexed[root, action, "L", 0]["teacher_a_q"] for action in native}
        selected_l = max(native, key=lambda action: means["L"][action])
        selected_a = indexed[root, native[0], "L", 0]["teacher_a_selected_action"]
        best_j = max(means["J"].values())
        regret_l = best_j - means["J"][selected_l]
        regret_a = best_j - means["J"][selected_a]
        pairs = [(left, right) for i, left in enumerate(native) for right in native[i + 1:]
                 if means["J"][left] != means["J"][right]]
        stochastic = {action: indexed[root, action, "L", 0]["stochastic"] for action in native}

        def concordance(values, subset):
            return (statistics.fmean((values[a] - values[b]) *
                    (means["J"][a] - means["J"][b]) > 0 for a, b in subset)
                    if subset else None)

        stochastic_pairs = [(a, b) for a, b in pairs if stochastic[a] or stochastic[b]]
        deterministic_pairs = [(a, b) for a, b in pairs if not stochastic[a] and not stochastic[b]]
        results.append({"root_id": root, "source_seed": source, "actions": len(native),
            "has_stochastic_action": any(stochastic.values()), "l_selected": selected_l,
            "a_selected": selected_a, "j_regret_l": regret_l, "j_regret_a": regret_a,
            "regret_delta_l_minus_a": regret_l - regret_a,
            "pairwise_concordance_l": concordance(means["L"], pairs),
            "pairwise_concordance_a": concordance(a_values, pairs),
            "stochastic_pairwise_l": concordance(means["L"], stochastic_pairs),
            "stochastic_pairwise_a": concordance(a_values, stochastic_pairs),
            "stochastic_pairs": len(stochastic_pairs),
            "deterministic_pairwise_l": concordance(means["L"], deterministic_pairs),
            "deterministic_pairwise_a": concordance(a_values, deterministic_pairs),
            "deterministic_pairs": len(deterministic_pairs),
            "action_targets": [{"action_fingerprint": action,
                "stochastic": stochastic[action], "l_mean": means["L"][action],
                "l_standard_error": standard_errors["L"][action],
                "l_centered_advantage": means["L"][action] - centers["L"],
                "j_mean": means["J"][action], "j_standard_error": standard_errors["J"][action],
                "j_centered_advantage": means["J"][action] - centers["J"],
                "teacher_a_q": a_values[action]} for action in native],
            "pairwise_targets": [{"left": left, "right": right,
                "involves_stochastic": stochastic[left] or stochastic[right],
                "l_margin": means["L"][left] - means["L"][right],
                "j_margin": means["J"][left] - means["J"][right],
                "teacher_a_margin": a_values[left] - a_values[right]}
                for i, left in enumerate(native) for right in native[i + 1:]]})
    for result in results:
        result["pairwise_concordance_delta"] = ((result["pairwise_concordance_l"] or 0.0)
                                                - (result["pairwise_concordance_a"] or 0.0))
    return results


def analyze(rows, expected_roots=32, replicates=8, l_budget=5000, j_budget=10000,
            fixture=False):
    indexed, roots, metadata = _validate(rows, expected_roots, replicates, l_budget, j_budget, fixture)
    root_results = _root_measurements(indexed, roots, metadata, replicates)
    regret_deltas = defaultdict(list)
    pairwise_deltas = defaultdict(list)
    stochastic_deltas = defaultdict(list)
    stochastic_pair_deltas = []
    deterministic_pair_deltas = []
    for row in root_results:
        source = row["source_seed"]
        regret_deltas[source].append(row["regret_delta_l_minus_a"])
        pairwise_deltas[source].append(row["pairwise_concordance_delta"])
        if row["has_stochastic_action"]:
            stochastic_deltas[source].append(row["regret_delta_l_minus_a"])
        if row["stochastic_pairwise_l"] is not None:
            stochastic_pair_deltas.append(row["stochastic_pairwise_l"] - row["stochastic_pairwise_a"])
        if row["deterministic_pairwise_l"] is not None:
            deterministic_pair_deltas.append(row["deterministic_pairwise_l"] - row["deterministic_pairwise_a"])
    regret_values = [row["regret_delta_l_minus_a"] for row in root_results]
    pair_values = [row["pairwise_concordance_delta"] for row in root_results]
    regret_ci = cluster_ci(regret_deltas)
    pair_ci = cluster_ci(pairwise_deltas)
    regrets_l = [row["j_regret_l"] for row in root_results]
    regrets_a = [row["j_regret_a"] for row in root_results]
    new_harmful = [row["root_id"] for row in root_results
                   if row["j_regret_l"] >= HARMFUL_REGRET and row["j_regret_a"] < HARMFUL_REGRET]
    materially_worse = [row["root_id"] for row in root_results
                        if row["regret_delta_l_minus_a"] >= MATERIAL_REGRET_DELTA]
    stochastic_values = [value for values in stochastic_deltas.values() for value in values]
    stochastic_coverage = bool(stochastic_values and stochastic_pair_deltas)
    gates = {"regret_ci_below_zero": regret_ci[1] < 0,
             "pairwise_ci_above_zero": pair_ci[0] > 0,
             "no_new_harmful_regret": not new_harmful,
             "max_regret_not_worse": max(regrets_l) <= max(regrets_a),
             "stochastic_coverage_present": stochastic_coverage,
             "stochastic_not_worse": stochastic_coverage and statistics.fmean(stochastic_values) <= 0,
             "stochastic_pairwise_not_worse": stochastic_coverage
                                                and statistics.fmean(stochastic_pair_deltas) >= 0}
    noncoverage_gates = {key: value for key, value in gates.items()
                         if key not in ("stochastic_coverage_present", "stochastic_not_worse",
                                        "stochastic_pairwise_not_worse")}
    if all(gates.values()):
        classification = "FORCED_ACTION_TARGET_PASS"
    elif not stochastic_coverage and all(noncoverage_gates.values()):
        classification = "FORCED_ACTION_TARGET_DETERMINISTIC_ONLY"
    else:
        classification = "FORCED_ACTION_TARGET_FAIL"
    return {"schema": "silver_forced_action_analysis_v1", "classification": classification,
        "roots": len(roots), "source_seeds": len(regret_deltas), "replicates": replicates,
        "l_budget": l_budget, "j_budget": j_budget, "bootstrap_resamples": RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED, "harmful_regret_threshold": HARMFUL_REGRET,
        "material_regret_delta": MATERIAL_REGRET_DELTA,
        "mean_regret_delta_l_minus_a": statistics.fmean(regret_values),
        "regret_delta_cluster_ci95": regret_ci,
        "mean_pairwise_concordance_delta": statistics.fmean(pair_values),
        "pairwise_delta_cluster_ci95": pair_ci,
        "tail": {"l_max": max(regrets_l), "a_max": max(regrets_a),
                 "l_upper_decile": percentile(regrets_l, .9),
                 "a_upper_decile": percentile(regrets_a, .9),
                 "new_harmful_roots": new_harmful,
                 "materially_worse_roots": materially_worse},
        "stochastic_roots": len(stochastic_values),
        "mean_stochastic_regret_delta": statistics.fmean(stochastic_values) if stochastic_values else None,
        "stochastic_pairwise_comparisons": len(stochastic_pair_deltas),
        "mean_stochastic_pairwise_delta": (statistics.fmean(stochastic_pair_deltas)
                                             if stochastic_pair_deltas else None),
        "deterministic_pairwise_comparisons": len(deterministic_pair_deltas),
        "mean_deterministic_pairwise_delta": (statistics.fmean(deterministic_pair_deltas)
                                                if deterministic_pair_deltas else None),
        "gates": gates, "root_results": root_results}


def analyze_historical(rows, replicates=8, l_budget=5000, j_budget=10000):
    root_count = len({row.get("root_id") for row in rows})
    indexed, roots, metadata = _validate(rows, root_count, replicates, l_budget, j_budget,
                                         False, population="historical_regression")
    results = _root_measurements(indexed, roots, metadata, replicates)
    misranked = [row["root_id"] for row in results if row["j_regret_l"] > 0]
    worse = [row["root_id"] for row in results if row["regret_delta_l_minus_a"] > 0]
    return {"schema": "silver_forced_action_historical_regression_v1",
        "classification": ("HISTORICAL_REGRESSION_PASS" if not misranked and not worse
                           else "HISTORICAL_REGRESSION_FAIL"),
        "roots": len(results), "misranked_roots": misranked,
        "worse_than_teacher_a_roots": worse, "root_results": results}


def load(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    selection = sub.add_parser("select")
    selection.add_argument("capture")
    selection.add_argument("output")
    analysis = sub.add_parser("analyze")
    analysis.add_argument("input")
    analysis.add_argument("output")
    analysis.add_argument("--fixture", action="store_true")
    regression = sub.add_parser("regression")
    regression.add_argument("input")
    regression.add_argument("output")
    args = parser.parse_args()
    if args.command == "select":
        output = Path(args.output)
        manifest = Path(str(output) + ".manifest.json")
        if output.exists() or manifest.exists():
            raise SystemExit("refusing existing selection output")
        rows = select(load(args.capture))
        output.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
        manifest.write_text(json.dumps({"schema": "silver_forced_action_selection_v1",
            "rule": "sha256(root_id), first two eligible roots per source seed",
            "source_capture_sha256": sha256(args.capture), "selected_sha256": sha256(output),
            "source_seeds": sorted({row["source_seed"] for row in rows}),
            "selected_root_ids": [row["root_id"] for row in rows]}, indent=2) + "\n")
    elif args.command == "analyze":
        output = Path(args.output)
        if output.exists():
            raise SystemExit("refusing existing analysis output")
        kwargs = ({"expected_roots": 1, "replicates": 2, "l_budget": 8,
                   "j_budget": 16, "fixture": True} if args.fixture else {})
        output.write_text(json.dumps(analyze(load(args.input), **kwargs), indent=2) + "\n")
    else:
        output = Path(args.output)
        if output.exists():
            raise SystemExit("refusing existing regression output")
        output.write_text(json.dumps(analyze_historical(load(args.input)), indent=2) + "\n")


if __name__ == "__main__":
    main()
