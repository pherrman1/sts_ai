#!/usr/bin/env python3
"""Compare frozen learned-prior replays only after strict provenance alignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

from analyze_silver_learned_visit_replay import ARMS, BOOTSTRAP_SEED, bootstrap_mean, load


CONTROL_ARMS = ("current_uct", "oracle_visit_puct")
CONTROL_FIELDS = ("selected_action_fingerprint", "frozen_b_top_choice", "frozen_b_regret")
HEADER_FIELDS = ("replay_schema", "snapshot_schema", "judgment", "oracle", "anchors")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def indexed(rows):
    return {(row["group_id"], row["replicate"], row["arm"]): row for row in rows}


def root_replicates(rows):
    return {(row["group_id"], row["replicate"]) for row in rows}


def verify_artifact(name, path, metadata, snapshots_hash, relabels_hash):
    expected = metadata[name]
    observed = sha256(path)
    if observed != expected["replay_sha256"]:
        raise ValueError(f"{name} replay hash mismatch")
    if expected["snapshots_sha256"] != snapshots_hash:
        raise ValueError(f"{name} snapshot provenance mismatch")
    if expected["relabels_sha256"] != relabels_hash:
        raise ValueError(f"{name} relabel provenance mismatch")
    return {"replay_sha256": observed, "source_commit": expected["source_commit"],
            "executable_sha256": expected["executable_sha256"],
            "snapshots_sha256": snapshots_hash, "relabels_sha256": relabels_hash}


def compatible(reference_header, reference_rows, reference_provenance,
               candidate_header, candidate_rows, candidate_provenance):
    """Return all prerequisite results; false means do not compute a comparison."""
    checks = {
        "same_header_contract": all(reference_header.get(key) == candidate_header.get(key)
                                    for key in HEADER_FIELDS),
        "same_group_replicate_keys": root_replicates(reference_rows) == root_replicates(candidate_rows),
        "same_snapshot_hash": reference_provenance["snapshots_sha256"] == candidate_provenance["snapshots_sha256"],
        "same_relabel_hash": reference_provenance["relabels_sha256"] == candidate_provenance["relabels_sha256"],
        "same_executable_hash": reference_provenance["executable_sha256"] == candidate_provenance["executable_sha256"],
        "same_source_commit": reference_provenance["source_commit"] == candidate_provenance["source_commit"],
    }
    if checks["same_group_replicate_keys"]:
        reference = indexed(reference_rows)
        candidate = indexed(candidate_rows)
        keys = sorted(root_replicates(reference_rows))
        checks["same_per_root_replicate_seed"] = all(
            reference[(group, replicate, arm)]["search_seed"] == candidate[(group, replicate, arm)]["search_seed"]
            for group, replicate in keys for arm in ARMS)
        checks["exact_current_oracle_controls"] = all(
            all(reference[(group, replicate, arm)][field] == candidate[(group, replicate, arm)][field]
                for field in CONTROL_FIELDS)
            for group, replicate in keys for arm in CONTROL_ARMS)
    else:
        checks["same_per_root_replicate_seed"] = False
        checks["exact_current_oracle_controls"] = False
    return {"pass": all(checks.values()), "checks": checks,
            "failures": [name for name, passed in checks.items() if not passed]}


def learned_comparison(candidate_rows, baseline_rows, bootstrap_seed):
    candidate = indexed(candidate_rows)
    baseline = indexed(baseline_rows)
    groups = sorted({row["group_id"] for row in candidate_rows})
    top_deltas, regret_deltas = [], []
    for group in groups:
        top_deltas.append(statistics.fmean(
            float(candidate[(group, replicate, "learned_visit_puct")]["frozen_b_top_choice"])
            - float(baseline[(group, replicate, "learned_visit_puct")]["frozen_b_top_choice"])
            for replicate in range(4)))
        regret_deltas.append(statistics.fmean(
            float(candidate[(group, replicate, "learned_visit_puct")]["frozen_b_regret"])
            - float(baseline[(group, replicate, "learned_visit_puct")]["frozen_b_regret"])
            for replicate in range(4)))
    rng = random.Random(bootstrap_seed)
    return {
        "roots": len(groups), "replicates_per_root": 4, "bootstrap_replicates": 10_000,
        "bootstrap_seed": bootstrap_seed,
        "mean_b_best_probability_delta": statistics.fmean(top_deltas),
        "mean_b_best_probability_delta_pp": 100.0 * statistics.fmean(top_deltas),
        "b_best_probability_delta_ci95": bootstrap_mean(top_deltas, rng),
        "mean_frozen_b_regret_delta": statistics.fmean(regret_deltas),
        "mean_frozen_b_regret_delta_ci95": bootstrap_mean(regret_deltas, rng),
        "median_frozen_b_regret_delta": statistics.median(regret_deltas),
        "regret_improved": sum(delta < -1e-12 for delta in regret_deltas),
        "regret_worsened": sum(delta > 1e-12 for delta in regret_deltas),
        "regret_tied": sum(abs(delta) <= 1e-12 for delta in regret_deltas),
        "largest_negative_regret_delta": {
            "group_id": groups[min(range(len(groups)), key=lambda i: (regret_deltas[i], groups[i]))],
            "delta": min(regret_deltas)},
        "largest_positive_regret_delta": {
            "group_id": groups[max(range(len(groups)), key=lambda i: (regret_deltas[i], groups[i]))],
            "delta": max(regret_deltas)},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("grouped_linear", type=Path)
    parser.add_argument("raw_count", type=Path)
    parser.add_argument("rankshape", type=Path)
    parser.add_argument("provenance", type=Path,
                        help="JSON mapping replay names to frozen artifact hashes/provenance")
    parser.add_argument("snapshots", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(args.provenance.read_text(encoding="utf-8"))["replays"]
    snapshots_hash, relabels_hash = sha256(args.snapshots), sha256(args.relabels)
    paths = {"grouped_linear": args.grouped_linear, "raw_count": args.raw_count, "rankshape": args.rankshape}
    provenance = {name: verify_artifact(name, path, metadata, snapshots_hash, relabels_hash)
                  for name, path in paths.items()}
    loaded = {name: load(path) for name, path in paths.items()}
    header, rows = loaded["grouped_linear"]
    comparisons = {}
    for number, name in enumerate(("raw_count", "rankshape"), 1):
        candidate_header, candidate_rows = loaded[name]
        preconditions = compatible(header, rows, provenance["grouped_linear"],
                                   candidate_header, candidate_rows, provenance[name])
        result = {"preconditions": preconditions}
        if preconditions["pass"]:
            result["comparison"] = learned_comparison(rows, candidate_rows, BOOTSTRAP_SEED + 100 + number)
        else:
            result["comparison"] = None
            result["status"] = "REJECTED_INCOMPATIBLE_PROVENANCE_OR_CONTROLS"
        comparisons[name] = result
    payload = {"schema": "silver_cross_prior_replay_analysis_v1", "grouped_linear": provenance["grouped_linear"],
               "comparisons": comparisons,
               "interpretation": "Repeated diagnostic roots only; this is search-level evidence, not gameplay or playing-strength confirmation."}
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
