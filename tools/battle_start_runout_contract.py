#!/usr/bin/env python3
"""Fail-closed contract for the joined battle-start V_win/L corpus."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from tools.combat_evaluator_contract import (
        FROZEN_TEACHER,
        LABELS,
        PREFIX,
        EXPECTED_STATE_FEATURE_COUNT,
        _validate_teacher,
        sha256,
        validate_label_row,
    )
    from tools.ooc_semantic_pipeline_contract import RICH_NAMES
except ModuleNotFoundError:
    from combat_evaluator_contract import (
        FROZEN_TEACHER,
        LABELS,
        PREFIX,
        EXPECTED_STATE_FEATURE_COUNT,
        _validate_teacher,
        sha256,
        validate_label_row,
    )
    from ooc_semantic_pipeline_contract import RICH_NAMES


SCHEMA_VERSION = "battle_start_runout_v1"
DATASET_ROLES = {"primary_corrected_vwin_l", "heuristic_policy_auxiliary"}
RUNOUT_HEADER = [
    "sourceSeed", "finalOutcome", "finalWon", "finalFloor", "finalHp",
    "fightCount", "trajectoryComplete", "trajectoryValid", "combatRows",
    "invalidCombatRows", "teacherId", "simulatorHealthFailures", "fatalFailure",
]
EXPECTED_HEADER = PREFIX + list(RICH_NAMES) + LABELS
STATE_ORDER_SHA256 = hashlib.sha256("\n".join(RICH_NAMES).encode()).hexdigest()
HEADER_SHA256 = hashlib.sha256(",".join(EXPECTED_HEADER).encode()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hash(value: object, name: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"invalid {name}")


def _integer(value: object, name: str) -> int:
    require(not isinstance(value, bool) and re.fullmatch(r"-?\d+", str(value)) is not None,
            f"invalid {name}")
    return int(value)


def _binary(value: object, name: str) -> int:
    result = _integer(value, name)
    require(result in (0, 1), f"{name} must be 0 or 1")
    return result


def _finite(value: object, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    require(math.isfinite(result), f"non-finite {name}")
    return result


def _bound_file(info: object, name: str) -> Path:
    require(isinstance(info, dict) and isinstance(info.get("path"), str) and info["path"],
            f"missing {name} path")
    _hash(info.get("sha256"), f"{name} hash")
    path = Path(info["path"])
    require(path.is_file() and sha256(path) == info["sha256"], f"{name} hash mismatch")
    return path


def _read_combat(path: Path) -> tuple[list[dict], dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        require(header == EXPECTED_HEADER, "canonical combat header/order mismatch")
        raw_rows = list(reader)
    rows = []
    seen = set()
    counts = Counter(valid=0, invalid=0, ambiguous=0, wins=0, deaths=0,
                    escapes=0, turnCapLoss=0)
    for line, cells in enumerate(raw_rows, 2):
        require(len(cells) == len(EXPECTED_HEADER), f"combat CSV width mismatch at line {line}")
        feature_cells = cells[len(PREFIX):len(PREFIX) + len(RICH_NAMES)]
        for name, value in zip(RICH_NAMES, feature_cells):
            _finite(value, name)
        # The canonical state repeats act/floor in the metadata prefix.
        for name in ("act", "floor"):
            meta = cells[PREFIX.index(name)]
            state = feature_cells[RICH_NAMES.index(name)]
            require(_finite(meta, name) == _finite(state, name),
                    f"metadata/state {name} mismatch at line {line}")
        row = dict(zip(EXPECTED_HEADER, cells))
        key = (_integer(row["sourceSeed"], "sourceSeed"),
               _integer(row["fightIdx"], "fightIdx"))
        require(key not in seen, "duplicate combat identity: (sourceSeed, fightIdx)")
        seen.add(key)
        bits = validate_label_row(row, line)
        valid = bits["labelValid"]
        counts["valid" if valid else "invalid"] += 1
        counts["ambiguous"] += bits["progressAmbiguous"]
        counts["wins"] += bits["won"] * valid
        counts["deaths"] += bits["trueDeath"] * valid
        counts["escapes"] += bits["escaped"]
        counts["turnCapLoss"] += bits["turnCapLoss"]
        rows.append(row)
    seeds = {int(row["sourceSeed"]) for row in rows}
    return rows, {
        "rows": len(rows), "source_seeds": len(seeds),
        "counts": dict(counts), "features": list(RICH_NAMES),
        "csv_sha256": sha256(path),
    }


def _read_runout(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        require(next(reader, []) == RUNOUT_HEADER, "run-out header/order mismatch")
        rows = []
        for line, cells in enumerate(reader, 2):
            require(len(cells) == len(RUNOUT_HEADER), f"run-out CSV width mismatch at line {line}")
            rows.append(dict(zip(RUNOUT_HEADER, cells)))
    seen = set()
    for line, row in enumerate(rows, 2):
        require(len(row) == len(RUNOUT_HEADER), f"run-out CSV width mismatch at line {line}")
        seed = _integer(row["sourceSeed"], "run-out sourceSeed")
        require(seed >= 0 and seed not in seen, "missing/duplicate source run identity")
        seen.add(seed)
        outcome = row["finalOutcome"]
        require(outcome in ("PLAYER_VICTORY", "PLAYER_LOSS", "UNDECIDED"),
                "impossible final outcome")
        final_won = _integer(row["finalWon"], "finalWon")
        require(final_won == {"PLAYER_VICTORY": 1, "PLAYER_LOSS": 0, "UNDECIDED": -1}[outcome],
                "finalWon/finalOutcome mismatch")
        for name in ("finalFloor", "finalHp", "fightCount", "combatRows", "invalidCombatRows",
                     "simulatorHealthFailures"):
            require(_integer(row[name], name) >= 0, f"negative {name}")
        complete = _binary(row["trajectoryComplete"], "trajectoryComplete")
        valid = _binary(row["trajectoryValid"], "trajectoryValid")
        fatal = _binary(row["fatalFailure"], "fatalFailure")
        require(complete == int(outcome != "UNDECIDED"), "trajectoryComplete/finalOutcome mismatch")
        require(not valid or (complete and not fatal and row["simulatorHealthFailures"] == "0"),
                "trajectoryValid is inconsistent with health/fatal status")
        require(isinstance(row["teacherId"], str) and bool(row["teacherId"]),
                "missing run-out teacherId")
    return rows


def _validate_feature_contract(contract: object) -> None:
    require(isinstance(contract, dict), "missing feature contract")
    require(contract.get("count") == EXPECTED_STATE_FEATURE_COUNT,
            "canonical feature width mismatch")
    require(contract.get("state_names") == list(RICH_NAMES),
            "canonical feature names/order mismatch")
    require(contract.get("state_order_sha256") == STATE_ORDER_SHA256,
            "canonical state order hash mismatch")
    require(contract.get("header_sha256") == HEADER_SHA256,
            "canonical header hash mismatch")


def _validate_teacher_binding(teacher: dict) -> None:
    _validate_teacher(teacher)
    expected_environment = {
        "STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
        "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
        "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
        "STS_SILVER_TELEMETRY": "1",
    }
    require(teacher.get("environment") == expected_environment,
            "teacher environment is not the frozen ordinary Silver contract")
    artifacts = teacher.get("model_artifacts")
    require(isinstance(artifacts, list) and artifacts, "teacher has no loaded model hashes")
    roles = set()
    for artifact in artifacts:
        require(isinstance(artifact, dict), "invalid teacher model artifact")
        role, path, digest = artifact.get("role"), artifact.get("path"), artifact.get("sha256")
        require(isinstance(role, str) and role and role not in roles, "invalid/duplicate teacher model role")
        require(isinstance(path, str) and path, "teacher model artifact is missing path")
        _hash(digest, "teacher model artifact SHA256")
        require(Path(path).is_file(), "teacher model artifact is missing")
        require(sha256(path) == digest, "teacher model artifact hash mismatch")
        roles.add(role)
    policy = teacher.get("ooc_policy")
    require(isinstance(policy, dict), "teacher is missing effective OOC policy")
    require(policy.get("schema_version") == "runFullRunOOC_policy_v1",
            "unsupported effective OOC policy schema")
    require(policy.get("policy_chain") == "runFullRunOOC",
            "effective OOC policy chain mismatch")
    require(policy.get("restV") is False and policy.get("shopV") is True,
            "effective OOC horizon flags mismatch")
    require(isinstance(policy.get("flags"), dict) and isinstance(policy.get("parameters"), dict),
            "effective OOC policy configuration is incomplete")
    ooc_artifacts = policy.get("model_artifacts")
    require(isinstance(ooc_artifacts, list) and ooc_artifacts,
            "effective OOC policy has no model artifacts")
    ooc_roles = set()
    for artifact in ooc_artifacts:
        require(isinstance(artifact, dict), "invalid effective OOC model artifact")
        role, path, digest = artifact.get("role"), artifact.get("path"), artifact.get("sha256")
        require(isinstance(role, str) and role and role not in ooc_roles,
                "invalid/duplicate effective OOC model role")
        require(isinstance(path, str) and path, "effective OOC model artifact is missing path")
        _hash(digest, "effective OOC model artifact SHA256")
        require(Path(path).is_file() and sha256(path) == digest,
                "effective OOC model artifact hash mismatch")
        ooc_roles.add(role)


def _stable_split(seeds: set[int]) -> dict[int, str]:
    groups = {}
    for seed in sorted(seeds):
        h = int(hashlib.sha256(f"combat-evaluator-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32
        groups[seed] = "train" if h < .70 else "validation" if h < .85 else "test"
    return groups


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {name: None for name in ("min", "p05", "p25", "median", "p75", "p95", "max")}
    values = sorted(values)
    def q(fraction: float) -> float:
        position = (len(values) - 1) * fraction
        lower, upper = math.floor(position), math.ceil(position)
        if lower == upper:
            return values[lower]
        return values[lower] + (values[upper] - values[lower]) * (position - lower)
    return {"min": values[0], "p05": q(.05), "p25": q(.25), "median": q(.5),
            "p75": q(.75), "p95": q(.95), "max": values[-1]}


def _floor_band(floor: int) -> str:
    return "1-5" if floor <= 5 else "6-10" if floor <= 10 else "11-15" if floor <= 15 else "16-25" if floor <= 25 else "26+"


def _hp_band(row: dict) -> str:
    hp = float(row["curHp"])
    maximum = float(row["maxHp"])
    fraction = hp / maximum if maximum > 0 else 0.0
    return "<0.25" if fraction < .25 else "0.25-0.50" if fraction < .50 else "0.50-0.75" if fraction < .75 else ">=0.75"


def _coverage(combat_rows: list[dict], runout_rows: list[dict], seed_to_run: dict[int, dict]) -> dict:
    valid_sources = {seed for seed, row in seed_to_run.items() if row["trajectoryValid"] == "1"}
    vwin = [row for row in combat_rows if int(row["sourceSeed"]) in valid_sources]
    deaths = [row for row in vwin if row["labelValid"] == "1" and row["trueDeath"] == "1" and row["progressAmbiguous"] == "0"]
    final_wins = sum(row["finalOutcome"] == "PLAYER_VICTORY" for row in runout_rows)
    final_losses = sum(row["finalOutcome"] == "PLAYER_LOSS" for row in runout_rows)
    source_wins = sum(row["finalOutcome"] == "PLAYER_VICTORY" for row in runout_rows if row["trajectoryValid"] == "1")
    source_losses = sum(row["finalOutcome"] == "PLAYER_LOSS" for row in runout_rows if row["trajectoryValid"] == "1")
    by = {name: Counter() for name in ("act", "roomClass", "encounter", "floorBand", "fightIdx")}
    for row in vwin:
        by["act"][row["act"]] += 1
        by["roomClass"][row["roomClass"]] += 1
        by["encounter"][row["encounter"]] += 1
        by["floorBand"][_floor_band(int(row["floor"]))] += 1
        by["fightIdx"][row["fightIdx"]] += 1
    rows_by_source = Counter(int(row["sourceSeed"]) for row in vwin)
    death_by = {name: Counter() for name in ("act", "roomClass", "encounter", "hpFractionBand")}
    for row in deaths:
        death_by["act"][row["act"]] += 1
        death_by["roomClass"][row["roomClass"]] += 1
        death_by["encounter"][row["encounter"]] += 1
        death_by["hpFractionBand"][_hp_band(row)] += 1
    splits = _stable_split(set(seed_to_run)) if len(seed_to_run) >= 4 else {}
    if set(splits.values()) != {"train", "validation", "test"}:
        split_counts = {"status": "insufficient_source_support"}
    else:
        split_counts = {}
        for split in ("train", "validation", "test"):
            source_rows = [row for row in runout_rows if splits[int(row["sourceSeed"])] == split]
            row_rows = [row for row in vwin if splits[int(row["sourceSeed"])] == split]
            eligible_deaths = [row for row in deaths if splits[int(row["sourceSeed"])] == split]
            split_counts[split] = {
                "source_seeds": len(source_rows),
                "wins": sum(row["finalOutcome"] == "PLAYER_VICTORY" for row in source_rows),
                "losses": sum(row["finalOutcome"] == "PLAYER_LOSS" for row in source_rows),
                "battle_start_rows": len(row_rows),
                "l_eligible_deaths": len(eligible_deaths),
            }
    return {
        "source_trajectories": {"requested": len(runout_rows), "completed": len(runout_rows), "valid": len(valid_sources),
                                "final_wins": final_wins, "final_losses": final_losses,
                                "run_win_rate": final_wins / len(runout_rows) if runout_rows else None},
        "v_win": {"eligible_battle_start_rows": len(vwin), "unique_source_seeds": len({int(r["sourceSeed"]) for r in vwin}),
                   "row_weighted_win_prevalence": sum(seed_to_run[int(r["sourceSeed"])]["finalWon"] == "1" for r in vwin) / len(vwin) if vwin else None,
                   "source_weighted_win_prevalence": source_wins / (source_wins + source_losses) if source_wins + source_losses else None,
                   "by": {name: dict(values) for name, values in by.items()},
                   "rows_per_source": dict(Counter(rows_by_source.values())),
                   "source_group_split": split_counts},
        "l": {"eligible_nonambiguous_deaths": len(deaths), "unique_death_source_seeds": len({r["sourceSeed"] for r in deaths}),
              "lossRemainingFrac": _quantiles([float(r["lossRemainingFrac"]) for r in deaths]),
              "by": {name: dict(values) for name, values in death_by.items()}},
        "invalid_combat_rows": sum(row["labelValid"] == "0" for row in combat_rows),
        "ambiguous_deaths": sum(row["trueDeath"] == "1" and row["progressAmbiguous"] == "1" for row in combat_rows),
        "escaped_combat_rows": sum(row["escaped"] == "1" for row in combat_rows),
        "trajectory_valid_sources": len(valid_sources),
    }


def validate_shard(shard: dict, teacher: dict, producer_git_sha: str,
                   producer_executable_sha256: str) -> dict:
    spec = shard.get("seed_spec", {})
    offset = _integer(spec.get("offset"), "seed offset")
    count = _integer(spec.get("count"), "seed count")
    ascension = _integer(spec.get("ascension", 0), "ascension")
    require(offset >= 0 and count > 0, "invalid source seed range")
    combat_path = _bound_file(shard.get("combat_csv"), "combat CSV")
    runout_path = _bound_file(shard.get("runout_csv"), "run-out CSV")
    combat_rows, combat = _read_combat(combat_path)
    runout_rows = _read_runout(runout_path)
    expected_seeds = set(range(offset, offset + count))
    run_seeds = {int(row["sourceSeed"]) for row in runout_rows}
    require(run_seeds == expected_seeds, "incomplete requested source cohort")
    combat_seeds = {int(row["sourceSeed"]) for row in combat_rows}
    require(combat_seeds <= expected_seeds, "combat source seed outside requested cohort")
    require(teacher["git_sha"] == producer_git_sha and teacher["executable_sha256"] == producer_executable_sha256,
            "teacher/producer provenance mismatch")
    seed_to_run = {int(row["sourceSeed"]): row for row in runout_rows}
    teachers = {row["teacherId"] for row in combat_rows} | {row["teacherId"] for row in runout_rows}
    require(teachers == {teacher["teacher_id"]}, "mixed or mismatched teacher IDs")
    rows_by_seed = Counter(int(row["sourceSeed"]) for row in combat_rows)
    invalid_by_seed = Counter(int(row["sourceSeed"]) for row in combat_rows if row["labelValid"] == "0")
    for seed, run in seed_to_run.items():
        require(int(run["combatRows"]) == rows_by_seed[seed], "run-out combat row count mismatch")
        require(int(run["fightCount"]) == rows_by_seed[seed], "run-out fight count mismatch")
        require(int(run["invalidCombatRows"]) == invalid_by_seed[seed], "run-out invalid row count mismatch")
        require(run["trajectoryValid"] == "1", "fatal simulator-health or incomplete trajectory cannot enter corpus")
        require(run["simulatorHealthFailures"] == "0" and run["fatalFailure"] == "0",
                "fatal simulator-health or hook/replay failure")
    return {"combat_rows": combat_rows, "runout_rows": runout_rows, "combat": combat,
            "coverage": _coverage(combat_rows, runout_rows, seed_to_run),
            "seed_spec": {"offset": offset, "count": count, "ascension": ascension},
            "paths": {"combat_csv": combat_path, "runout_csv": runout_path}}


def _validate_runtime(runtime: object) -> None:
    require(isinstance(runtime, dict), "missing runtime environment")
    for name in ("machine", "cpu", "omp_num_threads", "worker_count", "command"):
        require(name in runtime and runtime[name] not in (None, ""), f"runtime missing {name}")
    require(int(runtime["omp_num_threads"]) > 0 and int(runtime["worker_count"]) > 0,
            "runtime worker counts must be positive")


def validate_manifest(manifest: dict) -> dict:
    required = ("schema_version", "dataset_role", "producer_git_sha", "producer_executable_sha256", "teacher",
                "ooc_policy", "feature_contract", "seed_spec", "runtime", "shards", "integrity")
    require(all(name in manifest for name in required), "manifest missing required field")
    require(manifest["schema_version"] == SCHEMA_VERSION, "unsupported schema version")
    require(manifest["dataset_role"] in DATASET_ROLES, "unsupported dataset role")
    require(re.fullmatch(r"[0-9a-f]{40}", manifest["producer_git_sha"]) is not None,
            "invalid producer git SHA")
    _hash(manifest["producer_executable_sha256"], "producer executable SHA256")
    _validate_teacher_binding(manifest["teacher"])
    require(manifest["ooc_policy"] == manifest["teacher"]["ooc_policy"],
            "manifest effective OOC policy differs from teacher")
    _validate_feature_contract(manifest["feature_contract"])
    _validate_runtime(manifest["runtime"])
    require(isinstance(manifest["shards"], list) and manifest["shards"], "manifest has no shards")
    seen_seeds = set()
    combined_combat, combined_runout = [], []
    shard_reports = []
    for shard in manifest["shards"]:
        report = validate_shard(shard, manifest["teacher"], manifest["producer_git_sha"],
                                manifest["producer_executable_sha256"])
        seeds = set(range(report["seed_spec"]["offset"], report["seed_spec"]["offset"] + report["seed_spec"]["count"]))
        require(not (seen_seeds & seeds), "duplicate source run identity across shards")
        seen_seeds |= seeds
        combined_combat.extend(report["combat_rows"])
        combined_runout.extend(report["runout_rows"])
        shard_reports.append(report)
    require(manifest["seed_spec"].get("source_count") == len(seen_seeds), "source count mismatch")
    ranges = manifest["seed_spec"].get("ranges")
    require(isinstance(ranges, list) and sorted(ranges) == sorted(r["seed_spec"] for r in shard_reports),
            "source seed ranges mismatch")
    seed_to_run = {int(row["sourceSeed"]): row for row in combined_runout}
    coverage = _coverage(combined_combat, combined_runout, seed_to_run)
    expected = {
        "requested_sources": len(seen_seeds), "completed_sources": coverage["source_trajectories"]["completed"],
        "trajectory_valid_sources": coverage["trajectory_valid_sources"],
        "final_wins": coverage["source_trajectories"]["final_wins"], "final_losses": coverage["source_trajectories"]["final_losses"],
        "combat_rows": len(combined_combat), "v_win_eligible_rows": coverage["v_win"]["eligible_battle_start_rows"],
        "v_win_unique_sources": coverage["v_win"]["unique_source_seeds"],
        "l_eligible_deaths": coverage["l"]["eligible_nonambiguous_deaths"],
        "l_unique_death_sources": coverage["l"]["unique_death_source_seeds"],
        "invalid_combat_rows": coverage["invalid_combat_rows"], "ambiguous_deaths": coverage["ambiguous_deaths"],
        "escaped_combat_rows": coverage["escaped_combat_rows"],
    }
    require(manifest["integrity"] == expected, "manifest integrity/count mismatch")
    return {"coverage": coverage, "integrity": expected, "shards": len(shard_reports),
            "features": list(RICH_NAMES), "source_seeds": sorted(seen_seeds)}


def _manifest(teacher: dict, producer_git_sha: str, producer_executable_sha256: str,
              shards: list[dict], runtime: dict,
              dataset_role: str = "primary_corrected_vwin_l") -> dict:
    ranges = [shard["seed_spec"] for shard in shards]
    return {"schema_version": SCHEMA_VERSION, "dataset_role": dataset_role,
            "producer_git_sha": producer_git_sha,
            "producer_executable_sha256": producer_executable_sha256, "teacher": teacher,
            "ooc_policy": json.loads(json.dumps(teacher["ooc_policy"])),
            "feature_contract": {"count": EXPECTED_STATE_FEATURE_COUNT, "state_names": list(RICH_NAMES),
                                  "state_order_sha256": STATE_ORDER_SHA256, "header_sha256": HEADER_SHA256},
            "seed_spec": {"source_count": sum(int(s["count"]) for s in ranges), "ranges": ranges},
            "runtime": runtime, "shards": shards, "integrity": {}}


def build_manifest(combat_csv: str | Path, runout_csv: str | Path, teacher_path: str | Path,
                   output: str | Path, producer_git_sha: str, producer_executable_sha256: str,
                   seed_offset: int, seed_count: int, ascension: int, runtime: dict,
                   dataset_role: str = "primary_corrected_vwin_l") -> dict:
    teacher = json.loads(Path(teacher_path).read_text(encoding="utf-8"))
    _validate_teacher_binding(teacher)
    shard = {"seed_spec": {"offset": seed_offset, "count": seed_count, "ascension": ascension},
             "combat_csv": {"path": str(Path(combat_csv).resolve()), "sha256": sha256(combat_csv)},
             "runout_csv": {"path": str(Path(runout_csv).resolve()), "sha256": sha256(runout_csv)}}
    manifest = _manifest(teacher, producer_git_sha, producer_executable_sha256, [shard], runtime, dataset_role)
    # Fill the exact aggregate counts after validating the complete shard.
    shard_report = validate_shard(shard, teacher, producer_git_sha, producer_executable_sha256)
    seed_to_run = {int(row["sourceSeed"]): row for row in shard_report["runout_rows"]}
    coverage = _coverage(shard_report["combat_rows"], shard_report["runout_rows"], seed_to_run)
    manifest["integrity"] = {
        "requested_sources": seed_count, "completed_sources": coverage["source_trajectories"]["completed"],
        "trajectory_valid_sources": coverage["trajectory_valid_sources"],
        "final_wins": coverage["source_trajectories"]["final_wins"], "final_losses": coverage["source_trajectories"]["final_losses"],
        "combat_rows": len(shard_report["combat_rows"]), "v_win_eligible_rows": coverage["v_win"]["eligible_battle_start_rows"],
        "v_win_unique_sources": coverage["v_win"]["unique_source_seeds"],
        "l_eligible_deaths": coverage["l"]["eligible_nonambiguous_deaths"],
        "l_unique_death_sources": coverage["l"]["unique_death_source_seeds"],
        "invalid_combat_rows": coverage["invalid_combat_rows"], "ambiguous_deaths": coverage["ambiguous_deaths"],
        "escaped_combat_rows": coverage["escaped_combat_rows"],
    }
    validate_manifest(manifest)
    Path(output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def aggregate_manifests(inputs: list[str | Path], output: str | Path, runtime: dict) -> dict:
    manifests = [json.loads(Path(path).read_text(encoding="utf-8")) for path in inputs]
    for item in manifests:
        validate_manifest(item)
    first = manifests[0]
    for item in manifests[1:]:
        require(item["producer_git_sha"] == first["producer_git_sha"] and
                item["producer_executable_sha256"] == first["producer_executable_sha256"] and
                item["teacher"] == first["teacher"] and item["feature_contract"] == first["feature_contract"],
                "mixed producer, teacher, or feature contract across shards")
    roles = {item["dataset_role"] for item in manifests}
    require(len(roles) == 1, "mixed dataset roles across shards")
    manifest = _manifest(first["teacher"], first["producer_git_sha"], first["producer_executable_sha256"],
                         [shard for item in manifests for shard in item["shards"]], runtime,
                         roles.pop())
    # Recompute the aggregate integrity without duplicating the individual CSV data in the manifest.
    all_combat, all_runout = [], []
    for shard in manifest["shards"]:
        report = validate_shard(shard, manifest["teacher"], manifest["producer_git_sha"], manifest["producer_executable_sha256"])
        all_combat.extend(report["combat_rows"]); all_runout.extend(report["runout_rows"])
    coverage = _coverage(all_combat, all_runout, {int(row["sourceSeed"]): row for row in all_runout})
    manifest["integrity"] = {
        "requested_sources": len(all_runout), "completed_sources": coverage["source_trajectories"]["completed"],
        "trajectory_valid_sources": coverage["trajectory_valid_sources"],
        "final_wins": coverage["source_trajectories"]["final_wins"], "final_losses": coverage["source_trajectories"]["final_losses"],
        "combat_rows": len(all_combat), "v_win_eligible_rows": coverage["v_win"]["eligible_battle_start_rows"],
        "v_win_unique_sources": coverage["v_win"]["unique_source_seeds"],
        "l_eligible_deaths": coverage["l"]["eligible_nonambiguous_deaths"],
        "l_unique_death_sources": coverage["l"]["unique_death_source_seeds"],
        "invalid_combat_rows": coverage["invalid_combat_rows"], "ambiguous_deaths": coverage["ambiguous_deaths"],
        "escaped_combat_rows": coverage["escaped_combat_rows"],
    }
    validate_manifest(manifest)
    Path(output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--aggregate", nargs="+")
    parser.add_argument("--combat-csv")
    parser.add_argument("--runout-csv")
    parser.add_argument("--teacher")
    parser.add_argument("--output")
    parser.add_argument("--producer-git-sha")
    parser.add_argument("--producer-executable-sha256")
    parser.add_argument("--seed-offset", type=int)
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--ascension", type=int, default=0)
    parser.add_argument("--runtime-json")
    parser.add_argument("--dataset-role", choices=sorted(DATASET_ROLES),
                        default="primary_corrected_vwin_l")
    args = parser.parse_args()
    if args.build:
        required_values = ("combat_csv", "runout_csv", "teacher", "output",
                           "producer_git_sha", "producer_executable_sha256",
                           "seed_offset", "seed_count", "runtime_json")
        require(all(getattr(args, name) is not None and getattr(args, name) != ""
                    for name in required_values),
                "--build requires combat/runout/teacher/output/provenance/seed/runtime arguments")
        manifest = build_manifest(args.combat_csv, args.runout_csv, args.teacher, args.output,
                                  args.producer_git_sha, args.producer_executable_sha256,
                                  args.seed_offset, args.seed_count, args.ascension,
                                  json.loads(Path(args.runtime_json).read_text(encoding="utf-8")),
                                  args.dataset_role)
    elif args.aggregate:
        require(args.output and args.runtime_json, "--aggregate requires --output and --runtime-json")
        manifest = aggregate_manifests(args.aggregate, args.output,
                                       json.loads(Path(args.runtime_json).read_text(encoding="utf-8")))
    else:
        require(args.manifest, "manifest path required")
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = validate_manifest(manifest)
        print(json.dumps(result["coverage"], indent=2, sort_keys=True))
        return 0
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"battle_start_runout_contract: {exc}")
