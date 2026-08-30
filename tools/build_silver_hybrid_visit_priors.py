#!/usr/bin/env python3
"""Build frozen A-only hybrid priors for the Silver root diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_predictions(path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("visit_prior_schema") != "silver_parent_visit_prior_predictions_v1":
        raise ValueError("unexpected learned-prior schema")
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    for values in groups.values():
        values.sort(key=lambda row: row["silver_order"])
    return header, groups


def load_a_visits(path):
    visits = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if (row.get("relabel_schema") != "silver_leaf_teacher_v1"
                    or row.get("state_kind") != "parent"
                    or row.get("budget") != 25000
                    or row.get("replicate") != "A"
                    or not row.get("teacher_valid", False)):
                continue
            group = row["group_id"]
            actions = {action["action_fingerprint"]: int(action["visits"])
                       for action in row["root_actions"]}
            if group in visits:
                raise ValueError(f"duplicate A visits: {group}")
            total = sum(actions.values())
            if total <= 0:
                raise ValueError(f"non-positive A visit total: {group}")
            visits[group] = {fp: value / total for fp, value in actions.items()}
    return visits


def write_prior(path, schema_target, groups, values):
    with path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "visit_prior_schema": "silver_parent_visit_prior_predictions_v1",
            "feature_schema": "silver_parent_policy_features_v1",
            "feature_count": 1788,
            "target": schema_target,
            "construction": "frozen_25k_A_only_hybrid",
        }, sort_keys=True) + "\n")
        for group in sorted(groups):
            for row in groups[group]:
                stream.write(json.dumps({
                    "group_id": group,
                    "action_fingerprint": row["action_fingerprint"],
                    "silver_order": row["silver_order"],
                    "normalized_visit_share": values[group][row["action_fingerprint"]],
                }, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("learned_predictions", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prediction_header, all_groups = load_predictions(args.learned_predictions)
    a_visits = load_a_visits(args.relabels)
    groups = {group: rows for group, rows in all_groups.items() if len(rows) > 1}
    if len(groups) != 63:
        raise ValueError(f"expected 63 multi-action groups, found {len(groups)}")

    learned_order_mass = {}
    oracle_order_learned_mass = {}
    for group in sorted(groups):
        rows = groups[group]
        if set(a_visits[group]) != {row["action_fingerprint"] for row in rows}:
            raise ValueError(f"A action surface mismatch: {group}")
        learned_order = sorted(rows, key=lambda row: -float(row["raw_prediction"]))
        oracle_order = sorted(rows, key=lambda row: -a_visits[group][row["action_fingerprint"]])
        learned_mass = sorted(
            (float(row["normalized_visit_share"]) for row in rows), reverse=True
        )
        oracle_mass = sorted(
            (a_visits[group][row["action_fingerprint"]] for row in rows), reverse=True
        )
        learned_order_mass[group] = {
            row["action_fingerprint"]: mass
            for row, mass in zip(learned_order, oracle_mass)
        }
        oracle_order_learned_mass[group] = {
            row["action_fingerprint"]: mass
            for row, mass in zip(oracle_order, learned_mass)
        }
        for prior in (learned_order_mass[group], oracle_order_learned_mass[group]):
            if abs(sum(prior.values()) - 1.0) > 1e-12:
                raise ValueError(f"hybrid prior is not normalized: {group}")

    output_a = args.output_dir / "learned_order_oracle_mass.jsonl"
    output_b = args.output_dir / "oracle_order_learned_mass.jsonl"
    write_prior(output_a, "learned_order_oracle_mass", groups, learned_order_mass)
    write_prior(output_b, "oracle_order_learned_mass", groups, oracle_order_learned_mass)
    report = {
        "schema": "silver_hybrid_visit_prior_construction_v1",
        "inputs": {
            "learned_predictions": str(args.learned_predictions),
            "learned_predictions_sha256": sha256(args.learned_predictions),
            "relabels": str(args.relabels),
            "relabels_sha256": sha256(args.relabels),
        },
        "source_prediction_schema": prediction_header,
        "groups": len(groups),
        "construction": {
            "learned_order_oracle_mass": "learned raw-count rank order; descending exact A visit shares assigned by rank",
            "oracle_order_learned_mass": "descending exact A visit order; descending learned normalized magnitudes assigned by rank",
            "uses_25k_b": False,
            "uses_model_training": False,
            "stable_tie_break": "existing silver_order",
        },
        "outputs": {
            "learned_order_oracle_mass": {"path": str(output_a), "sha256": sha256(output_a)},
            "oracle_order_learned_mass": {"path": str(output_b), "sha256": sha256(output_b)},
        },
    }
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
