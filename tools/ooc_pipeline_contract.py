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
    "teacher_id", "git_sha", "executable_sha256", "combat_backend", "rng_regime",
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
    if len(str(teacher["executable_sha256"])) != 64:
        raise ValueError("combat_teacher.executable_sha256 must be a SHA256")
    search = teacher["search_configuration"]
    frozen_search = {"simulation_budgets": [10000], "exploration_parameter": 25.0,
                     "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
                     "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
                     "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
                     "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
                     "learned_visit_puct": False, "direct_learned_leaf": False,
                     "adaptive": False}
    if not isinstance(search, dict):
        raise ValueError("combat_teacher.search_configuration must be an object")
    for key, expected in frozen_search.items():
        if search.get(key) != expected:
            raise ValueError(f"combat_teacher.search_configuration.{key} must be {expected!r}")
    required_env = {"STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
                    "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
                    "STS_SILVER_REUSE_CAP_MODE": "allocated", "STS_SILVER_ADAPTIVE": "0",
                    "STS_SILVER_VNET_LEAF_DIRECT": "0", "STS_SILVER_TELEMETRY": "1"}
    environment = teacher.get("environment")
    if not isinstance(environment, dict):
        raise ValueError("combat_teacher.environment must be an object")
    for key, expected in required_env.items():
        if environment.get(key) != expected:
            raise ValueError(f"combat_teacher.environment.{key} must be {expected!r}")
    artifacts = teacher["model_artifacts"]
    if not isinstance(artifacts, list):
        raise ValueError("combat_teacher.model_artifacts must be a list")
    for i, artifact in enumerate(artifacts):
        if not artifact.get("role") or not artifact.get("path") or len(str(artifact.get("sha256", ""))) != 64:
            raise ValueError(f"combat_teacher.model_artifacts[{i}] requires role, path, and SHA256")


def validate_corpus(manifest: dict) -> dict:
    import math
    validate_manifest(manifest)
    path = Path(manifest["csv"]["path"])
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        prefix = ["sourceSeed", "fightIdx", "act", "floor", "encounter", "roomClass", "decisionIdx", "teacherId"]
        if header[:len(prefix)] != prefix or "won" not in header:
            raise ValueError("whole-combat CSV metadata/target boundary is invalid")
        won_idx = header.index("won")
        features = header[len(prefix):won_idx]
        if len(features) != 1766 or len(set(features)) != 1766:
            raise ValueError(f"expected exactly 1766 unique canonical features, got {len(features)}")
        required = {"endHp", "startHp", "startMaxHp", "endMaxHp", "endHpFrac",
                    "startPotionIds", "endPotionIds", "startPotionCount", "endPotionCount",
                    "goldDelta", "smokeBombUsed", "changedRelicCounters", "ritualDaggerChanges",
                    "deckStructureChanged", "parasiteAdded", "persistentMutationSummary"}
        if missing := sorted(required - set(header)):
            raise ValueError("whole-combat CSV missing targets/diagnostics: " + ", ".join(missing))
        rows = list(reader)
    teacher_id = manifest["combat_teacher"]["teacher_id"]
    keys, seeds = set(), set(); wins = 0; acts = {}; rooms = {}; invalid = []
    for line, row in enumerate(rows, 2):
        try:
            seed, fight = int(row["sourceSeed"]), int(row["fightIdx"])
            key = (seed, fight)
            if key in keys: raise ValueError("duplicate sourceSeed/fightIdx")
            keys.add(key); seeds.add(seed)
            if int(row["decisionIdx"]) != 0: raise ValueError("decisionIdx is not zero")
            if row["teacherId"] != teacher_id: raise ValueError("teacherId mismatch")
            values = [float(row[name]) for name in features]
            if not all(math.isfinite(v) for v in values): raise ValueError("non-finite feature")
            won = int(row["won"])
            if won not in (0, 1): raise ValueError("won is not binary")
            for name in ("endHp", "startHp", "startMaxHp", "endMaxHp", "endHpFrac"):
                if not math.isfinite(float(row[name])): raise ValueError(f"non-finite {name}")
            wins += won; acts[row["act"]] = acts.get(row["act"], 0) + 1
            rooms[row["roomClass"]] = rooms.get(row["roomClass"], 0) + 1
        except Exception as exc:
            invalid.append({"line": line, "reason": str(exc)})
    if invalid: raise ValueError(f"whole-combat corpus has {len(invalid)} invalid rows; first={invalid[0]}")
    integrity = manifest["integrity"]
    if len(rows) != int(integrity["rows"]): raise ValueError("manifest row count mismatch")
    if len(seeds) != int(integrity["completed_runs"]): raise ValueError("manifest completed_runs/unique seeds mismatch")
    return {"rows": len(rows), "source_seeds": len(seeds), "wins": wins,
            "losses": len(rows)-wins, "loss_fraction": (len(rows)-wins)/len(rows) if rows else None,
            "act_distribution": acts, "room_distribution": rooms,
            "feature_count": len(features), "teacher_id": teacher_id,
            "requested_runs": int(integrity["requested_runs"]),
            "completed_runs": int(integrity["completed_runs"]),
            "quarantined_runs": int(integrity["quarantined_runs"])}


def validate_manifest(manifest: dict, verify_csv: bool = True) -> None:
    missing = [k for k in MANIFEST_REQUIRED if not manifest.get(k)]
    if missing:
        raise ValueError("corpus manifest missing: " + ", ".join(missing))
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {manifest['schema_version']!r}")
    validate_teacher(manifest["combat_teacher"])
    if len(str(manifest.get("producer_executable_sha256", ""))) != 64:
        raise ValueError("producer_executable_sha256 is required")
    if manifest["producer_executable_sha256"] != manifest["combat_teacher"]["executable_sha256"]:
        raise ValueError("producer executable hash disagrees with combat teacher")
    if manifest["producer_git_sha"] != manifest["combat_teacher"]["git_sha"]:
        raise ValueError("producer SHA disagrees with combat teacher SHA")
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
    p = sub.add_parser("validate-corpus")
    p.add_argument("manifest")
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
    elif args.command == "validate-corpus":
        print(json.dumps(validate_corpus(json.loads(Path(args.manifest).read_text(encoding="utf-8"))), indent=2, sort_keys=True))
    elif args.command == "h-plan":
        print(json.dumps(h_plan(args.total_branches, parse_budgets(args.futures)), indent=2))
    else:
        manifest = make_manifest(args); validate_manifest(manifest)
        Path(args.output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
