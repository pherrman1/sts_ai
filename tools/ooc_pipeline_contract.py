#!/usr/bin/env python3
"""Fail-closed contracts and small planning helpers for future OOC datagen."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "ooc_pipeline_v1"
TEACHER_REQUIRED = (
    "teacher_id", "git_sha", "combat_backend", "rng_regime",
    "search_configuration", "model_artifacts",
)
MANIFEST_REQUIRED = (
    "schema_version", "producer_git_sha", "combat_teacher", "seed_spec",
    "csv", "collection_timestamp", "integrity",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_budgets(text: str) -> list[int]:
    try:
        values = [int(x.strip()) for x in text.split(",")]
    except ValueError as exc:
        raise ValueError("fight budgets must be comma-separated integers") from exc
    if not values or any(v <= 0 for v in values):
        raise ValueError("fight budgets must be a non-empty list of positive integers")
    return values


def h_plan(total_branches: int, futures: list[int]) -> list[dict]:
    if total_branches <= 0 or not futures or any(h <= 0 for h in futures):
        raise ValueError("total branches and all H values must be positive")
    return [{"H": h, "distinct_state_actions": total_branches // h,
             "expensive_branches": (total_branches // h) * h} for h in futures]


def validate_teacher(teacher: dict) -> None:
    missing = [k for k in TEACHER_REQUIRED if not teacher.get(k)]
    if missing:
        raise ValueError("combat teacher is under-specified; missing: " + ", ".join(missing))
    if len(str(teacher["git_sha"])) != 40:
        raise ValueError("combat_teacher.git_sha must be a full 40-character SHA")
    search = teacher["search_configuration"]
    if not isinstance(search, dict) or not search.get("simulation_budgets"):
        raise ValueError("combat_teacher.search_configuration.simulation_budgets is required")
    artifacts = teacher["model_artifacts"]
    if not isinstance(artifacts, list):
        raise ValueError("combat_teacher.model_artifacts must be a list")
    for i, artifact in enumerate(artifacts):
        if not artifact.get("role") or len(str(artifact.get("sha256", ""))) != 64:
            raise ValueError(f"combat_teacher.model_artifacts[{i}] requires role and SHA256")


def validate_manifest(manifest: dict, verify_csv: bool = True) -> None:
    missing = [k for k in MANIFEST_REQUIRED if not manifest.get(k)]
    if missing:
        raise ValueError("corpus manifest missing: " + ", ".join(missing))
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {manifest['schema_version']!r}")
    validate_teacher(manifest["combat_teacher"])
    csv_info = manifest["csv"]
    if not csv_info.get("path") or len(str(csv_info.get("sha256", ""))) != 64:
        raise ValueError("csv.path and csv.sha256 are required")
    if verify_csv:
        path = Path(csv_info["path"])
        if not path.is_file() or sha256(path) != csv_info["sha256"]:
            raise ValueError("CSV is missing or its SHA256 does not match the manifest")
    integrity = manifest["integrity"]
    for key in ("requested_runs", "completed_runs", "quarantined_runs", "rows"):
        if key not in integrity or int(integrity[key]) < 0:
            raise ValueError(f"integrity.{key} must be a nonnegative integer")


def make_manifest(args: argparse.Namespace) -> dict:
    teacher = json.loads(Path(args.teacher).read_text(encoding="utf-8"))
    validate_teacher(teacher)
    csv_path = Path(args.csv).resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "producer_git_sha": args.producer_sha,
        "producer_executable_sha256": args.executable_sha256,
        "combat_teacher": teacher,
        "seed_spec": json.loads(args.seed_spec),
        "csv": {"path": str(csv_path), "sha256": sha256(csv_path)},
        "collection_timestamp": datetime.now(timezone.utc).isoformat(),
        "integrity": {"requested_runs": args.requested, "completed_runs": args.completed,
                      "quarantined_runs": args.quarantined, "rows": args.rows,
                      "summary": args.integrity_summary},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("manifest")
    p.add_argument("--no-csv-check", action="store_true")
    p = sub.add_parser("budgets")
    p.add_argument("schedule")
    p = sub.add_parser("h-plan")
    p.add_argument("total_branches", type=int)
    p.add_argument("--futures", default="1,2,4")
    p = sub.add_parser("make-manifest")
    p.add_argument("--teacher", required=True); p.add_argument("--csv", required=True)
    p.add_argument("--output", required=True); p.add_argument("--producer-sha", required=True)
    p.add_argument("--executable-sha256"); p.add_argument("--seed-spec", required=True)
    p.add_argument("--requested", type=int, required=True); p.add_argument("--completed", type=int, required=True)
    p.add_argument("--quarantined", type=int, required=True); p.add_argument("--rows", type=int, required=True)
    p.add_argument("--integrity-summary", default="")
    args = ap.parse_args()
    if args.command == "check":
        validate_manifest(json.loads(Path(args.manifest).read_text(encoding="utf-8")), not args.no_csv_check)
        print("ooc corpus manifest: OK")
    elif args.command == "budgets":
        values = parse_budgets(args.schedule)
        print(json.dumps({"fight_budgets": values, "prefixes": [values[:i] for i in range(1, len(values)+1)],
                          "total_simulations": sum(values)}))
    elif args.command == "h-plan":
        print(json.dumps(h_plan(args.total_branches, parse_budgets(args.futures)), indent=2))
    else:
        manifest = make_manifest(args); validate_manifest(manifest)
        Path(args.output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
