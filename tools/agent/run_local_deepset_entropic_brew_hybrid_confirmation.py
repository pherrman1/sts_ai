#!/usr/bin/env python3
"""Run the frozen 512-pair confirmation locally as guarded 128-seed chunks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parent
EVIDENCE_DIR = REPO_ROOT / "docs/experiments/evidence/deepset_entropic_brew_hybrid_confirmation_2026-09-24"
CANARY_MANIFEST = EVIDENCE_DIR / "run-manifest-canary.json"
CONFIRMATION_MANIFEST = EVIDENCE_DIR / "run-manifest-confirmation.json"
DEFAULT_WORK_ROOT = REPO_ROOT / "build/local_deepset_hybrid_confirmation_7069518"
sys.path.insert(0, str(TOOLS_DIR))
import analyze_deepset_entropic_brew_hybrid_confirmation as confirmation  # noqa: E402
import check_deepset_entropic_brew_hybrid_canary as canary_validator  # noqa: E402
import merge_deepset_entropic_brew_hybrid_confirmation as merger  # noqa: E402


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_files() -> dict[str, Path]:
    return {
        "binary": REPO_ROOT / "build/linux-gcc-release/one_combat",
        "standard_ctm": REPO_ROOT / "selfplay/models/combat_transition_near_full_except_smoke_v2.native",
        "fast_ctm": Path("/tmp/deepset-entropic-hybrid-specialist.native"),
        "v4_policy": REPO_ROOT / "selfplay/models/ooc_strategic_tok_final.native",
        "floor_model": REPO_ROOT / "models/v_rich_trees.txt",
        "win_model": REPO_ROOT / "models/v_win_trees.txt",
    }


def assert_frozen_sources(files: dict[str, Path], guard_bytes: bytes) -> dict[str, str]:
    expected = {**confirmation.ARTIFACT_SHAS,
                "binary": confirmation.FROZEN_BINARY_SHA256}
    hashes: dict[str, str] = {}
    for role, path in files.items():
        confirmation.require(path.is_file(), f"missing frozen {role}: {path}")
        digest = confirmation.sha256(path)
        confirmation.require(digest == expected[role],
                             f"wrong frozen {role} SHA256: {digest} != {expected[role]}")
        hashes[role] = digest
    binary = files["binary"]
    confirmation.require(os.access(binary, os.X_OK), "frozen one_combat binary is not executable")
    confirmation.require(digest_bytes(guard_bytes) == merger.FROZEN_SEED_GUARD_SHA256,
                         "c9 seed guard hash differs from the reviewed local guard pin")
    build_record = confirmation.read_manifest(EVIDENCE_DIR / "build-provenance.json")
    confirmation.require(build_record.get("sourceGitSha") == confirmation.FROZEN_SHA
                         and build_record.get("binarySha256") == hashes["binary"],
                         "recorded build provenance differs from the frozen source/binary")
    return hashes


def frozen_guard_bytes() -> bytes:
    try:
        guard = subprocess.check_output(
            ["git", "show", f"{confirmation.FROZEN_SHA}:tools/seed_guard.sh"],
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        raise confirmation.EvidenceError("cannot read seed_guard.sh from the frozen c9 source") from exc
    confirmation.require(digest_bytes(guard) == merger.FROZEN_SEED_GUARD_SHA256,
                         "seed_guard.sh from frozen c9 differs from the reviewed guard pin")
    return guard


def stage_assets(root: Path, manifest: dict[str, Any], sources: dict[str, Path],
                 guard_bytes: bytes, expected_hashes: dict[str, str]) -> tuple[dict[str, Path], Path]:
    destination_files = merger.local_files_for_root(manifest, root)
    for role, destination in destination_files.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sources[role], destination)
        if role == "binary":
            destination.chmod(destination.stat().st_mode | 0o111)
        confirmation.require(confirmation.sha256(destination) == expected_hashes[role],
                             f"staged {role} SHA256 changed during copy")
    guard_path = root / "tools/seed_guard.sh"
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_bytes(guard_bytes)
    guard_path.chmod(0o755)
    confirmation.require(confirmation.sha256(guard_path) == merger.FROZEN_SEED_GUARD_SHA256,
                         "staged c9 seed guard hash mismatch")
    return destination_files, guard_path


def all_target_paths(root: Path, canary_manifest: dict[str, Any]) -> list[Path]:
    targets: list[Path] = [
        root / "transport-plan.json",
        root / "canary-validation.json",
        root / "transport-completion.json",
        root / "merged/merge-report.json",
        root / "analysis/summary.json",
        root / "analysis/per-seed.csv",
        root / "analysis/analyzer.stdout.json",
    ]
    for arm in canary_manifest["arms"]:
        trace = arm["env"]["STS_OOC_MCTS_TRACE"]
        results = arm["results"]
        targets.extend([
            root / results,
            root / (results + ".meta.json"),
            root / arm["log"],
            root / trace,
            root / (trace + ".support.jsonl"),
            root / (trace + ".actions.jsonl"),
            root / f"canaries/{arm['name']}/transport.json",
        ])
        normalized = root / ("canary/standard" if arm["name"] == "C" else "canary/hybrid")
        targets.extend(normalized / name for name in (
            "results.csv", "results.csv.meta.json", "run.log", "mcts.csv",
            "mcts.csv.support.jsonl", "mcts.csv.actions.jsonl",
        ))
    for spec in merger.expected_specs():
        chunk = root / "chunks" / spec["id"]
        targets.extend(chunk / name for name in merger.CHUNK_FILES)
    targets.extend(root / "merged" / arm / name for arm in ("standard", "hybrid") for name in (
        "results.csv", "results.csv.meta.json", "run.log", "mcts.csv",
        "mcts.csv.support.jsonl", "mcts.csv.actions.jsonl",
    ))
    return targets


def check_fresh_paths(root: Path, targets: list[Path]) -> None:
    confirmation.require(not root.exists() and not root.is_symlink(),
                         f"refusing existing local run root: {root}")
    strings = [str(path) for path in targets]
    confirmation.require(len(strings) == len(set(strings)),
                         "local transport plan contains colliding output paths")
    existing = [str(path) for path in targets if path.exists() or path.is_symlink()]
    confirmation.require(not existing, "refusing existing local output paths: " + ", ".join(existing))


def preflight_only(work_root: Path) -> None:
    confirmation_manifest = confirmation.read_manifest(CONFIRMATION_MANIFEST)
    canary_manifest = confirmation.read_manifest(CANARY_MANIFEST)
    sources = source_files()
    guard_bytes = frozen_guard_bytes()
    hashes = assert_frozen_sources(sources, guard_bytes)
    confirmation.validate_manifest(confirmation_manifest, sources, hashes)
    confirmation.validate_manifest(canary_manifest, sources, hashes,
                                    seed_start=989999, seed_count=1)
    check_fresh_paths(work_root, all_target_paths(work_root, canary_manifest))

    with tempfile.TemporaryDirectory(prefix="deepset-confirmation-preflight-") as temp_dir:
        guard_root = Path(temp_dir)
        guard_path = guard_root / "tools/seed_guard.sh"
        guard_path.parent.mkdir(parents=True)
        guard_path.write_bytes(guard_bytes)
        guard_path.chmod(0o755)
        confirmation.require(confirmation.sha256(guard_path) == merger.FROZEN_SEED_GUARD_SHA256,
                             "staged c9 seed guard hash mismatch during preflight")

        # Run guard-only checks from the directory containing the verified c9
        # guard; the repository root may carry a newer, unpinned guard.
        for arm in ("C", "H"):
            arm_manifest = confirmation.manifest_arm(canary_manifest, arm)
            env = {**canary_manifest["common_env"], **arm_manifest["env"]}
            command = [item if item != "{results}" else arm_manifest["results"]
                       for item in canary_manifest["command"]]
            subprocess.run(guarded_canary_argv(env, command, guard_only=True), cwd=guard_root,
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        for spec in merger.expected_specs():
            env = merger.expected_environment(confirmation_manifest, spec)
            command = merger.expected_game_command(confirmation_manifest, spec)
            subprocess.run(merger.guarded_argv(env, ["guard-only", *command]), cwd=guard_root,
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    print("local transport preflight PASS: frozen pins verified; 2 canaries and 8 chunks are guard-valid; no paths created")


def guarded_canary_argv(environment: dict[str, str], game_command: list[str],
                        guard_only: bool = False) -> list[str]:
    insert = ["guard-only"] if guard_only else []
    return [
        "env", "-i", *(f"{key}={value}" for key, value in sorted(environment.items())),
        "bash", "tools/seed_guard.sh", *insert, *game_command,
    ]


def execute(argv: list[str], root: Path, log_path: Path) -> tuple[str, str, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = now_utc()
    clock_start = time.monotonic()
    with log_path.open("xb") as log_stream:
        result = subprocess.run(argv, cwd=root, stdout=log_stream, stderr=subprocess.STDOUT,
                                check=False)
    elapsed = time.monotonic() - clock_start
    finished = now_utc()
    confirmation.require(result.returncode == 0,
                         f"guarded command failed with exit code {result.returncode}; see {log_path}")
    return started, finished, elapsed


def verify_output_files(paths: list[Path], label: str) -> None:
    for path in paths:
        confirmation.require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
                             f"{label}: expected nonempty regular output is missing: {path}")


def run_canaries(root: Path, manifest_path: Path, manifest: dict[str, Any],
                 local_files: dict[str, Path], hashes: dict[str, str]) -> dict[str, Any]:
    raw_outputs: dict[str, dict[str, Path]] = {}
    for arm in ("C", "H"):
        arm_manifest = confirmation.manifest_arm(manifest, arm)
        environment = {**manifest["common_env"], **arm_manifest["env"]}
        game_command = [item if item != "{results}" else arm_manifest["results"]
                        for item in manifest["command"]]
        guard_only = guarded_canary_argv(environment, game_command, guard_only=True)
        subprocess.run(guard_only, cwd=root, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True)
        print(f"canary {arm} starting seed=989999", flush=True)
        log_path = root / arm_manifest["log"]
        started, finished, elapsed = execute(
            guarded_canary_argv(environment, game_command), root, log_path
        )
        trace_rel = arm_manifest["env"]["STS_OOC_MCTS_TRACE"]
        results_rel = arm_manifest["results"]
        paths = {
            "results": root / results_rel,
            "meta": root / (results_rel + ".meta.json"),
            "log": log_path,
            "trace": root / trace_rel,
            "support": root / (trace_rel + ".support.jsonl"),
            "actions": root / (trace_rel + ".actions.jsonl"),
        }
        verify_output_files(list(paths.values()), f"canary {arm}")
        receipt = {
            "schemaVersion": 1,
            "transport": merger.TRANSPORT_NAME,
            "arm": arm,
            "seed": 989999,
            "environmentPolicy": "clean-env-i",
            "environment": environment,
            "guardedArgv": guarded_canary_argv(environment, game_command),
            "seedGuardSha256": merger.FROZEN_SEED_GUARD_SHA256,
            "artifactSha256": hashes,
            "startedAtUtc": started,
            "finishedAtUtc": finished,
            "elapsedSeconds": elapsed,
            "exitCode": 0,
        }
        receipt_path = root / f"canaries/{arm}/transport.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
        raw_outputs[arm] = paths
        print(f"canary {arm} completed; outcome excluded from quality analysis", flush=True)

    normalized_dirs: dict[str, Path] = {}
    for arm, output_name in (("C", "standard"), ("H", "hybrid")):
        destination = root / "canary" / output_name
        destination.mkdir(parents=True)
        for source_key, target_name in (
            ("results", "results.csv"),
            ("meta", "results.csv.meta.json"),
            ("log", "run.log"),
            ("trace", "mcts.csv"),
            ("support", "mcts.csv.support.jsonl"),
            ("actions", "mcts.csv.actions.jsonl"),
        ):
            shutil.copyfile(raw_outputs[arm][source_key], destination / target_name)
        normalized_dirs[arm] = destination

    report = canary_validator.validate_canary(
        manifest_path, normalized_dirs["C"], normalized_dirs["H"], local_files, hashes
    )
    confirmation.require(report["status"] == "CANARY_MECHANISM_AND_PROVENANCE_PASS",
                         "both local canaries failed mechanism/provenance validation")
    (root / "canary-validation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("both canary validations PASS; starting paired 128-seed chunks", flush=True)
    return report


def run_confirmation_chunks(root: Path, manifest_path: Path, manifest: dict[str, Any],
                            plan_path: Path, local_files: dict[str, Path]) -> None:
    chunks_root = root / "chunks"
    chunks_root.mkdir()
    for spec in merger.expected_specs():
        directory = chunks_root / spec["id"]
        directory.mkdir()
        environment = merger.expected_environment(manifest, spec)
        game_command = merger.expected_game_command(manifest, spec)
        print(f"chunk {spec['id']} starting seeds={spec['seedStart']}..{spec['seedEnd']}",
              flush=True)
        started, finished, elapsed = execute(
            merger.guarded_argv(environment, game_command), root, directory / "run.log"
        )
        trace = directory / "mcts.csv"
        output_files = [
            directory / "results.csv",
            directory / "results.csv.meta.json",
            directory / "run.log",
            trace,
            directory / "mcts.csv.support.jsonl",
            directory / "mcts.csv.actions.jsonl",
        ]
        verify_output_files(output_files, f"chunk {spec['id']}")
        merger.write_transport_receipt(
            directory / "transport.json", plan_path, root, manifest, spec,
            local_files, environment, started, finished, elapsed,
        )
        print(f"chunk {spec['id']} completed exit=0", flush=True)


def run_frozen_confirmation(work_root: Path) -> dict[str, Any]:
    confirmation_manifest = confirmation.read_manifest(CONFIRMATION_MANIFEST)
    canary_manifest = confirmation.read_manifest(CANARY_MANIFEST)
    sources = source_files()
    guard_bytes = frozen_guard_bytes()
    hashes = assert_frozen_sources(sources, guard_bytes)
    confirmation.require(hashes["binary"] == confirmation_manifest["binary"]["sha256"],
                         "frozen binary differs from confirmation manifest")
    confirmation.require(hashes["binary"] == canary_manifest["binary"]["sha256"],
                         "frozen binary differs from canary manifest")

    target_paths = all_target_paths(work_root, canary_manifest)
    check_fresh_paths(work_root, target_paths)
    work_root.parent.mkdir(parents=True, exist_ok=True)
    work_root.mkdir()
    local_files, guard_path = stage_assets(work_root, confirmation_manifest, sources,
                                           guard_bytes, hashes)
    (work_root / "results").mkdir()
    (work_root / "logs").mkdir()
    confirmation.validate_manifest(confirmation_manifest, local_files, hashes)
    confirmation.validate_manifest(canary_manifest, local_files, hashes,
                                    seed_start=989999, seed_count=1)

    transport_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                            text=True).strip()
    plan = merger.build_transport_plan(CONFIRMATION_MANIFEST, work_root, local_files,
                                       guard_path, transport_sha, hashes)
    plan_path = work_root / "transport-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Mechanically prove every invocation stays within the historical frozen guard's 128-seed cap
    # before the first canary starts. This invokes only seed_guard.sh guard-only.
    for arm in ("C", "H"):
        arm_manifest = confirmation.manifest_arm(canary_manifest, arm)
        env = {**canary_manifest["common_env"], **arm_manifest["env"]}
        command = [item if item != "{results}" else arm_manifest["results"]
                   for item in canary_manifest["command"]]
        subprocess.run(guarded_canary_argv(env, command, guard_only=True), cwd=work_root,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for spec in merger.expected_specs():
        env = merger.expected_environment(confirmation_manifest, spec)
        command = merger.expected_game_command(confirmation_manifest, spec)
        subprocess.run(merger.guarded_argv(env, ["guard-only", *command]), cwd=work_root,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    canary_report = run_canaries(work_root, CANARY_MANIFEST, canary_manifest,
                                  local_files, hashes)
    run_confirmation_chunks(work_root, CONFIRMATION_MANIFEST, confirmation_manifest,
                            plan_path, local_files)

    merged_root = work_root / "merged"
    merge_report = merger.merge_chunks(CONFIRMATION_MANIFEST, work_root, merged_root, hashes)
    print("all eight chunks merged and receipt validation PASS", flush=True)

    analysis_dir = work_root / "analysis"
    analysis_dir.mkdir()
    summary_path = analysis_dir / "summary.json"
    per_seed_path = analysis_dir / "per-seed.csv"
    command = [
        sys.executable,
        str(TOOLS_DIR / "analyze_deepset_entropic_brew_hybrid_confirmation.py"),
        "--standard", str(merged_root / "standard"),
        "--hybrid", str(merged_root / "hybrid"),
        "--manifest", str(CONFIRMATION_MANIFEST),
        "--binary", str(local_files["binary"]),
        "--standard-ctm", str(local_files["standard_ctm"]),
        "--fast-ctm", str(local_files["fast_ctm"]),
        "--v4-policy", str(local_files["v4_policy"]),
        "--floor-model", str(local_files["floor_model"]),
        "--win-model", str(local_files["win_model"]),
        "--summary", str(summary_path),
        "--per-seed", str(per_seed_path),
    ]
    print("all chunks are complete; running the unchanged frozen analyzer", flush=True)
    analyzer = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    (analysis_dir / "analyzer.stdout.json").write_text(analyzer.stdout, encoding="utf-8")
    if analyzer.returncode != 0:
        raise confirmation.EvidenceError(
            f"frozen analyzer failed with exit {analyzer.returncode}: {analyzer.stderr.strip()}"
        )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    completion = {
        "schemaVersion": 1,
        "status": "COMPLETE",
        "transport": merger.TRANSPORT_NAME,
        "scientificProtocolChanged": False,
        "frozenSourceGitSha": confirmation.FROZEN_SHA,
        "transportToolGitSha": transport_sha,
        "binarySha256": hashes["binary"],
        "seedRange": [confirmation.SEED_START,
                      confirmation.SEED_START + confirmation.SEED_COUNT - 1],
        "seedCountPerArm": confirmation.SEED_COUNT,
        "chunkCountPerArm": 4,
        "executionOrder": list(merger.CHUNK_IDS),
        "canaryValidation": canary_report["status"],
        "qualityClassification": summary["classification"],
        "mergeReportSha256": confirmation.sha256(merged_root / "merge-report.json"),
        "summarySha256": confirmation.sha256(summary_path),
        "perSeedSha256": confirmation.sha256(per_seed_path),
    }
    (work_root / "transport-completion.json").write_text(
        json.dumps(completion, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--preflight-only", action="store_true",
                        help="verify pins, collisions, and historical frozen guard without writing outputs or running seeds")
    args = parser.parse_args()
    try:
        if args.preflight_only:
            preflight_only(args.work_root.resolve())
            return 0
        summary = run_frozen_confirmation(args.work_root.resolve())
    except (confirmation.EvidenceError, OSError, ValueError, subprocess.CalledProcessError,
            json.JSONDecodeError) as exc:
        print(f"local confirmation STOPPED: {exc}", file=sys.stderr, flush=True)
        return 2
    print(f"local confirmation complete: {summary['classification']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
