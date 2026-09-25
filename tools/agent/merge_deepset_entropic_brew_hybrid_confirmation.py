#!/usr/bin/env python3
"""Strictly merge the frozen confirmation's four guarded 128-seed chunks."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
import analyze_deepset_entropic_brew_hybrid_confirmation as confirmation  # noqa: E402


CHUNK_SIZE = 128
CHUNK_IDS = ("C1", "H1", "C2", "H2", "C3", "H3", "C4", "H4")
TRANSPORT_NAME = "local-seed-guarded-four-by-128"
FROZEN_SEED_GUARD_SHA256 = "28df9602ddcada2a6353f48da106c9fa63a87fbc5d6094ef88f6e79a0d8035b5"
CHUNK_FILES = {
    "results.csv",
    "results.csv.meta.json",
    "run.log",
    "mcts.csv",
    "mcts.csv.support.jsonl",
    "mcts.csv.actions.jsonl",
    "transport.json",
}
META_CHUNK_FIELDS = {"argv", "seedBlock", "nSeeds", "timestamp"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise confirmation.EvidenceError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for chunk_index in range(4):
        seed_start = confirmation.SEED_START + chunk_index * CHUNK_SIZE
        for arm in ("C", "H"):
            chunk_id = f"{arm}{chunk_index + 1}"
            specs.append({
                "id": chunk_id,
                "arm": arm,
                "sequence": len(specs) + 1,
                "seedStart": seed_start,
                "seedCount": CHUNK_SIZE,
                "seedEnd": seed_start + CHUNK_SIZE - 1,
                "resultsPath": f"chunks/{chunk_id}/results.csv",
                "tracePath": f"chunks/{chunk_id}/mcts.csv",
                "logPath": f"chunks/{chunk_id}/run.log",
            })
    return specs


def local_files_for_root(manifest: dict[str, Any], root: Path) -> dict[str, Path]:
    arm_c = confirmation.manifest_arm(manifest, "C")
    arm_h = confirmation.manifest_arm(manifest, "H")
    return {
        "binary": root / manifest["binary"]["remote_path"],
        "standard_ctm": root / arm_c["env"]["STS_OOC_MCTS_COMBAT_MODEL"],
        "fast_ctm": root / arm_h["env"]["STS_OOC_MCTS_COMBAT_MODEL"],
        "v4_policy": root / manifest["common_env"]["STS_OOC_STRATEGIC_TOK_NN"],
        "floor_model": root / "models/v_rich_trees.txt",
        "win_model": root / "models/v_win_trees.txt",
    }


def expected_hashes_for_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    require(manifest.get("binary", {}).get("sha256") == confirmation.FROZEN_BINARY_SHA256,
            "manifest binary SHA does not match the frozen confirmation executable")
    return {**confirmation.ARTIFACT_SHAS, "binary": confirmation.FROZEN_BINARY_SHA256}


def expected_environment(manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, str]:
    arm = confirmation.manifest_arm(manifest, spec["arm"])
    env = {**manifest["common_env"], **arm["env"]}
    env["STS_OOC_MCTS_TRACE"] = spec["tracePath"]
    return env


def expected_game_command(manifest: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    return [
        manifest["command"][0],
        "bestbench",
        str(confirmation.COMBAT_BUDGET),
        str(CHUNK_SIZE),
        str(confirmation.ASCENSION),
        str(spec["seedStart"]),
        spec["resultsPath"],
    ]


def guarded_argv(environment: dict[str, str], game_command: list[str]) -> list[str]:
    return [
        "env",
        "-i",
        *(f"{key}={value}" for key, value in sorted(environment.items())),
        "bash",
        "tools/seed_guard.sh",
        *game_command,
    ]


def build_transport_plan(manifest_path: Path, root: Path, local_files: dict[str, Path],
                         guard_path: Path, transport_git_sha: str,
                         expected_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    manifest = confirmation.read_manifest(manifest_path)
    hashes = expected_hashes or expected_hashes_for_manifest(manifest)
    confirmation.validate_manifest(manifest, local_files, hashes)
    guard_sha = confirmation.sha256(guard_path)
    require(guard_sha == FROZEN_SEED_GUARD_SHA256,
            "local seed guard is not byte-identical to the frozen c9 guard")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", transport_git_sha)),
            "transport tooling Git SHA must be a full lowercase commit SHA")
    return {
        "schemaVersion": 1,
        "transport": TRANSPORT_NAME,
        "scientificProtocolChanged": False,
        "frozenSourceGitSha": confirmation.FROZEN_SHA,
        "transportToolGitSha": transport_git_sha,
        "workRoot": str(root.resolve()),
        "manifestSha256": confirmation.sha256(manifest_path),
        "seedGuardSha256": guard_sha,
        "artifactSha256": {role: confirmation.sha256(path)
                           for role, path in sorted(local_files.items())},
        "executionOrder": list(CHUNK_IDS),
        "chunks": expected_specs(),
    }


def write_transport_receipt(path: Path, plan_path: Path, root: Path,
                            manifest: dict[str, Any], spec: dict[str, Any],
                            local_files: dict[str, Path], environment: dict[str, str],
                            started_at: str, finished_at: str, elapsed_seconds: float) -> None:
    game_command = expected_game_command(manifest, spec)
    plan = confirmation.read_manifest(plan_path)
    plan_sha = confirmation.sha256(plan_path)
    receipt = {
        "schemaVersion": 1,
        "transport": TRANSPORT_NAME,
        "chunkId": spec["id"],
        "arm": spec["arm"],
        "sequence": spec["sequence"],
        "seedStart": spec["seedStart"],
        "seedCount": spec["seedCount"],
        "seedEnd": spec["seedEnd"],
        "manifestSha256": plan["manifestSha256"],
        "transportPlanSha256": plan_sha,
        "workRoot": str(root.resolve()),
        "workingDirectory": str(root.resolve()),
        "environmentPolicy": "clean-env-i",
        "environment": environment,
        "gameCommand": game_command,
        "guardedArgv": guarded_argv(environment, game_command),
        "seedGuardPath": "tools/seed_guard.sh",
        "seedGuardSha256": FROZEN_SEED_GUARD_SHA256,
        "artifactSha256": {role: confirmation.sha256(file)
                           for role, file in sorted(local_files.items())},
        "exitCode": 0,
        "startedAtUtc": started_at,
        "finishedAtUtc": finished_at,
        "elapsedSeconds": elapsed_seconds,
    }
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_transport_plan(path: Path, root: Path, manifest_path: Path,
                        local_files: dict[str, Path], guard_path: Path,
                        expected_hashes: dict[str, str]) -> dict[str, Any]:
    plan = confirmation.read_manifest(path)
    expected_fields = {
        "schemaVersion", "transport", "scientificProtocolChanged", "frozenSourceGitSha",
        "transportToolGitSha", "workRoot", "manifestSha256", "seedGuardSha256",
        "artifactSha256", "executionOrder", "chunks",
    }
    require(set(plan) == expected_fields, "transport plan has unknown or missing fields")
    require(plan["schemaVersion"] == 1 and plan["transport"] == TRANSPORT_NAME,
            "unsupported local transport plan")
    require(plan["scientificProtocolChanged"] is False,
            "local transport plan claims a scientific protocol change")
    require(plan["frozenSourceGitSha"] == confirmation.FROZEN_SHA,
            "transport plan frozen source SHA mismatch")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", plan["transportToolGitSha"])),
            "transport tooling Git SHA is malformed")
    require(plan["workRoot"] == str(root.resolve()), "transport plan work root mismatch")
    require(plan["manifestSha256"] == confirmation.sha256(manifest_path),
            "transport plan confirmation manifest hash mismatch")
    guard_sha = confirmation.sha256(guard_path)
    require(guard_sha == FROZEN_SEED_GUARD_SHA256 == plan["seedGuardSha256"],
            "transport plan seed guard hash mismatch")
    actual_asset_hashes = {role: confirmation.sha256(file)
                           for role, file in sorted(local_files.items())}
    require(actual_asset_hashes == expected_hashes,
            "local staged binary/model hashes differ from the frozen artifact pins")
    require(plan["artifactSha256"] == actual_asset_hashes,
            "transport plan binary/model hashes differ from staged files")
    require(plan["executionOrder"] == list(CHUNK_IDS),
            "transport plan execution order is not C1,H1,C2,H2,C3,H3,C4,H4")
    require(plan["chunks"] == expected_specs(),
            "transport plan must contain exactly the four frozen chunks per arm")
    return plan


def _utc_datetime(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise confirmation.EvidenceError(f"{label} is malformed: {value!r}") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
            f"{label} must use UTC")
    return parsed


def validate_transport_receipt(path: Path, plan_path: Path, plan: dict[str, Any],
                               manifest_path: Path, root: Path,
                               local_files: dict[str, Path], manifest: dict[str, Any],
                               spec: dict[str, Any], expected_environment: dict[str, str]) -> dict[str, Any]:
    receipt = confirmation.read_manifest(path)
    required = {
        "schemaVersion", "transport", "chunkId", "arm", "sequence", "seedStart",
        "seedCount", "seedEnd", "manifestSha256", "transportPlanSha256", "workRoot",
        "workingDirectory", "environmentPolicy", "environment", "gameCommand", "guardedArgv",
        "seedGuardPath", "seedGuardSha256", "artifactSha256", "exitCode", "startedAtUtc",
        "finishedAtUtc", "elapsedSeconds",
    }
    require(set(receipt) == required, f"{path}: transport receipt has unknown or missing fields")
    expected_scalars = {
        "schemaVersion": 1,
        "transport": TRANSPORT_NAME,
        "chunkId": spec["id"],
        "arm": spec["arm"],
        "sequence": spec["sequence"],
        "seedStart": spec["seedStart"],
        "seedCount": CHUNK_SIZE,
        "seedEnd": spec["seedEnd"],
        "manifestSha256": confirmation.sha256(manifest_path),
        "transportPlanSha256": confirmation.sha256(plan_path),
        "workRoot": str(root.resolve()),
        "workingDirectory": str(root.resolve()),
        "environmentPolicy": "clean-env-i",
        "seedGuardPath": "tools/seed_guard.sh",
        "seedGuardSha256": FROZEN_SEED_GUARD_SHA256,
        "exitCode": 0,
    }
    for key, value in expected_scalars.items():
        require(receipt.get(key) == value, f"{path}: receipt {key} mismatch")
    require(receipt["environment"] == expected_environment,
            f"{path}: clean process environment differs from the frozen arm configuration")
    game_command = expected_game_command(manifest, spec)
    require(receipt["gameCommand"] == game_command, f"{path}: guarded bestbench command mismatch")
    require(receipt["guardedArgv"] == guarded_argv(expected_environment, game_command),
            f"{path}: execution did not route through the local seed guard")
    expected_asset_hashes = {role: confirmation.sha256(file)
                             for role, file in sorted(local_files.items())}
    require(receipt["artifactSha256"] == expected_asset_hashes == plan["artifactSha256"],
            f"{path}: frozen binary/model hashes differ across chunk receipts")
    start_time = _utc_datetime(receipt["startedAtUtc"], f"{path}: startedAtUtc")
    finish_time = _utc_datetime(receipt["finishedAtUtc"], f"{path}: finishedAtUtc")
    require(finish_time >= start_time, f"{path}: finish time precedes start time")
    elapsed = receipt["elapsedSeconds"]
    require(isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0,
            f"{path}: elapsedSeconds must be finite and nonnegative")
    return receipt


def _normalized_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(meta)
    normalized["argv"] = ["bestbench", str(confirmation.COMBAT_BUDGET), "<chunk-size>",
                          str(confirmation.ASCENSION), "<chunk-start>", "<chunk-results>"]
    normalized["seedBlock"] = {"lo": "<chunk-start>", "hi": "<chunk-end>"}
    normalized["nSeeds"] = "<chunk-size>"
    normalized["timestamp"] = "<chunk-start-time>"
    return normalized


def _csv_bytes(path: Path, required_fields: tuple[str, ...]) -> tuple[bytes, list[bytes]]:
    raw = path.read_bytes()
    require(raw.endswith(b"\n"), f"{path}: CSV must end with LF")
    lines = raw.splitlines(keepends=True)
    require(lines and lines[0].endswith(b"\n"), f"{path}: missing CSV header")
    require(all(line.endswith(b"\n") for line in lines), f"{path}: unterminated CSV row")
    require(len(lines) >= 2, f"{path}: CSV contains no data rows")
    header = lines[0]
    try:
        names = next(csv.reader(io.StringIO(header.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise confirmation.EvidenceError(f"{path}: malformed CSV header") from exc
    require(set(required_fields) <= set(names), f"{path}: required CSV columns are missing")
    require(len(names) == len(set(names)), f"{path}: duplicate CSV column names")
    require(len(lines) - 1 == len(confirmation.read_csv_keyed(path, required_fields)),
            f"{path}: CSV records span multiple physical lines")
    return header, lines[1:]


def _write_merged_csv(paths: list[Path], destination: Path,
                      required_fields: tuple[str, ...]) -> None:
    header: bytes | None = None
    with destination.open("xb") as output:
        for index, path in enumerate(paths):
            current_header, rows = _csv_bytes(path, required_fields)
            if header is None:
                header = current_header
                output.write(header)
            else:
                require(current_header == header, f"{path}: CSV header differs across chunks")
            output.writelines(rows)


def _write_merged_jsonl(paths: list[Path], destination: Path) -> None:
    with destination.open("xb") as output:
        for path in paths:
            raw = path.read_bytes()
            require(raw.endswith(b"\n"), f"{path}: JSONL must end with LF")
            confirmation.read_jsonl(path)
            output.write(raw)


def _write_merged_log(paths: list[Path], destination: Path) -> None:
    marker = b"[ooc-mcts-config] "
    saw_config = False
    with destination.open("xb") as output:
        for path in paths:
            raw = path.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise confirmation.EvidenceError(f"{path}: log is not UTF-8") from exc
            lines = raw.splitlines(keepends=True)
            config_count = sum(marker in line for line in lines)
            require(config_count == 1, f"{path}: expected one effective OOC config record")
            for line in lines:
                if marker in line:
                    if saw_config:
                        continue
                    saw_config = True
                output.write(line)
    require(saw_config, "merged log has no effective OOC config record")


def merge_chunks(manifest_path: Path, root: Path, output_root: Path,
                 expected_hashes: dict[str, str] | None = None,
                 chunks_dir: Path | None = None) -> dict[str, Any]:
    manifest = confirmation.read_manifest(manifest_path)
    hashes = expected_hashes or expected_hashes_for_manifest(manifest)
    local_files = local_files_for_root(manifest, root)
    arms = confirmation.validate_manifest(manifest, local_files, hashes)
    guard_path = root / "tools/seed_guard.sh"
    plan_path = root / "transport-plan.json"
    plan = read_transport_plan(plan_path, root, manifest_path, local_files, guard_path, hashes)
    chunk_root = chunks_dir or root / "chunks"
    require(chunk_root.is_dir(), "chunk directory is missing")
    actual_chunk_entries = sorted(path.name for path in chunk_root.iterdir())
    require(actual_chunk_entries == sorted(CHUNK_IDS),
            f"expected exactly {list(CHUNK_IDS)}; found chunk entries {actual_chunk_entries}")
    require(not output_root.exists() and not output_root.is_symlink(),
            f"refusing existing merged output path: {output_root}")

    plan_bytes = plan_path.read_bytes()
    require(json.loads(plan_bytes) == plan, "transport plan changed while loading")
    plan_sha = sha256_bytes(plan_bytes)
    manifest_sha = confirmation.sha256(manifest_path)
    normalized_meta: dict[str, Any] | None = None
    configs: dict[str, dict[str, Any]] = {}
    validated: dict[str, dict[str, dict[str, Any]]] = {"C": {}, "H": {}}
    receipts: dict[str, dict[str, Any]] = {}
    source_paths: dict[str, dict[str, Path]] = {}

    for spec in expected_specs():
        chunk_id = spec["id"]
        directory = chunk_root / chunk_id
        require(not directory.is_symlink(), f"{chunk_id}: chunk directory must not be a symlink")
        entries = list(directory.iterdir())
        actual_files = {path.name for path in entries if path.is_file()}
        require(actual_files == CHUNK_FILES,
                f"{chunk_id}: expected files {sorted(CHUNK_FILES)}, found {sorted(actual_files)}")
        require(all(path.is_file() and not path.is_symlink() for path in entries),
                f"{chunk_id}: chunk outputs must not be symlinks")
        env = expected_environment(manifest, spec)
        result_path = spec["resultsPath"]
        receipt = validate_transport_receipt(
            directory / "transport.json", plan_path, plan, manifest_path, root,
            local_files, manifest, spec, env,
        )
        require(receipt["manifestSha256"] == manifest_sha and receipt["transportPlanSha256"] == plan_sha,
                f"{chunk_id}: receipt manifest/plan hash mismatch")

        chunk_seeds = list(range(spec["seedStart"], spec["seedEnd"] + 1))
        arm_data = confirmation.validate_arm(
            directory, spec["arm"], chunk_seeds, env, hashes["binary"], result_path
        )
        metadata = arm_data["meta"]
        _utc_datetime(metadata.get("timestamp"), f"{chunk_id}: metadata timestamp")
        current_normalized = _normalized_metadata(metadata)
        if normalized_meta is None:
            normalized_meta = current_normalized
        else:
            require(current_normalized == normalized_meta,
                    f"{chunk_id}: frozen bestbench binary/model/config metadata differs across chunks")

        if spec["arm"] in configs:
            require(arm_data["oocConfig"] == configs[spec["arm"]],
                    f"{chunk_id}: effective OOC MCTS config differs within arm")
        else:
            configs[spec["arm"]] = arm_data["oocConfig"]
        validated[spec["arm"]][chunk_id] = arm_data
        receipts[chunk_id] = receipt
        source_paths[chunk_id] = {
            "results": directory / "results.csv",
            "meta": directory / "results.csv.meta.json",
            "log": directory / "run.log",
            "trace": directory / "mcts.csv",
            "support": directory / "mcts.csv.support.jsonl",
            "actions": directory / "mcts.csv.actions.jsonl",
        }

    c_common = {key: value for key, value in configs["C"].items()
                if key not in {"combatModel", "brewFallbackModel", "dispatchRule"}}
    h_common = {key: value for key, value in configs["H"].items()
                if key not in {"combatModel", "brewFallbackModel", "dispatchRule"}}
    require(c_common == h_common, "C/H chunks differ in a common effective OOC MCTS setting")

    output_root.mkdir(parents=True, exist_ok=False)
    output_dirs: dict[str, Path] = {}
    for arm in ("C", "H"):
        name = "standard" if arm == "C" else "hybrid"
        destination = output_root / name
        destination.mkdir()
        output_dirs[arm] = destination
        chunk_ids = [f"{arm}{index}" for index in range(1, 5)]
        paths = [source_paths[chunk_id] for chunk_id in chunk_ids]
        _write_merged_csv([item["results"] for item in paths], destination / "results.csv",
                          confirmation.RESULT_FIELDS)
        _write_merged_csv([item["trace"] for item in paths], destination / "mcts.csv",
                          confirmation.TRACE_FIELDS)
        _write_merged_jsonl([item["support"] for item in paths],
                            destination / "mcts.csv.support.jsonl")
        _write_merged_jsonl([item["actions"] for item in paths],
                            destination / "mcts.csv.actions.jsonl")
        _write_merged_log([item["log"] for item in paths], destination / "run.log")

        metadata = copy.deepcopy(validated[arm][chunk_ids[0]]["meta"])
        arm_manifest = arms[arm]
        metadata["argv"] = [
            "bestbench", str(confirmation.COMBAT_BUDGET), str(confirmation.SEED_COUNT),
            str(confirmation.ASCENSION), str(confirmation.SEED_START), arm_manifest["results"],
        ]
        metadata["seedBlock"] = {
            "lo": confirmation.SEED_START,
            "hi": confirmation.SEED_START + confirmation.SEED_COUNT - 1,
        }
        metadata["nSeeds"] = confirmation.SEED_COUNT
        (destination / "results.csv.meta.json").write_text(
            json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
        )

        full_env = {**manifest["common_env"], **arm_manifest["env"]}
        confirmation.validate_arm(destination, arm, list(range(
            confirmation.SEED_START,
            confirmation.SEED_START + confirmation.SEED_COUNT,
        )), full_env, hashes["binary"], arm_manifest["results"])

    report = {
        "schemaVersion": 1,
        "transport": TRANSPORT_NAME,
        "scientificProtocolChanged": False,
        "frozenSourceGitSha": confirmation.FROZEN_SHA,
        "manifestSha256": manifest_sha,
        "transportPlanSha256": plan_sha,
        "seedRange": [confirmation.SEED_START,
                      confirmation.SEED_START + confirmation.SEED_COUNT - 1],
        "seedCountPerArm": confirmation.SEED_COUNT,
        "chunkCountPerArm": 4,
        "chunkSize": CHUNK_SIZE,
        "executionOrder": list(CHUNK_IDS),
        "chunks": {
            chunk_id: {
                "arm": receipts[chunk_id]["arm"],
                "seedStart": receipts[chunk_id]["seedStart"],
                "seedEnd": receipts[chunk_id]["seedEnd"],
                "startedAtUtc": receipts[chunk_id]["startedAtUtc"],
                "finishedAtUtc": receipts[chunk_id]["finishedAtUtc"],
                "elapsedSeconds": receipts[chunk_id]["elapsedSeconds"],
                "inputSha256": {path_key: confirmation.sha256(path)
                                for path_key, path in source_paths[chunk_id].items()},
            }
            for chunk_id in CHUNK_IDS
        },
        "outputs": {
            arm: {path.name: confirmation.sha256(path)
                  for path in sorted(directory.iterdir()) if path.is_file()}
            for arm, directory in output_dirs.items()
        },
        "note": "Merged raw result/trace CSV rows and support/action JSONL records byte-for-byte; repeated CSV headers and duplicate per-chunk config log lines were omitted. Source chunk files remain unchanged.",
    }
    (output_root / "merge-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _split_fixture_csv(source: Path, destination: Path, start: int, end: int,
                       required_fields: tuple[str, ...]) -> None:
    raw = source.read_bytes()
    lines = raw.splitlines(keepends=True)
    header = lines[0]
    records: dict[int, bytes] = {}
    try:
        decoded = [line.decode("utf-8") for line in lines[1:]]
        for line, row in zip(lines[1:], csv.DictReader(io.StringIO(header.decode() + "".join(decoded)),
                                                       restkey="__extra__")):
            require(not row.get("__extra__"), f"{source}: synthetic CSV row overflow")
            seed = int(row["seed"])
            records[seed] = line
    except (UnicodeDecodeError, csv.Error, KeyError, ValueError) as exc:
        raise confirmation.EvidenceError(f"{source}: cannot split synthetic CSV") from exc
    require(set(range(start, end + 1)) <= set(records),
            f"{source}: synthetic rows do not cover requested chunk")
    destination.write_bytes(header + b"".join(records[seed] for seed in range(start, end + 1)))
    confirmation.read_csv_keyed(destination, required_fields)


def _split_fixture_jsonl(source: Path, destination: Path, start: int, end: int,
                         actions: bool = False) -> None:
    raw = source.read_bytes()
    by_seed: dict[int, list[bytes]] = {seed: [] for seed in range(start, end + 1)}
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        seed = int(row["seed"])
        if seed in by_seed:
            by_seed[seed].append(line)
    if not actions:
        require(all(len(lines) == 1 for lines in by_seed.values()),
                f"{source}: expected one support record per seed")
    require(all(by_seed.values()), f"{source}: missing synthetic seed records")
    destination.write_bytes(b"".join(line for seed in range(start, end + 1)
                                        for line in by_seed[seed]))


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="deepset-local-chunk-merge-") as temp:
        root = Path(temp) / "work"
        root.mkdir()
        fixture_root = root / "fixture"
        standard, hybrid, manifest_path, original_files = confirmation.synthetic_fixture(
            fixture_root, "mixed"
        )
        manifest = confirmation.read_manifest(manifest_path)
        guard_path = root / "tools/seed_guard.sh"
        guard_path.parent.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / "tools/seed_guard.sh", guard_path)
        shutil.copymode(REPO_ROOT / "tools/seed_guard.sh", guard_path)

        local_files: dict[str, Path] = {}
        arms = {arm: confirmation.manifest_arm(manifest, arm) for arm in ("C", "H")}
        staging_paths = {
            "binary": manifest["binary"]["remote_path"],
            "standard_ctm": arms["C"]["env"]["STS_OOC_MCTS_COMBAT_MODEL"],
            "fast_ctm": arms["H"]["env"]["STS_OOC_MCTS_COMBAT_MODEL"],
            "v4_policy": manifest["common_env"]["STS_OOC_STRATEGIC_TOK_NN"],
            "floor_model": "models/v_rich_trees.txt",
            "win_model": "models/v_win_trees.txt",
        }
        for role, relative in staging_paths.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original_files[role], target)
            local_files[role] = target

        dynamic_hashes = {role: confirmation.sha256(path) for role, path in local_files.items()}
        for item, role in zip(manifest["artifacts"],
                              ("standard_ctm", "fast_ctm", "v4_policy", "floor_model", "win_model")):
            item["sha256"] = dynamic_hashes[role]
        manifest["binary"]["sha256"] = dynamic_hashes["binary"]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifest_path = root / "confirmation-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        hashes = dict(dynamic_hashes)
        plan = build_transport_plan(manifest_path, root, local_files, guard_path, "7069518b5da3b38f4bac562a9b724de158814583", hashes)
        plan_path = root / "transport-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        plan_sha = confirmation.sha256(plan_path)
        chunks_root = root / "chunks"
        chunks_root.mkdir()
        for spec in expected_specs():
            directory = chunks_root / spec["id"]
            directory.mkdir()
            source_dir = standard if spec["arm"] == "C" else hybrid
            start = spec["seedStart"]
            end = spec["seedEnd"]
            _split_fixture_csv(source_dir / "results.csv", directory / "results.csv", start, end,
                               confirmation.RESULT_FIELDS)
            _split_fixture_csv(source_dir / "mcts.csv", directory / "mcts.csv", start, end,
                               confirmation.TRACE_FIELDS)
            _split_fixture_jsonl(source_dir / "mcts.csv.support.jsonl",
                                 directory / "mcts.csv.support.jsonl", start, end)
            _split_fixture_jsonl(source_dir / "mcts.csv.actions.jsonl",
                                 directory / "mcts.csv.actions.jsonl", start, end, actions=True)
            shutil.copyfile(source_dir / "run.log", directory / "run.log")
            metadata = confirmation.read_one_json(source_dir / "results.csv.meta.json")
            metadata.update({
                "argv": ["bestbench", str(confirmation.COMBAT_BUDGET), str(CHUNK_SIZE),
                         str(confirmation.ASCENSION), str(start), spec["resultsPath"]],
                "seedBlock": {"lo": start, "hi": end},
                "nSeeds": CHUNK_SIZE,
                "timestamp": "2026-09-25T00:00:00Z",
            })
            (directory / "results.csv.meta.json").write_text(
                json.dumps(metadata) + "\n", encoding="utf-8"
            )
            env = expected_environment(manifest, spec)
            receipt = {
                "schemaVersion": 1,
                "transport": TRANSPORT_NAME,
                "chunkId": spec["id"],
                "arm": spec["arm"],
                "sequence": spec["sequence"],
                "seedStart": start,
                "seedCount": CHUNK_SIZE,
                "seedEnd": end,
                "manifestSha256": confirmation.sha256(manifest_path),
                "transportPlanSha256": plan_sha,
                "workRoot": str(root.resolve()),
                "workingDirectory": str(root.resolve()),
                "environmentPolicy": "clean-env-i",
                "environment": env,
                "gameCommand": expected_game_command(manifest, spec),
                "guardedArgv": guarded_argv(env, expected_game_command(manifest, spec)),
                "seedGuardPath": "tools/seed_guard.sh",
                "seedGuardSha256": FROZEN_SEED_GUARD_SHA256,
                "artifactSha256": dynamic_hashes,
                "exitCode": 0,
                "startedAtUtc": "2026-09-25T00:00:00Z",
                "finishedAtUtc": "2026-09-25T00:00:01Z",
                "elapsedSeconds": 1.0,
            }
            (directory / "transport.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

        output_root = root / "merged"
        report = merge_chunks(manifest_path, root, output_root, hashes)
        require(report["seedCountPerArm"] == 512 and report["chunkCountPerArm"] == 4,
                "self-test merge report lost the frozen cohort dimensions")
        require(confirmation.read_csv_keyed(output_root / "standard/results.csv",
                                            confirmation.RESULT_FIELDS)
                == confirmation.read_csv_keyed(standard / "results.csv", confirmation.RESULT_FIELDS),
                "self-test standard merge changed result row contents")
        require(confirmation.read_csv_keyed(output_root / "hybrid/mcts.csv",
                                            confirmation.TRACE_FIELDS)
                == confirmation.read_csv_keyed(hybrid / "mcts.csv", confirmation.TRACE_FIELDS),
                "self-test hybrid merge changed trace row contents")

        missing_root = root / "missing-chunks"
        shutil.copytree(chunks_root, missing_root)
        shutil.rmtree(missing_root / "H4")
        try:
            merge_chunks(manifest_path, root, root / "missing-output", hashes, missing_root)
        except confirmation.EvidenceError:
            pass
        else:
            raise AssertionError("missing-chunk self-test did not fail")
    print("deepset local four-chunk merger self-test PASS")


def parser() -> Any:
    import argparse

    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--manifest", type=Path)
    result.add_argument("--work-root", type=Path)
    result.add_argument("--output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.manifest is None or args.work_root is None:
        raise SystemExit("--manifest and --work-root are required")
    output = args.output or args.work_root / "merged"
    try:
        report = merge_chunks(args.manifest, args.work_root, output)
    except (confirmation.EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"confirmation chunk merge FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "CHUNK_MERGE_PASS", "output": str(output),
                      "seedCountPerArm": report["seedCountPerArm"],
                      "chunkCountPerArm": report["chunkCountPerArm"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
