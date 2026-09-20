#!/usr/bin/env python3
"""Evaluate the frozen MLP_FLAT_V1 scorer on a locked source-seed cohort.

This is deliberately separate from ``learn_silver_prefix_scorer.py``.  The
original tool remains the PR #258 parity oracle; this driver reuses its feature
and model definitions while making the source-seed partition explicit:

    base20 -> original PR #258 training pool
    expansion40 -> fresh training pool
    locked40 -> never used by fitting or normalization

The driver is offline.  It never calls Silver or either teacher and it never
uses locked q32 values until after a prefix has been selected from predictions.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.stats import pearsonr, spearmanr
import torch
from torch import nn


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "learn_silver_prefix_scorer", ROOT / "tools/learn_silver_prefix_scorer.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen PR #258 scorer module")
FROZEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FROZEN)

REPLICATES = FROZEN.REPLICATES
TRAINING_SEED = FROZEN.TRAINING_SEED
BOOTSTRAP_SEED = FROZEN.BOOTSTRAP_SEED
PARAMETERS = 75809


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def load_packet(packet: dict, role: str) -> tuple[list[dict], dict]:
    """Load one packet without applying the old 247-leaf cardinality checks."""
    paths = {key: Path(packet[key]) for key in ("prefix", "corpus", "baseline", "teachers", "manifest")}
    for key, path in paths.items():
        if not path.is_file():
            raise SystemExit(f"{role}: missing {key} artifact: {path}")

    leaves = {}
    for row in jsonl(paths["corpus"]):
        leaf = row["leaf_snapshot_id"]
        if leaf in leaves:
            raise SystemExit(f"{role}: duplicate corpus leaf {leaf}")
        leaves[leaf] = row

    baseline_rows = defaultdict(list)
    for row in jsonl(paths["baseline"]):
        if row.get("accepted"):
            baseline_rows[row["leaf_snapshot_id"]].append(row)
    baseline = {}
    for leaf, rows in baseline_rows.items():
        rows = sorted(rows, key=lambda row: int(row["replicate"]))
        if len(rows) != REPLICATES or {int(row["replicate"]) for row in rows} != set(range(REPLICATES)):
            continue
        baseline[leaf] = {
            "value": statistics.fmean(row["original_root_corrected_utility"] for row in rows),
            "source_seed": str(rows[0]["source_seed"]),
        }

    teachers = defaultdict(dict)
    for row in jsonl(paths["teachers"]):
        if row.get("state_kind") == "leaf" and row.get("teacher_valid") and row.get("selected_q_valid"):
            teachers[row["leaf_snapshot_id"]][str(row["replicate"])] = row["original_root_corrected_teacher_value"]
    teachers = {leaf: values for leaf, values in teachers.items() if "A" in values and "B" in values}

    values = defaultdict(dict)
    metadata = {}
    for row in jsonl(paths["prefix"]):
        if not row.get("accepted") or int(row["requested_prefix_length"]) > 2:
            continue
        key = row["requested_prefix_key"]
        leaf = row["leaf_snapshot_id"]
        rep = int(row["replicate"])
        identity = (leaf, key)
        if rep in values[identity]:
            raise SystemExit(f"{role}: duplicate candidate replicate {leaf}/{key}/{rep}")
        values[identity][rep] = row["original_root_corrected_utility"]
        old = metadata.setdefault(identity, row)
        if old["requested_prefix_fingerprints"] != row["requested_prefix_fingerprints"]:
            raise SystemExit(f"{role}: candidate key metadata mismatch: {identity}")

    rows = []
    state_names = None
    for (leaf, key), samples in sorted(values.items()):
        if set(samples) != set(range(REPLICATES)):
            raise SystemExit(f"{role}: candidate lacks all 32 replicates: {leaf}/{key}")
        corpus = leaves.get(leaf)
        if corpus is None or leaf not in baseline or leaf not in teachers:
            continue
        fingerprints = metadata[(leaf, key)]["requested_prefix_fingerprints"]
        if len(fingerprints) not in (1, 2):
            raise SystemExit(f"{role}: unsupported prefix length {len(fingerprints)}")
        state = corpus["leaf_state"]["state"]
        state_vec, names = FROZEN.state_features(state)
        if state_names is None:
            state_names = names
        elif state_names != names:
            raise SystemExit(f"{role}: feature schema mismatch at {leaf}/{key}")
        actions = [FROZEN.parse_action(fp, state) for fp in fingerprints]
        q32 = statistics.fmean(samples.values())
        rows.append({
            "group_id": corpus["group_id"], "source_seed": str(corpus["run_seed"]),
            "leaf_snapshot_id": leaf, "prefix_key": key,
            "prefix_length": len(fingerprints), "prefix_fingerprints": fingerprints,
            "state_features": state_vec, "action1": actions[0],
            "action2": actions[1] if len(actions) == 2 else FROZEN.none_action(),
            "q32": q32, "leaf_baseline32": baseline[leaf]["value"],
            "centered_q": q32 - baseline[leaf]["value"],
            "teacher_a": teachers[leaf]["A"], "teacher_b": teachers[leaf]["B"],
        })

    by_leaf = defaultdict(dict)
    for row in rows:
        by_leaf[row["leaf_snapshot_id"]][row["prefix_key"]] = row
        if row["prefix_length"] == 2:
            parent = json.dumps(row["prefix_fingerprints"][:1], separators=(",", ":"))
            if parent not in by_leaf[row["leaf_snapshot_id"]]:
                # The parent may sort later; check after the complete load too.
                pass
    for leaf, candidates in by_leaf.items():
        for row in candidates.values():
            if row["prefix_length"] == 2:
                parent = json.dumps(row["prefix_fingerprints"][:1], separators=(",", ":"))
                if parent not in candidates:
                    raise SystemExit(f"{role}: length-2 candidate lacks length-1 parent: {row['prefix_key']}")
    groups = defaultdict(set)
    for row in rows:
        groups[row["group_id"]].add(row["source_seed"])
    if any(len(seeds) != 1 for seeds in groups.values()):
        raise SystemExit(f"{role}: sibling group spans multiple source seeds")
    if not rows:
        raise SystemExit(f"{role}: no usable candidate rows")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    return rows, {"role": role, "manifest": manifest, "paths": {k: str(v) for k, v in paths.items()},
                  "sha256": {k: sha256(v) for k, v in paths.items()},
                  "state_feature_names": state_names}


def validate_partition(config: dict, packets: dict[str, dict]) -> dict:
    roles = config["roles"]
    role_sources = {}
    for role, spec in roles.items():
        source_ids = {str(value) for value in spec["source_seeds"]}
        if len(source_ids) != len(spec["source_seeds"]):
            raise SystemExit(f"{role}: duplicate source seed in role manifest")
        role_sources[role] = source_ids
        actual = {row["source_seed"] for row in packets[role]["rows"]}
        missing = sorted(source_ids - actual)
        unexpected = sorted(actual - source_ids)
        if missing or unexpected:
            raise SystemExit(f"{role}: source seed mismatch missing={missing[:5]} unexpected={unexpected[:5]}")
    all_sources = set()
    for role, sources in role_sources.items():
        overlap = sorted(all_sources & sources)
        if overlap:
            raise SystemExit(f"source-role overlap at {role}: {overlap[:8]}")
        all_sources |= sources
    if len(role_sources["base_training_pool"]) != 20:
        raise SystemExit("base_training_pool must contain exactly 20 source seeds")
    if len(role_sources["expansion_training_pool"]) != 40:
        raise SystemExit("expansion_training_pool must contain exactly 40 source seeds")
    if len(role_sources["locked_validation"]) != 40:
        raise SystemExit("locked_validation must contain exactly 40 source seeds")
    return {role: sorted(sources) for role, sources in role_sources.items()}


def rows_for_sources(rows: list[dict], sources: set[str]) -> list[dict]:
    result = [row for row in rows if row["source_seed"] in sources]
    if {row["source_seed"] for row in result} != sources:
        raise SystemExit("training arm is missing a designated source seed")
    return result


def fit_flat(train: list[dict], test: list[dict], seed: int) -> tuple[np.ndarray, dict]:
    numeric_train = np.stack([FROZEN.mlp_numeric(row) for row in train])
    numeric_test = np.stack([FROZEN.mlp_numeric(row) for row in test])
    numeric_train, numeric_test, (mean, scale) = FROZEN.standardize(numeric_train, numeric_test)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    model = FROZEN.FlatMLP(numeric_train.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    x = torch.from_numpy(numeric_train)
    cards = torch.from_numpy(FROZEN.card_ids(train))
    y = torch.tensor([row["centered_q"] for row in train], dtype=torch.float32)
    for _ in range(80):
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.huber_loss(model(x, cards), y)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        prediction = model(torch.from_numpy(numeric_test), torch.from_numpy(FROZEN.card_ids(test))).numpy()
    params = sum(parameter.numel() for parameter in model.parameters())
    if params != PARAMETERS:
        raise SystemExit(f"frozen MLP parameter count changed: {params} != {PARAMETERS}")
    return prediction, {"parameters": params, "training_seed": seed,
                        "normalization_source": sorted({row["source_seed"] for row in train}),
                        "feature_width": int(numeric_train.shape[1]),
                        "epochs": 80, "optimizer": "Adam(lr=1e-3)", "loss": "Huber"}


def choose(candidates: list[dict], arm: str) -> dict:
    return FROZEN.choose_predicted(candidates, arm)


def select_rows(rows: list[dict], arm: str) -> list[dict]:
    """Select solely from prediction fields; q32 is read only for diagnostics."""
    by_leaf = defaultdict(list)
    for row in rows:
        by_leaf[row["leaf_snapshot_id"]].append(row)
    selected = []
    for leaf, candidates in sorted(by_leaf.items()):
        choice = choose(candidates, arm)
        selected.append({
            "group_id": choice["group_id"], "source_seed": choice["source_seed"],
            "leaf_snapshot_id": leaf, "baseline_value": choice["leaf_baseline32"],
            "value": choice["q32"], "teacher_a": choice["teacher_a"],
            "teacher_b": choice["teacher_b"], "selected_prefix": choice["prefix_key"],
            "selected_length": choice["prefix_length"], "selected_q32": choice["q32"],
            "oracle_prefix": max(candidates, key=lambda row: (row["q32"], row["prefix_key"]))["prefix_key"],
            "oracle_length": max(candidates, key=lambda row: (row["q32"], row["prefix_key"]))["prefix_length"],
            "oracle_q32": max(row["q32"] for row in candidates),
        })
    return selected


def bootstrap(selected: list[dict], iterations: int) -> dict:
    by_source = defaultdict(list)
    for row in selected:
        by_source[row["source_seed"]].append(row)
    sources = sorted(by_source)
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for draw in range(iterations):
        baseline, candidate = [], []
        for occurrence, source in enumerate(rng.choice(sources) for _ in sources):
            for row in by_source[source]:
                left = dict(row)
                left["group_id"] = f"{row['group_id']}#{draw}#{occurrence}"
                baseline.append(left)
                right = dict(left)
                right["value"] = row["value"]
                candidate.append(right)
        values.append(
            FROZEN.sibling_metrics(baseline, "baseline_value", "teacher_a")["mean_teacher_regret"]
            - FROZEN.sibling_metrics(candidate, "value", "teacher_a")["mean_teacher_regret"])
    values.sort()
    return {"p025": values[int(0.025 * (len(values) - 1))],
            "p975": values[int(0.975 * (len(values) - 1))],
            "bootstrap_seed": BOOTSTRAP_SEED, "iterations": iterations,
            "cluster_key": "source_seed", "cluster_count": len(sources)}


def selected_metrics(selected: list[dict], bootstrap_iterations: int) -> dict:
    baseline = [{**row, "value": row["baseline_value"]} for row in selected]
    oracle = [{**row, "value": row["oracle_q32"]} for row in selected]
    model_a = FROZEN.sibling_metrics(selected, "value", "teacher_a")
    model_b = FROZEN.sibling_metrics(selected, "value", "teacher_b")
    base_a = FROZEN.sibling_metrics(baseline, "value", "teacher_a")
    base_b = FROZEN.sibling_metrics(baseline, "value", "teacher_b")
    oracle_a = FROZEN.sibling_metrics(oracle, "value", "teacher_a")
    oracle_b = FROZEN.sibling_metrics(oracle, "value", "teacher_b")
    candidate_regrets = [row["oracle_q32"] - row["selected_q32"] for row in selected]
    lengths = Counter(row["selected_length"] for row in selected)
    oracle_lengths = Counter(row["oracle_length"] for row in selected)
    selected_first = [json.loads(row["selected_prefix"])[0] for row in selected]
    oracle_first = [json.loads(row["oracle_prefix"])[0] for row in selected]
    first_agreement = sum(a == b for a, b in zip(selected_first, oracle_first)) / len(selected)
    base_regret = base_a["mean_teacher_regret"]
    model_regret = model_a["mean_teacher_regret"]
    oracle_regret = oracle_a["mean_teacher_regret"]
    denominator = base_regret - oracle_regret
    group_diagnostics = FROZEN.group_diagnostics(selected)
    worst_regret_rows = sorted(
        ({"leaf_snapshot_id": row["leaf_snapshot_id"],
          "source_seed": row["source_seed"],
          "group_id": row["group_id"],
          "selected_prefix": row["selected_prefix"],
          "oracle_prefix": row["oracle_prefix"],
          "selected_q32": row["selected_q32"],
          "oracle_q32": row["oracle_q32"],
          "regret": row["oracle_q32"] - row["selected_q32"]}
         for row in selected), key=lambda row: row["regret"], reverse=True)
    regret_by_oracle_length = {}
    for length in (1, 2):
        values = [row["oracle_q32"] - row["selected_q32"]
                  for row in selected if row["oracle_length"] == length]
        regret_by_oracle_length[str(length)] = {
            "count": len(values),
            "mean": statistics.fmean(values) if values else None,
            "p95": float(np.percentile(values, 95)) if values else None,
        }
    finite = all(math.isfinite(value) for value in candidate_regrets)
    return {
        "teacher_a": {"baseline": base_a, "model": model_a, "oracle": oracle_a},
        "teacher_b": {"baseline": base_b, "model": model_b, "oracle": oracle_b},
        "teacher_a_regret_reduction": (base_regret - model_regret) / base_regret,
        "teacher_b_regret_reduction": (base_b["mean_teacher_regret"] - model_b["mean_teacher_regret"]) / base_b["mean_teacher_regret"],
        "recovered_oracle_fraction": (base_regret - model_regret) / denominator if denominator else None,
        "oracle_denominator": {"baseline_regret": base_regret, "locked_full_q32_oracle_regret": oracle_regret,
                               "difference": denominator},
        "clustered_bootstrap": bootstrap(selected, bootstrap_iterations),
        "candidate_regret": {"mean": statistics.fmean(candidate_regrets),
                              "median": statistics.median(candidate_regrets),
                              "p95": float(np.percentile(candidate_regrets, 95)),
                              "maximum": max(candidate_regrets)},
        "candidate_regret_by_oracle_length": regret_by_oracle_length,
        "catastrophic_tail": {
            "largest_per_leaf_q32_regret": max(candidate_regrets),
            "p95_candidate_regret": float(np.percentile(candidate_regrets, 95)),
            "largest_sibling_group_teacher_a_regression": min(
                (row["improvement"] for row in group_diagnostics["largest_regressions"]),
                default=0.0),
            "worst_leaf_cases": worst_regret_rows[:8],
            "severe_obvious_defect": not finite,
        },
        "group_diagnostics": group_diagnostics,
        "selected_length_counts": dict(lengths), "oracle_length_counts": dict(oracle_lengths),
        "first_action_agreement": first_agreement,
        "full_prefix_agreement": sum(row["selected_prefix"] == row["oracle_prefix"] for row in selected) / len(selected),
        "prefix_length_agreement": sum(row["selected_length"] == row["oracle_length"] for row in selected) / len(selected),
        "leaves": len(selected), "represented_groups": len({row["group_id"] for row in selected}),
        "selected_rows": selected,
    }


def source_contributions(selected: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in selected:
        grouped[row["source_seed"]].append(row)
    report = []
    for source, rows in sorted(grouped.items()):
        baseline = [{**row, "value": row["baseline_value"]} for row in rows]
        model = [{**row, "value": row["value"]} for row in rows]
        base = FROZEN.sibling_metrics(baseline, "value", "teacher_a")["mean_teacher_regret"]
        value = FROZEN.sibling_metrics(model, "value", "teacher_a")["mean_teacher_regret"]
        report.append({"source_seed": source, "leaf_count": len(rows),
                       "baseline_regret": base, "model_regret": value,
                       "difference": base - value})
    return report


def leave_one_source_out(selected: list[dict], bootstrap_iterations: int) -> list[dict]:
    """Describe the locked result after omitting each source once."""
    sources = sorted({row["source_seed"] for row in selected})
    report = []
    for source in sources:
        remaining = [row for row in selected if row["source_seed"] != source]
        metrics = selected_metrics(remaining, bootstrap_iterations)
        report.append({"omitted_source_seed": source,
                       "remaining_source_count": len(sources) - 1,
                       "recovered_oracle_fraction": metrics["recovered_oracle_fraction"],
                       "teacher_a_regret_reduction": metrics["teacher_a_regret_reduction"],
                       "clustered_p025": metrics["clustered_bootstrap"]["p025"]})
    return report


def direct_prediction(rows: list[dict], arm: str) -> dict:
    target = np.asarray([row["centered_q"] for row in rows])
    prediction = np.asarray([row[f"predicted_{arm}"] for row in rows])
    return {"centered_mae": float(np.mean(np.abs(target - prediction))),
            "centered_rmse": float(np.sqrt(np.mean((target - prediction) ** 2))),
            "pearson": float(pearsonr(target, prediction).statistic),
            "spearman": float(spearmanr(target, prediction).statistic)}


def write_predictions(rows: list[dict], path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps({key: row[key] for key in (
                "group_id", "source_seed", "leaf_snapshot_id", "prefix_key", "prefix_length",
                "q32", "centered_q", "predicted_MLP_FLAT_V1")},
                sort_keys=True, separators=(",", ":")) + "\n")


def run(args: argparse.Namespace) -> int:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    packets = {}
    for role, spec in config["roles"].items():
        rows, metadata = load_packet(spec["packet"], role)
        metadata["rows"] = rows
        packets[role] = metadata
    partition = validate_partition(config, packets)

    base = packets["base_training_pool"]["rows"]
    expansion = packets["expansion_training_pool"]["rows"]
    locked = packets["locked_validation"]["rows"]
    base_sources = set(partition["base_training_pool"])
    expansion_sources = set(partition["expansion_training_pool"])
    locked_sources = set(partition["locked_validation"])
    expansion_first = set(config["roles"]["expansion_training_pool"]["primary_first_20"])
    if not expansion_first <= expansion_sources or len(expansion_first) != 20:
        raise SystemExit("primary_first_20 must contain exactly 20 expansion source seeds")

    train_rows = {
        "TRAIN20": rows_for_sources(base, base_sources),
        "TRAIN40": rows_for_sources(base, base_sources) + rows_for_sources(expansion, expansion_first),
        "TRAIN60": rows_for_sources(base, base_sources) + rows_for_sources(expansion, expansion_sources),
    }
    if any({row["source_seed"] for row in rows} & locked_sources for rows in train_rows.values()):
        raise SystemExit("locked validation source entered a training arm")
    validation = list(locked)
    validation_sources = {row["source_seed"] for row in validation}
    if validation_sources != locked_sources:
        raise SystemExit("locked validation does not cover exactly the designated sources")

    args.output.mkdir(parents=True, exist_ok=False)
    all_reports = {}
    for arm, rows in train_rows.items():
        prediction, meta = fit_flat(rows, validation, TRAINING_SEED)
        for row, value in zip(validation, prediction):
            row[f"predicted_MLP_FLAT_V1"] = float(value)
        selected = select_rows(validation, "MLP_FLAT_V1")
        report = selected_metrics(selected, args.bootstrap)
        report["training_sources"] = sorted({row["source_seed"] for row in rows})
        report["training_source_count"] = len(report["training_sources"])
        report["training_rows"] = len(rows)
        report["model"] = meta
        report["direct_prediction"] = direct_prediction(validation, "MLP_FLAT_V1")
        report["source_contributions"] = source_contributions(selected)
        all_reports[arm] = report
        prediction_path = args.output / f"{arm.lower()}-predictions.jsonl.gz"
        write_predictions(validation, prediction_path)

    # The five-seed repeat is a diagnostic only.  It reuses the same TRAIN60
    # sources and the same locked validation set; no seed is selected.
    robustness = []
    for seed in range(20260920, 20260925):
        prediction, meta = fit_flat(train_rows["TRAIN60"], validation, seed)
        for row, value in zip(validation, prediction):
            row["predicted_MLP_FLAT_V1"] = float(value)
        selected = select_rows(validation, "MLP_FLAT_V1")
        report = selected_metrics(selected, args.bootstrap)
        robustness.append({"training_seed": seed,
                           "teacher_a_regret": report["teacher_a"]["model"]["mean_teacher_regret"],
                           "recovered_oracle_fraction": report["recovered_oracle_fraction"],
                           "teacher_b_regret_reduction": report["teacher_b_regret_reduction"],
                           "parameters": meta["parameters"]})

    all_rows = base + expansion + locked
    dataset = {}
    for role, packet in packets.items():
        rows = packet["rows"]
        leaves = {row["leaf_snapshot_id"] for row in rows}
        groups = {row["group_id"] for row in rows}
        lengths = Counter(row["prefix_length"] for row in rows)
        per_leaf = Counter(row["leaf_snapshot_id"] for row in rows)
        dataset[role] = {"source_seeds": len({row["source_seed"] for row in rows}),
                         "leaves": len(leaves), "sibling_groups": len(groups),
                         "length_1_candidates": lengths[1], "length_2_candidates": lengths[2],
                         "total_candidates": len(rows),
                         "candidates_per_leaf": {"mean": statistics.fmean(per_leaf.values()),
                                                  "median": statistics.median(per_leaf.values()),
                                                  "p95": float(np.percentile(list(per_leaf.values()), 95))}}

    primary = all_reports["TRAIN60"]
    locked_leaves = dataset["locked_validation"]["leaves"]
    gate = {"recovered_at_least_50_percent": primary["recovered_oracle_fraction"] is not None and primary["recovered_oracle_fraction"] >= 0.50,
            "clustered_p025_positive": primary["clustered_bootstrap"]["p025"] > 0,
            "teacher_b_not_below_negative_5_percent": primary["teacher_b_regret_reduction"] >= -0.05,
            "full_locked_coverage": primary["leaves"] == locked_leaves,
            "no_severe_catastrophic_tail_defect": not primary["catastrophic_tail"]["severe_obvious_defect"],
            "performance_not_obviously_driven_by_one_or_two_sources": len(primary["source_contributions"]) >= 3,
            "source_seed_count_at_least_30": len(locked_sources) >= 30}
    source_rows = primary["source_contributions"]
    improved = sum(row["difference"] > 0 for row in source_rows)
    worsened = sum(row["difference"] < 0 for row in source_rows)
    influence = leave_one_source_out(
        primary["selected_rows"], args.bootstrap)
    influence_by_change = sorted(
        influence,
        key=lambda row: row["recovered_oracle_fraction"] - primary["recovered_oracle_fraction"])
    learning_curve = {
        "recovered_oracle_fraction": {
            arm: all_reports[arm]["recovered_oracle_fraction"]
            for arm in ("TRAIN20", "TRAIN40", "TRAIN60")},
        "teacher_a_regret_reduction": {
            arm: all_reports[arm]["teacher_a_regret_reduction"]
            for arm in ("TRAIN20", "TRAIN40", "TRAIN60")},
    }
    curve_values = [learning_curve["recovered_oracle_fraction"][arm]
                    for arm in ("TRAIN20", "TRAIN40", "TRAIN60")]
    if curve_values[0] < curve_values[1] < curve_values[2]:
        learning_curve["classification"] = "LEARNING_CURVE_POSITIVE"
    elif (abs(curve_values[1] - curve_values[2]) <= 0.02
          and max(curve_values[1], curve_values[2]) < 0.50):
        learning_curve["classification"] = "LEARNING_CURVE_SATURATED"
    else:
        learning_curve["classification"] = "NO_CLEAR_MONOTONE_TREND"
    if all(gate.values()):
        classification = "FLAT_MLP_SCALE_VALIDATED"
    elif primary["recovered_oracle_fraction"] is not None and primary["recovered_oracle_fraction"] >= 0.25 and primary["clustered_bootstrap"]["p025"] > 0:
        classification = "FLAT_MLP_SCALE_PARTIAL"
    elif len(locked_sources) < 30:
        classification = "FLAT_MLP_SCALE_UNDERPOWERED"
    else:
        classification = "FLAT_MLP_GENERALIZATION_FAILED"

    config_hash = sha256(args.config)
    analysis = {"schema": "silver_prefix_scorer_scale_analysis_v1",
                "classification": classification, "gate": gate,
                "dataset": dataset, "arms": all_reports,
                "learning_curve": learning_curve,
                "train60_robustness": robustness,
                "robustness_summary": {"mean_recovered": statistics.fmean(r["recovered_oracle_fraction"] for r in robustness),
                                       "std_recovered": statistics.pstdev(r["recovered_oracle_fraction"] for r in robustness),
                                       "min_recovered": min(r["recovered_oracle_fraction"] for r in robustness),
                                       "max_recovered": max(r["recovered_oracle_fraction"] for r in robustness)},
                "source_seed_robustness": {"improved": improved, "unchanged": len(source_rows) - improved - worsened,
                                           "worsened": worsened, "rows": source_rows,
                                           "leave_one_source_out": influence,
                                           "largest_positive_influence": influence_by_change[-1] if influence_by_change else None,
                                           "largest_negative_influence": influence_by_change[0] if influence_by_change else None},
                "training": {"configuration": "MLP_FLAT_V1", "parameter_count": PARAMETERS,
                              "training_seed": TRAINING_SEED, "bootstrap_iterations": args.bootstrap,
                              "teacher_fields_in_training": False, "locked_values_used_for_selection": False},
                "partition": partition, "config_sha256": config_hash,
                "inputs": {role: packet["sha256"] for role, packet in packets.items()},
                "decision_rule": "TRAIN60 gate: recovered >= 50%, clustered Teacher-A p025 > 0, Teacher-B reduction >= -5%, full coverage, >=30 locked sources",
                "boundary": "offline evidence only; no SimpleAgent integration, rollout-policy change, learned gameplay, hard64 holdout, or architecture tuning"}
    (args.output / "analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "dataset-summary.json").write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=5000)
    args = parser.parse_args()
    if args.bootstrap < 1000:
        parser.error("--bootstrap must be at least 1000")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
