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


def eligible_leaf(row: dict) -> bool:
    """Keep only nonterminal PLAYER_NORMAL leaves when state data is present."""
    envelope = row.get("leaf_state")
    if envelope is None:
        # Preserve the small synthetic selector fixtures, which intentionally
        # omit the full wire state.
        return True
    state = envelope.get("state", {})
    return state.get("inputState") == 1 and state.get("outcome") == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-groups", type=int, default=500)
    parser.add_argument("--required-source-seeds", nargs="+", default=[])
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
            if not eligible_leaf(row):
                continue
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
                    "source_seed": str(row.get("run_seed", "")),
                    "legal": legal, "mapped": set(), "leaf_ids": [],
                }
            elif group["legal"] != legal:
                raise SystemExit(f"{args.corpus}: group {group_id} has inconsistent legal-action sets")
            elif group["source_seed"] != str(row.get("run_seed", "")):
                raise SystemExit(f"{args.corpus}: group {group_id} spans source seeds")
            group["mapped"].add(row.get("incoming_action_fingerprint", ""))
            group["leaf_ids"].append(leaf_id)

    incomplete_groups = {
        group_id for group_id, group in groups.items()
        if not set(group["legal"]) <= group["mapped"]
    }
    groups = {
        group_id: group for group_id, group in groups.items()
        if group_id not in incomplete_groups
    }
    target = min(args.target_groups, len(groups))
    rollout_order = {"long": 0, "medium": 1, "short": 2}
    hp_order = {"low": 0, "mid": 1, "high": 2}
    category_order = {"boss": 0, "elite": 1, "hallway": 2}
    rollout_weight = {"long": 2, "medium": 1, "short": 1}
    hp_weight = {"low": 2, "mid": 1, "high": 1}
    buckets: dict[int, dict[tuple[str, str, str], list[str]]] = defaultdict(
        lambda: defaultdict(list))
    for group_id, group in groups.items():
        key = (rollout_band(group), hp_band(group), group["encounter_category"])
        buckets[group["act"]][key].append(group_id)
    for act_buckets in buckets.values():
        for ids in act_buckets.values():
            ids.sort(key=stable, reverse=True)

    selected: list[str] = []
    selected_set: set[str] = set()
    rollout_counts: dict[int, Counter] = defaultdict(Counter)
    hp_counts: dict[int, Counter] = defaultdict(Counter)
    category_counts: dict[int, Counter] = defaultdict(Counter)

    def retain(gid: str) -> None:
        selected.append(gid)
        selected_set.add(gid)
        group = groups[gid]
        rollout_counts[group["act"]][rollout_band(group)] += 1
        hp_counts[group["act"]][hp_band(group)] += 1
        category_counts[group["act"]][group["encounter_category"]] += 1

    def choose_for_act(act: int) -> str | None:
        candidates = []
        for (rollout, hp, category), ids in buckets[act].items():
            while ids and ids[-1] in selected_set:
                ids.pop()
            if not ids:
                continue
            candidates.append((
                rollout_counts[act][rollout] / rollout_weight.get(rollout, 1),
                hp_counts[act][hp] / hp_weight.get(hp, 1),
                category_counts[act][category],
                rollout_order.get(rollout, 99), hp_order.get(hp, 99),
                category_order.get(category, 99), stable(ids[-1]), ids[-1],
            ))
        if not candidates:
            return None
        gid = min(candidates)[-1]
        key = (rollout_band(groups[gid]), hp_band(groups[gid]),
               groups[gid]["encounter_category"])
        popped = buckets[act][key].pop()
        assert popped == gid
        return gid

    # Act 4 is rare and is retained before balancing the remaining acts.
    act4 = sorted((gid for gid, group in groups.items() if group["act"] == 4), key=stable)
    for gid in act4:
        retain(gid)
    acts = sorted(act for act in buckets if act != 4)
    while len(selected) < target:
        progressed = False
        for act in acts:
            if len(selected) < target:
                gid = choose_for_act(act)
                if gid is not None:
                    retain(gid)
                    progressed = True
        if not progressed:
            break

    required_sources = {str(seed) for seed in args.required_source_seeds}
    selected_sources = {groups[gid]["source_seed"] for gid in selected}
    for source_seed in sorted(required_sources - selected_sources):
        candidates = sorted(
            (gid for gid, group in groups.items()
             if group["source_seed"] == source_seed and gid not in selected_set),
            key=stable)
        if not candidates:
            raise SystemExit(f"{args.corpus}: required source seed has no complete group: {source_seed}")
        retain(candidates[0])

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
        "required_source_seeds": sorted(required_sources),
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
