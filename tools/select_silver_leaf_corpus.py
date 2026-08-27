#!/usr/bin/env python3
"""Deterministically select complete Silver sibling groups for the teacher pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def hp_band(row: dict) -> str:
    fraction = row["cur_hp"] / max(1, row["max_hp"])
    return "low" if fraction < 0.34 else "mid" if fraction < 0.67 else "high"


def rollout_band(row: dict) -> str:
    turns = row["aux_rollout"]["turn_delta"]
    return "short" if turns <= 2 else "medium" if turns <= 5 else "long"


def stable(group_id: str) -> str:
    return hashlib.sha256(group_id.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-groups", type=int, default=500)
    args = parser.parse_args()
    if args.target_groups <= 0:
        parser.error("--target-groups must be positive")

    groups: dict[str, dict] = {}
    leaf_ids: set[str] = set()
    corpus_hash = hashlib.sha256()
    with args.corpus.open("rb") as stream:
        for number, raw_line in enumerate(stream, 1):
            corpus_hash.update(raw_line)
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            if row.get("corpus_schema") != "silver_leaf_corpus_v1":
                raise SystemExit(f"{args.corpus}:{number}: incompatible corpus schema")
            leaf_id = row["leaf_snapshot_id"]
            if leaf_id in leaf_ids:
                raise SystemExit(f"{args.corpus}:{number}: duplicate leaf_snapshot_id {leaf_id}")
            leaf_ids.add(leaf_id)
            group_id = row["group_id"]
            legal = tuple(sorted(row.get("parent_legal_action_fingerprints", [])))
            if not legal:
                raise SystemExit(f"{args.corpus}: group {group_id} has no legal-action set")
            group = groups.get(group_id)
            if group is None:
                group = groups[group_id] = {
                    "act": row["act"], "cur_hp": row["cur_hp"], "max_hp": row["max_hp"],
                    "encounter_category": row["encounter_category"],
                    "aux_rollout": {"turn_delta": row["aux_rollout"]["turn_delta"]},
                    "legal": legal, "mapped": set(), "leaf_ids": [],
                }
            elif group["legal"] != legal:
                raise SystemExit(f"{args.corpus}: group {group_id} has inconsistent legal-action sets")
            group["mapped"].add(row.get("incoming_action_fingerprint", ""))
            group["leaf_ids"].append(leaf_id)

    target = min(args.target_groups, len(groups))
    for group_id, group in groups.items():
        if not set(group["legal"]) <= group["mapped"]:
            raise SystemExit(f"{args.corpus}: group {group_id} is incomplete")
    by_act: dict[int, list[str]] = defaultdict(list)
    for group_id, group in groups.items():
        by_act[group["act"]].append(group_id)
    for act, ids in by_act.items():
        ids.sort(key=lambda gid: (
            rollout_band(groups[gid]) != "long",
            hp_band(groups[gid]) != "low",
            groups[gid]["encounter_category"] == "hallway",
            stable(gid),
        ))

    selected: list[str] = []
    selected_set: set[str] = set()
    # Act 4 is rare and is retained before balancing the remaining acts.
    for gid in by_act.get(4, []):
        selected.append(gid)
        selected_set.add(gid)
    acts = sorted(act for act in by_act if act != 4)
    cursors = {act: 0 for act in acts}
    while len(selected) < target:
        progressed = False
        for act in acts:
            ids = by_act[act]
            while cursors[act] < len(ids) and ids[cursors[act]] in selected_set:
                cursors[act] += 1
            if cursors[act] < len(ids) and len(selected) < target:
                gid = ids[cursors[act]]
                cursors[act] += 1
                selected.append(gid)
                selected_set.add(gid)
                progressed = True
        if not progressed:
            break

    selected.sort()
    selected_leaves = sorted(
        leaf_id for gid in selected for leaf_id in groups[gid]["leaf_ids"]
    )
    counts: dict[str, Counter] = {
        "act": Counter(), "hp_band": Counter(), "rollout_length_band": Counter(),
        "encounter_category": Counter(),
    }
    leaf_counts = {key: Counter() for key in counts}
    for gid in selected:
        representative = groups[gid]
        counts["act"][str(representative["act"])] += 1
        counts["hp_band"][hp_band(representative)] += 1
        counts["rollout_length_band"][rollout_band(representative)] += 1
        counts["encounter_category"][representative["encounter_category"]] += 1
        leaf_count = len(groups[gid]["leaf_ids"])
        leaf_counts["act"][str(representative["act"])] += leaf_count
        leaf_counts["hp_band"][hp_band(representative)] += leaf_count
        leaf_counts["rollout_length_band"][rollout_band(representative)] += leaf_count
        leaf_counts["encounter_category"][representative["encounter_category"]] += leaf_count
    manifest = {
        "manifest_schema": "silver_leaf_manifest_v1",
        "source_corpus_sha256": corpus_hash.hexdigest(),
        "target_groups": args.target_groups,
        "selected_groups": len(selected),
        "selected_leaves": len(selected_leaves),
        "group_ids": selected,
        "leaf_snapshot_ids": selected_leaves,
        "groups_by_act": dict(sorted(counts["act"].items())),
        "leaves_by_act": dict(sorted(leaf_counts["act"].items())),
        "groups_by_hp_band": dict(sorted(counts["hp_band"].items())),
        "leaves_by_hp_band": dict(sorted(leaf_counts["hp_band"].items())),
        "groups_by_rollout_length_band": dict(sorted(counts["rollout_length_band"].items())),
        "leaves_by_rollout_length_band": dict(sorted(leaf_counts["rollout_length_band"].items())),
        "groups_by_encounter_category": dict(sorted(counts["encounter_category"].items())),
        "leaves_by_encounter_category": dict(sorted(leaf_counts["encounter_category"].items())),
        "groups_with_at_least_two_unique_leaves": sum(
            len(groups[gid]["leaf_ids"]) >= 2 for gid in selected),
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in manifest if key not in {"group_ids", "leaf_snapshot_ids"}},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
