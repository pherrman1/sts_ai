#!/usr/bin/env python3
"""Reproduce the retained-node opportunity screen for the frozen Silver tree.

The input may be the original JSON capture or the committed gzip-compressed
copy. The script deliberately performs only the Wire-level screen: native
BattleContext fields absent from the capture are not inferred.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED = {
    "total_nodes": 1133,
    "state_nodes": 997,
    "chance_nodes": 136,
    "player_normal_unresolved": 974,
    "distinct_non_queue_keys": 942,
    "candidate_groups": 49,
    "candidate_nodes": 104,
    "excess_nodes": 55,
    "unordered_pairs": 61,
    "candidate_pairs": 43,
    "candidate_triples": 6,
    "candidate_edges": 124,
    "candidate_groups_with_distinct_queue_items": 49,
    "candidate_groups_with_matching_state_hash": 49,
}

EXPECTED_PAYLOAD_SHA256 = "e20001e051e65e723c8cdf51e73890bc3df971454aa3713854acb2d9980ad22d"
EXPECTED_SESSION = "78c0ee4f9f67"
EXPECTED_SEQUENCE = 9
EXPECTED_OBSERVATION_HASH = "efb8bcf0367f908221521ab79f09c5f666ee5a6cf3d6e0b047b41f95558c84d8"


def load(path: Path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(raw)
    else:
        payload = raw
    document = json.loads(payload)
    evaluators = document["response"]["advisor"]["evaluators"]
    evaluator = next(item for item in evaluators if item["id"] == "silver_player_decision_v2")
    return document, evaluator["tree"], hashlib.sha256(payload).hexdigest(), hashlib.sha256(raw).hexdigest()


def non_queue_state(state):
    result = copy.deepcopy(state)
    result.pop("curCardQueueItem", None)
    return result


def key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    document, tree, payload_sha, file_sha = load(args.capture)
    if payload_sha != EXPECTED_PAYLOAD_SHA256:
        raise SystemExit(f"unexpected capture payload SHA-256: {payload_sha}")
    if document["session"] != EXPECTED_SESSION or document["sequence"] != EXPECTED_SEQUENCE:
        raise SystemExit("capture session/sequence does not match the frozen provenance")
    if document["observationHash"] != EXPECTED_OBSERVATION_HASH:
        raise SystemExit("capture observation hash does not match the frozen provenance")
    provenance = document.get("captureProvenance", {})
    if (
        provenance.get("liveSession") != EXPECTED_SESSION
        or provenance.get("liveSequence") != EXPECTED_SEQUENCE
        or provenance.get("liveObservationHash") != EXPECTED_OBSERVATION_HASH
    ):
        raise SystemExit("captureProvenance does not match the frozen live provenance")
    nodes = tree["nodes"]
    state_nodes = [node for node in nodes if node.get("hasState")]
    chance_nodes = [node for node in nodes if node.get("isChanceNode")]
    groups = defaultdict(list)
    for node in state_nodes:
        groups[key(non_queue_state(node["state"]))].append(node)
    candidate_groups = [group for group in groups.values() if len(group) > 1]
    queue_variant_counts = Counter()
    matching_hash_groups = 0
    for group in candidate_groups:
        queue_variants = {key(node["state"].get("curCardQueueItem")) for node in group}
        if len(queue_variants) < 2:
            raise SystemExit("candidate group does not contain distinct queue items")
        queue_variant_counts[len(queue_variants)] += 1
        if len({node.get("stateHash") for node in group}) == 1:
            matching_hash_groups += 1
    candidate_nodes = sum(len(group) for group in candidate_groups)
    excess_nodes = sum(len(group) - 1 for group in candidate_groups)
    unordered_pairs = sum(len(group) * (len(group) - 1) // 2 for group in candidate_groups)
    candidate_ids = {node["id"] for group in candidate_groups for node in group}
    candidate_edges = sum(1 for edge in tree["edges"] if edge["parentId"] in candidate_ids)
    normal_unresolved = sum(
        node["state"].get("inputState") == 1 and node["state"].get("outcome") == 0
        for node in state_nodes
    )
    boundary_counts = Counter(
        (node["state"].get("inputState"), node["state"].get("outcome"))
        for group in candidate_groups
        for node in group
    )
    group_size_counts = Counter(len(group) for group in candidate_groups)
    result = {
        "source": {
            "captureProvenance": document.get("captureProvenance"),
            "session": document["session"],
            "sequence": document["sequence"],
            "observationHash": document["observationHash"],
            "payloadSha256": payload_sha,
            "fileSha256": file_sha,
        },
        "tree": {
            "total_nodes": len(nodes),
            "state_nodes": len(state_nodes),
            "chance_nodes": len(chance_nodes),
            "player_normal_unresolved": normal_unresolved,
            "distinct_non_queue_keys": len(groups),
            "candidate_groups": len(candidate_groups),
            "candidate_nodes": candidate_nodes,
            "excess_nodes": excess_nodes,
            "unordered_pairs": unordered_pairs,
            "candidate_pairs": group_size_counts[2],
            "candidate_triples": group_size_counts[3],
            "candidate_edges": candidate_edges,
            "candidate_groups_with_distinct_queue_items": sum(queue_variant_counts.values()),
            "candidate_groups_with_matching_state_hash": matching_hash_groups,
            "total_edges": len(tree["edges"]),
            "candidate_boundary_counts": {
                f"inputState={input_state},outcome={outcome}": count
                for (input_state, outcome), count in sorted(boundary_counts.items())
            },
            "state_fraction": excess_nodes / len(state_nodes),
            "total_fraction": excess_nodes / len(nodes),
            "queue_variant_group_sizes": dict(sorted(queue_variant_counts.items())),
        },
    }
    observed = {name: result["tree"][name] for name in EXPECTED}
    if observed != EXPECTED:
        raise SystemExit(f"unexpected frozen-tree result: {json.dumps(observed, sort_keys=True)}")
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
