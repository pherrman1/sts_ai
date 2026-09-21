#!/usr/bin/env python3
"""Deterministically analyze the frozen Silver internal-FPU replay cohort."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


IMPLEMENTATION_SHA = "c9f58c20cd4879584fbe0d78828d33057350d914"
SNAPSHOT_SHA256 = "ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae"
FULL_BINARY_SHA256 = "a416d451279cc8d9324240e67f615fff56f52d307b8c14a07a91650ef96d7311"
FIRST_DECISION_BINARY_SHA256 = "d7a343f6e8e57bb48929443707bb8e63850f4c501fa31a203126a35713dcc722"
THREADS = 4

CONFIG = {
    "exploration_parameter": 25.0,
    "exploration_parameter_chance": 25.0,
    "chance_widening_c": 3.7028,
    "chance_widening_alpha": 0.52389,
    "end_turn_widening_c": 3.7028,
    "end_turn_widening_alpha": 0.52389,
    "reuse_cap": 32768,
    "reuse_cap_mode": "ALLOCATED",
    "adaptive": False,
    "exact_lock": False,
    "rho": False,
    "contract_mode": "CONTROL",
    "collect_rollout_diagnostics": False,
    "collect_uid_fragmentation_diagnostics": False,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> tuple[list[dict], str]:
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rb") as stream:
        for raw in stream:
            digest.update(raw)
            if raw.strip():
                rows.append(json.loads(raw))
    return rows, digest.hexdigest()


def by_case(rows: list[dict], label: str, expected_statuses: set[str]) -> dict[str, dict]:
    if len(rows) != 64:
        raise ValueError(f"{label}: expected 64 rows, got {len(rows)}")
    result = {}
    for row in rows:
        case_id = row.get("case_id")
        if not case_id or case_id in result:
            raise ValueError(f"{label}: duplicate or missing case_id: {case_id!r}")
        if row.get("status") not in expected_statuses:
            raise ValueError(f"{label}: unexpected status for {case_id}: {row.get('status')!r}")
        result[case_id] = row
    return result


def total(rows: dict[str, dict], field: str) -> int | float:
    return sum(row.get(field, 0) for row in rows.values())


def mean(rows: dict[str, dict], field: str, cases: set[str] | None = None) -> float:
    selected = [row for case, row in rows.items() if cases is None or case in cases]
    return sum(row.get(field, 0) for row in selected) / len(selected) if selected else 0.0


def compact_action(action: str) -> str:
    return action or "<none>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--snapshots", type=Path,
                        default=Path("docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl"))
    parser.add_argument("--table", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    root = args.root

    snapshots = [json.loads(line) for line in args.snapshots.read_text().splitlines() if line.strip()]
    if len(snapshots) != 64:
        raise ValueError(f"snapshot cohort is not 64 rows: {len(snapshots)}")
    snapshot_by_case = by_case(snapshots, "snapshots", {None})
    snapshot_hash = sha256_file(args.snapshots)
    if snapshot_hash != SNAPSHOT_SHA256:
        raise ValueError(f"snapshot SHA mismatch: {snapshot_hash}")

    paths = {
        "control_1k": root / "raw/full_control_1k.jsonl.gz",
        "fpu_1k": root / "raw/full_fpu_1k.jsonl.gz",
        "control_10k": root / "raw/full_control_10k.jsonl.gz",
        "fpu_10k": root / "raw/full_fpu_10k.jsonl.gz",
        "first_control_1k": root / "first_decision/first_control_1k.jsonl.gz",
        "first_fpu_1k": root / "first_decision/first_fpu_1k.jsonl.gz",
        "first_control_10k": root / "first_decision/first_control_10k.jsonl.gz",
        "first_fpu_10k": root / "first_decision/first_fpu_10k.jsonl.gz",
    }
    loaded = {}
    raw_hashes = {}
    for label, path in paths.items():
        rows, raw_hashes[label] = load_jsonl(path)
        loaded[label] = by_case(rows, label, {"ok"} if not label.startswith("first_")
                                 else {"ok", "transactional_selection_required"})

    for label, rows in loaded.items():
        for case_id, row in rows.items():
            snapshot = snapshot_by_case[case_id]
            if row.get("state_hash") != snapshot["state_hash"]:
                raise ValueError(f"{label}/{case_id}: state hash mismatch")

    full_labels = ["control_1k", "fpu_1k", "control_10k", "fpu_10k"]
    first_labels = ["first_control_1k", "first_fpu_1k", "first_control_10k", "first_fpu_10k"]
    config_hash = hashlib.sha256(json.dumps(CONFIG, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    c1, f1, c10, f10 = (loaded[label] for label in full_labels)
    case_ids = sorted(c1)
    root_agreement = {
        "control_1k_vs_control_10k": sum(c1[c]["first_action_fingerprint"] == c10[c]["first_action_fingerprint"] for c in case_ids),
        "fpu_1k_vs_control_10k": sum(f1[c]["first_action_fingerprint"] == c10[c]["first_action_fingerprint"] for c in case_ids),
        "control_1k_vs_fpu_1k": sum(c1[c]["first_action_fingerprint"] == f1[c]["first_action_fingerprint"] for c in case_ids),
    }
    disagreements = []
    for case_id in case_ids:
        control_action = c1[case_id]["first_action_fingerprint"]
        fpu_action = f1[case_id]["first_action_fingerprint"]
        reference_action = c10[case_id]["first_action_fingerprint"]
        if control_action == fpu_action:
            continue
        control_matches = control_action == reference_action
        fpu_matches = fpu_action == reference_action
        direction = ("toward" if fpu_matches and not control_matches else
                     "away" if control_matches and not fpu_matches else "both_off")
        disagreements.append({
            "case_id": case_id,
            "direction": direction,
            "control_matches_10k_control": control_matches,
            "fpu_matches_10k_control": fpu_matches,
            "control_1k_action": control_action,
            "fpu_1k_action": fpu_action,
            "control_10k_action": reference_action,
        })

    full_aggregates = {}
    for label in full_labels:
        rows = loaded[label]
        full_aggregates[label] = {
            "accepted": sum(row["status"] == "ok" for row in rows.values()),
            "wins": sum(bool(row.get("won")) for row in rows.values()),
            "simulations": total(rows, "simulations"),
            "nodes_created": total(rows, "nodes_created"),
            "depth_sum": total(rows, "depth_sum"),
            "chance_depth_sum": total(rows, "chance_depth_sum"),
            "search_wall_micros": total(rows, "search_wall_micros"),
            "hp_end_sum": total(rows, "hp_end"),
            "decisions": total(rows, "decisions"),
            "fpu_selection_opportunities": total(rows, "fpu_selection_opportunities"),
            "fpu_visited_selected_with_unvisited_remaining": total(rows, "fpu_visited_selected_with_unvisited_remaining"),
            "fpu_unvisited_selected": total(rows, "fpu_unvisited_selected"),
        }

    first_aggregates = {}
    first_pairs = {}
    for budget in ("1k", "10k"):
        control = loaded[f"first_control_{budget}"]
        fpu = loaded[f"first_fpu_{budget}"]
        control_ok = {case for case, row in control.items() if row["status"] == "ok"}
        fpu_ok = {case for case, row in fpu.items() if row["status"] == "ok"}
        common = control_ok & fpu_ok
        if control_ok != fpu_ok:
            raise ValueError(f"first-decision eligible sets differ for {budget}")
        for case_id in common:
            if control[case_id]["first_action_fingerprint"] != c1[case_id]["first_action_fingerprint"] if budget == "1k" else control[case_id]["first_action_fingerprint"] != c10[case_id]["first_action_fingerprint"]:
                raise ValueError(f"first-decision control action mismatch for {budget}/{case_id}")
            if fpu[case_id]["first_action_fingerprint"] != f1[case_id]["first_action_fingerprint"] if budget == "1k" else fpu[case_id]["first_action_fingerprint"] != f10[case_id]["first_action_fingerprint"]:
                raise ValueError(f"first-decision FPU action mismatch for {budget}/{case_id}")
        first_aggregates[budget] = {
            "eligible_common_cases": len(common),
            "excluded_transactional_cases": 64 - len(common),
            "control_status_counts": dict(Counter(row["status"] for row in control.values())),
            "fpu_status_counts": dict(Counter(row["status"] for row in fpu.values())),
            "control": {
                "mean_nodes_created": mean(control, "nodes_created", common),
                "mean_depth_sum": mean(control, "depth_sum", common),
                "mean_chance_depth_sum": mean(control, "chance_depth_sum", common),
                "mean_search_wall_micros": mean(control, "search_wall_micros", common),
                "fpu_selection_opportunities": total({c: control[c] for c in common}, "fpu_selection_opportunities"),
            },
            "fpu": {
                "mean_nodes_created": mean(fpu, "nodes_created", common),
                "mean_depth_sum": mean(fpu, "depth_sum", common),
                "mean_chance_depth_sum": mean(fpu, "chance_depth_sum", common),
                "mean_search_wall_micros": mean(fpu, "search_wall_micros", common),
                "fpu_selection_opportunities": total({c: fpu[c] for c in common}, "fpu_selection_opportunities"),
                "fpu_visited_selected_with_unvisited_remaining": total({c: fpu[c] for c in common}, "fpu_visited_selected_with_unvisited_remaining"),
                "fpu_unvisited_selected": total({c: fpu[c] for c in common}, "fpu_unvisited_selected"),
            },
            "paired_delta_fpu_minus_control": {
                "mean_nodes_created": mean({c: {"value": fpu[c]["nodes_created"] - control[c]["nodes_created"]} for c in common}, "value"),
                "mean_depth_sum": mean({c: {"value": fpu[c]["depth_sum"] - control[c]["depth_sum"]} for c in common}, "value"),
                "mean_chance_depth_sum": mean({c: {"value": fpu[c]["chance_depth_sum"] - control[c]["chance_depth_sum"]} for c in common}, "value"),
                "mean_search_wall_micros": mean({c: {"value": fpu[c]["search_wall_micros"] - control[c]["search_wall_micros"]} for c in common}, "value"),
            },
        }
        first_pairs[budget] = sorted(common)

    table_fields = ["case_id", "source_seed", "fight_index", "benchmark_seed", "state_hash",
                    "executable_git_sha", "silver_upstream_sha"]
    for label in full_labels:
        table_fields += [f"{label}_{field}" for field in
                         ("status", "first_action_fingerprint", "won", "hp_end", "max_hp",
                          "turns", "simulations", "nodes_created", "depth_sum", "chance_depth_sum",
                          "search_wall_micros", "fpu_selection_opportunities",
                          "fpu_visited_selected_with_unvisited_remaining", "fpu_unvisited_selected")]
    table_fields += ["root_control_1k_matches_control_10k", "root_fpu_1k_matches_control_10k",
                     "root_1k_control_fpu_agree", "root_disagreement_direction"]
    table_rows = []
    for case_id in case_ids:
        snapshot = snapshot_by_case[case_id]
        row = {field: snapshot.get(field, "") for field in table_fields[:7]}
        for label in full_labels:
            source = loaded[label][case_id]
            for field in table_fields:
                if field.startswith(label + "_"):
                    row[field] = source.get(field[len(label) + 1:], "")
        row["root_control_1k_matches_control_10k"] = c1[case_id]["first_action_fingerprint"] == c10[case_id]["first_action_fingerprint"]
        row["root_fpu_1k_matches_control_10k"] = f1[case_id]["first_action_fingerprint"] == c10[case_id]["first_action_fingerprint"]
        row["root_1k_control_fpu_agree"] = c1[case_id]["first_action_fingerprint"] == f1[case_id]["first_action_fingerprint"]
        row["root_disagreement_direction"] = next((item["direction"] for item in disagreements if item["case_id"] == case_id), "agree")
        table_rows.append(row)

    summary = {
        "implementation_sha": IMPLEMENTATION_SHA,
        "snapshot_sha256": snapshot_hash,
        "full_binary_sha256": FULL_BINARY_SHA256,
        "first_decision_binary_sha256": FIRST_DECISION_BINARY_SHA256,
        "threads": THREADS,
        "config": CONFIG,
        "config_sha256": config_hash,
        "raw_jsonl_sha256": raw_hashes,
        "cohort_rows": 64,
        "full_aggregates": full_aggregates,
        "primary_root_metric": {
            "agreement_control_1k_control_10k": f"{root_agreement['control_1k_vs_control_10k']}/64",
            "agreement_fpu_1k_control_10k": f"{root_agreement['fpu_1k_vs_control_10k']}/64",
            "agreement_control_1k_fpu_1k": f"{root_agreement['control_1k_vs_fpu_1k']}/64",
            "one_k_disagreement_count": len(disagreements),
            "direction_counts": dict(Counter(item["direction"] for item in disagreements)),
            "disagreements": disagreements,
        },
        "first_decision": first_aggregates,
        "first_decision_pair_case_ids": first_pairs,
    }

    table_path = args.table or root / "frozen_per_case.csv"
    with table_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=table_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table_rows)
    summary_path = args.summary or root / "frozen_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    markdown_path = args.markdown or root / "frozen_summary.md"
    primary = summary["primary_root_metric"]
    lines = [
        "# Frozen Silver internal-FPU cohort summary",
        "",
        f"Implementation SHA: `{IMPLEMENTATION_SHA}`",
        f"Snapshot SHA-256: `{snapshot_hash}`",
        f"Configuration SHA-256: `{config_hash}`",
        "",
        "## Preregistered primary root metric",
        "",
        "| Comparison | Agreement |",
        "|---|---:|",
        f"| 1k CONTROL vs 10k CONTROL | {primary['agreement_control_1k_control_10k']} |",
        f"| 1k FPU vs 10k CONTROL | {primary['agreement_fpu_1k_control_10k']} |",
        "",
        f"The 1k CONTROL/FPU root actions disagreed in `{primary['one_k_disagreement_count']}/64` cases.",
        "",
        "| Case | Direction relative to 10k CONTROL |",
        "|---|---|",
    ]
    for item in disagreements:
        lines.append(f"| `{item['case_id']}` | `{item['direction']}` |")
    lines += [
        "",
        "## Full-combat outcome and trajectory totals",
        "",
        "These totals are descriptive only. Once initial root actions differ, nodes, depth, wall time, and simulations are trajectory-confounded and are not interpreted as causal FPU efficiency gains.",
        "",
        "| Arm | Accepted | Wins | Simulations | Nodes | Depth | Chance depth | Search wall ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in full_labels:
        agg = full_aggregates[label]
        lines.append(f"| {label} | {agg['accepted']}/64 | {agg['wins']}/64 | {agg['simulations']:,} | {agg['nodes_created']:,} | {agg['depth_sum']:,} | {agg['chance_depth_sum']:,} | {agg['search_wall_micros'] / 1000:,.3f} |")
    lines += [
        "",
        "## First-decision paired efficiency",
        "",
        "The first-decision probe excludes the five transactional `CARD_SELECT` roots, which are handled by the transactional replay path. Values below use the 59 common ordinary-root cases and are paired by case.",
        "",
        "| Budget | Cases | CONTROL mean nodes | FPU mean nodes | CONTROL mean wall us | FPU mean wall us | Mean FPU minus CONTROL wall us |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for budget in ("1k", "10k"):
        agg = first_aggregates[budget]
        lines.append(f"| {budget} | {agg['eligible_common_cases']}/64 | {agg['control']['mean_nodes_created']:.2f} | {agg['fpu']['mean_nodes_created']:.2f} | {agg['control']['mean_search_wall_micros']:.3f} | {agg['fpu']['mean_search_wall_micros']:.3f} | {agg['paired_delta_fpu_minus_control']['mean_search_wall_micros']:.3f} |")
    lines += [
        "",
        "First-decision wall time is diagnostic and machine-dependent; it is reported separately from whole-combat totals and is not a production-performance qualification.",
        "",
        "## Provenance",
        "",
        "- All four full-combat arms: `OMP_NUM_THREADS=4 bash tools/seed_guard.sh build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl BUDGET --arm control [--internal-fpu]`.",
        "- First-decision diagnostics used the same command with `--first-decision-only`; this is measurement-only harness output and does not change FPU/search policy.",
        "- Full-combat binary SHA-256: `" + FULL_BINARY_SHA256 + "`.",
        "- First-decision binary SHA-256: `" + FIRST_DECISION_BINARY_SHA256 + "`.",
        "- Fixed config hash: `" + config_hash + "`.",
        "- Raw compressed JSONL and decompressed-content hashes are recorded in `frozen_summary.json`.",
    ]
    markdown_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
