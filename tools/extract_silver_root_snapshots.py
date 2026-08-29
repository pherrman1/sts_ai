#!/usr/bin/env python3
"""Extract the exact 25k-B multi-action anchor roots from the frozen corpus.

The selected corpus already contains complete BattleStateWire envelopes. This
small diagnostic-only tool makes the root replay input explicit and verifies
that the snapshot action surface agrees with the frozen A/B parent labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_labels(path: Path):
    labels = {"A": {}, "B": {}}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("state_kind") != "parent" or row.get("budget") != 25000:
                continue
            replicate = row.get("replicate")
            if replicate not in labels or not row.get("teacher_valid"):
                continue
            group = row["group_id"]
            if group in labels[replicate]:
                raise ValueError(f"duplicate {replicate} parent at line {line_number}: {group}")
            actions = row.get("root_actions", [])
            if len(actions) != row.get("root_action_count"):
                raise ValueError(f"root action count mismatch: {group}")
            labels[replicate][group] = {
                "row": row,
                "actions": {action["action_fingerprint"] for action in actions},
            }
    return labels


def extract(corpus: Path, relabel: Path, output: Path) -> None:
    labels = load_labels(relabel)
    wanted = {
        group
        for group, item in labels["B"].items()
        if len(item["actions"]) > 1
    }
    if len(wanted) != 63:
        raise ValueError(f"expected 63 multi-action B anchors, found {len(wanted)}")
    if wanted - labels["A"].keys():
        raise ValueError("a selected B anchor is missing a valid 25k-A parent")

    snapshots = {}
    with corpus.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("corpus_schema") != "silver_leaf_corpus_v1":
                raise ValueError(f"unexpected corpus schema at line {line_number}")
            group = row["group_id"]
            if group not in wanted:
                continue
            envelope = row["parent_state"]
            action_fingerprints = row["parent_legal_action_fingerprints"]
            if group in snapshots:
                previous = snapshots[group]
                if previous["parent_state"] != envelope:
                    raise ValueError(f"inconsistent parent_state for {group}")
                if previous["parent_legal_action_fingerprints"] != action_fingerprints:
                    raise ValueError(f"inconsistent parent action surface for {group}")
                continue
            if set(action_fingerprints) != labels["B"][group]["actions"]:
                raise ValueError(f"B action surface mismatch for {group}")
            if set(action_fingerprints) != labels["A"][group]["actions"]:
                raise ValueError(f"A action surface mismatch for {group}")
            snapshots[group] = {
                "snapshot_schema": "silver_root_snapshot_v1",
                "group_id": group,
                "act": row["act"],
                "floor": row["floor"],
                "encounter": row["encounter"],
                "encounter_category": row["encounter_category"],
                "run_seed": row["run_seed"],
                "combat_decision_ordinal": row["combat_decision_ordinal"],
                "parent_state_hash": row["parent_state_hash"],
                "parent_legal_action_fingerprints": action_fingerprints,
                "parent_state": envelope,
            }
    if set(snapshots) != wanted:
        missing = sorted(wanted - set(snapshots))
        raise ValueError(f"missing {len(missing)} selected parent snapshots")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({
            "snapshot_schema": "silver_root_snapshot_v1",
            "selection": "valid parent replicate B budget 25000 root_action_count > 1",
            "groups": len(snapshots),
            "source_corpus": str(corpus),
            "source_relabel": str(relabel),
        }, sort_keys=True) + "\n")
        for group in sorted(snapshots):
            stream.write(json.dumps(snapshots[group], sort_keys=True, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("relabel", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    extract(args.corpus, args.relabel, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
