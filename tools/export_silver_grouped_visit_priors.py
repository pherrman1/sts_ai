#!/usr/bin/env python3
"""Convert frozen grouped-linear probabilities to Silver replay prior v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


EXPECTED_INPUT_SCHEMA = "silver_grouped_linear_policy_predictions_v1"
EXPECTED_INPUT_SCHEMAS = {EXPECTED_INPUT_SCHEMA,
                          "silver_rank4_interaction_policy_predictions_v1"}
OUTPUT_SCHEMA = "silver_parent_visit_prior_predictions_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_probabilities(header: dict, rows: list[dict]) -> None:
    if header.get("schema") not in EXPECTED_INPUT_SCHEMAS:
        raise ValueError("unexpected grouped policy prediction schema")
    if header.get("feature_count") != 1788 or header.get("parent_key") != "group_id":
        raise ValueError("unexpected grouped policy feature/parent contract")
    grouped: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, 2):
        required = ("group_id", "action_fingerprint", "silver_order", "probability")
        if any(key not in row for key in required):
            raise ValueError(f"missing replay-prior field at line {number}")
        key = (row["group_id"], row["action_fingerprint"])
        if key in seen:
            raise ValueError(f"duplicate replay-prior action at line {number}")
        seen.add(key)
        value = float(row["probability"])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"invalid replay-prior probability at line {number}")
        grouped[row["group_id"]].append(row)
    if len(grouped) != 63 or len(rows) != 340:
        raise ValueError(f"expected frozen 63-root/340-action artifact, got {len(grouped)} roots/{len(rows)} actions")
    for group, values in grouped.items():
        values.sort(key=lambda row: row["silver_order"])
        orders = [row["silver_order"] for row in values]
        total = math.fsum(float(row["probability"]) for row in values)
        if len(set(orders)) != len(orders) or not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"non-normalized or malformed replay-prior parent: {group}")


def replay_rows(rows: list[dict]) -> list[dict]:
    return [{"group_id": row["group_id"], "action_fingerprint": row["action_fingerprint"],
             "silver_order": row["silver_order"], "normalized_visit_share": row["probability"]}
            for row in rows]


def load_probabilities(path: Path) -> tuple[dict, list[dict]]:
    with path.open(encoding="utf-8") as stream:
        try:
            header = json.loads(next(stream))
        except StopIteration as exc:
            raise ValueError("empty grouped policy prediction artifact") from exc
        rows = [json.loads(line) for line in stream if line.strip()]
    validate_probabilities(header, rows)
    return header, rows


def export(input_path: Path, output_path: Path) -> dict:
    header, rows = load_probabilities(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "visit_prior_schema": OUTPUT_SCHEMA,
            "feature_schema": header["feature_schema"],
            "feature_count": header["feature_count"],
            "target": "normalized_25k_A_visits_grouped_linear",
            "source_probability_sha256": sha256(input_path),
        }, sort_keys=True) + "\n")
        for row in replay_rows(rows):
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    _, replay_output_rows = load_replay_priors(output_path)
    for source, replay in zip(rows, replay_output_rows):
        if source["group_id"] != replay["group_id"] or source["action_fingerprint"] != replay["action_fingerprint"]:
            raise ValueError("replay-prior action parity failure")
        if float(source["probability"]) != float(replay["normalized_visit_share"]):
            raise ValueError("replay-prior probability parity failure")
    return {"input": str(input_path), "input_sha256": sha256(input_path), "output": str(output_path),
            "output_sha256": sha256(output_path), "parents": 63, "actions": 340,
            "probability_parity": True}


def load_replay_priors(path: Path) -> tuple[dict, list[dict]]:
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("visit_prior_schema") != OUTPUT_SCHEMA:
        raise ValueError("unexpected replay prior schema")
    required = {"group_id", "action_fingerprint", "silver_order", "normalized_visit_share"}
    if any(set(row) != required for row in rows):
        raise ValueError("replay prior has extra/missing action fields")
    return header, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("probabilities", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.probabilities, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
