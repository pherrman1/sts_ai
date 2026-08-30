#!/usr/bin/env python3
"""Fail-closed composition audit for the frozen visit-policy anchor surface."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


FEATURE_SHA256 = "0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd"
RELABEL_SHA256 = "abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def action_fingerprints(label: dict) -> list[str]:
    if not label.get("teacher_valid", False):
        raise ValueError(f"invalid frozen anchor: {label['group_id']}")
    actions = label.get("root_actions", [])
    if label.get("root_action_count") != len(actions):
        raise ValueError(f"label action count mismatch: {label['group_id']}")
    values = [action.get("action_fingerprint") for action in actions]
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"missing frozen action fingerprint: {label['group_id']}")
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate frozen action fingerprint: {label['group_id']}")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    feature_hash, relabel_hash = sha256(args.features), sha256(args.relabels)
    if feature_hash != FEATURE_SHA256:
        raise ValueError(f"feature SHA mismatch: {feature_hash}")
    if relabel_hash != RELABEL_SHA256:
        raise ValueError(f"relabel SHA mismatch: {relabel_hash}")

    features: dict[str, list[dict]] = defaultdict(list)
    with args.features.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("feature_schema") != "silver_parent_policy_features_v1" or header.get("feature_count") != 1788:
            raise ValueError("incompatible canonical feature artifact")
        for line in stream:
            if line.strip():
                row = json.loads(line)
                features[row["group_id"]].append(row)
    for group, rows in features.items():
        rows.sort(key=lambda row: row["silver_order"])
        if [row["silver_order"] for row in rows] != list(range(len(rows))):
            raise ValueError(f"noncanonical feature order: {group}")
        if len({row["action_fingerprint"] for row in rows}) != len(rows):
            raise ValueError(f"duplicate feature action: {group}")

    labels: dict[tuple[str, int, str], dict] = {}
    anchors: set[str] = set()
    with args.relabels.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("relabel_schema") != "silver_leaf_teacher_v1" or row.get("state_kind") != "parent":
                continue
            key = (row["group_id"], int(row["budget"]), row["replicate"])
            if key in labels:
                raise ValueError(f"duplicate relabel row: {key}")
            labels[key] = row
            if key[1:] == (25000, "B"):
                anchors.add(key[0])
    if len(anchors) != 93:
        raise ValueError(f"expected 93 frozen 25k-B anchors, got {len(anchors)}")

    multi, singleton = [], []
    for group in sorted(anchors):
        a = labels.get((group, 25000, "A"))
        b = labels.get((group, 25000, "B"))
        if a is None or b is None:
            raise ValueError(f"missing 25k A/B pair: {group}")
        a_fingerprints, b_fingerprints = action_fingerprints(a), action_fingerprints(b)
        rows = features.get(group)
        if rows is None:
            raise ValueError(f"anchor missing canonical feature rows: {group}")
        feature_fingerprints = [row["action_fingerprint"] for row in rows]
        if set(a_fingerprints) != set(b_fingerprints) or set(a_fingerprints) != set(feature_fingerprints):
            raise ValueError(f"A/B/feature action surface mismatch: {group}")
        if len(feature_fingerprints) == 1:
            if a_fingerprints[0] != b_fingerprints[0] or a_fingerprints[0] != feature_fingerprints[0]:
                raise ValueError(f"singleton fingerprint mismatch: {group}")
            singleton.append(group)
        elif len(feature_fingerprints) > 1:
            multi.append(group)
        else:
            raise ValueError(f"zero-action anchor: {group}")
    if len(multi) != 63 or len(singleton) != 30:
        raise ValueError(f"unexpected anchor composition: multi={len(multi)} singleton={len(singleton)}")

    report = {
        "schema": "silver_visit_policy_anchor_composition_audit_v1",
        "inputs": {"features_sha256": feature_hash, "relabels_sha256": relabel_hash},
        "anchors": {"valid_frozen_25k_b": len(anchors), "multi_action": len(multi),
                    "single_action": len(singleton), "zero_action": 0},
        "single_action_contract": {"distribution": [1.0],
            "a_b_feature_sole_fingerprint_equal": True, "groups": singleton},
        "multi_action_groups": multi,
        "passed": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
