#!/usr/bin/env python3
"""Small, repository-owned launcher for the designated GCP benchmark VM.

This helper deliberately operates only through the existing ``gcloud compute``
SSH path. It does not create, resize, delete, or reconfigure cloud resources;
credentials remain in the user's local gcloud configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

PROJECT = "sts-ai-502709"
ZONE = "europe-west3-c"
INSTANCE = "sts-test"
REMOTE_USER = "philippherrmann"
REMOTE_ROOT = "/home/philippherrmann/sts_sweep"
RESEARCH_CONTEXT = "sts-test"
WINDOWS_GCLOUD = (
    r"C:\Users\pherrman\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
MANIFEST_KEYS = {
    "schema_version", "experiment_id", "frozen_sha", "checkout", "build_dir",
    "binary", "artifacts", "common_env", "required_env",
    "expect_silver_telemetry", "command", "arms",
}


def gcloud_path() -> str:
    candidates = []
    if os.environ.get("STS_GCLOUD"):
        candidates.append(os.environ["STS_GCLOUD"])
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if found:
        candidates.append(found)
    candidates.extend(WINDOWS_GCLOUD)
    # WSL exposes the same documented Windows SDK locations under /mnt/c.
    candidates.extend(
        "/mnt/c/" + path[3:].replace("\\", "/")
        for path in WINDOWS_GCLOUD
        if path.startswith("C:\\")
    )
    for candidate in candidates:
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
    raise RuntimeError(
        "gcloud was not found; install/configure the Google Cloud SDK or set STS_GCLOUD"
    )


def common_args(args: argparse.Namespace) -> list[str]:
    return [
        f"--project={args.project}",
        f"--zone={args.zone}",
    ]


def require_designated_target(args: argparse.Namespace, action: str) -> None:
    expected = {
        "project": PROJECT,
        "zone": ZONE,
        "instance": INSTANCE,
        "user": REMOTE_USER,
        "remote_root": REMOTE_ROOT,
    }
    mismatches = [
        f"{name}={getattr(args, name)!r} (expected {value!r})"
        for name, value in expected.items()
        if getattr(args, name) != value
    ]
    if mismatches:
        raise ValueError(
            f"{action} is restricted to the designated GCP target: "
            + ", ".join(mismatches)
        )


def run_gcloud(args: argparse.Namespace, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([gcloud_path(), *command, *common_args(args)], text=True)


def ssh_command(args: argparse.Namespace, remote: str) -> int:
    command = [
        gcloud_path(),
        "compute",
        "ssh",
        f"{args.user}@{args.instance}",
        *common_args(args),
        "--command",
        remote,
    ]
    return subprocess.run(command, check=False).returncode


def designated_remote_path(args: argparse.Namespace, relative: str, action: str) -> str:
    require_designated_target(args, action)
    components = relative.split("/")
    if any(
        component in {"", ".", ".."}
        or re.fullmatch(r"[A-Za-z0-9._-]+", component) is None
        for component in components
    ):
        raise ValueError(
            f"{action} remote path components may contain only ASCII letters, digits, '.', '_', and '-'"
        )
    path = PurePosixPath(relative)
    if path.is_absolute():
        raise ValueError(
            f"{action} remote path must be relative to the designated remote root"
        )
    return str(PurePosixPath(args.remote_root) / path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _remote_file(value: object, label: str) -> dict[str, str]:
    _require(isinstance(value, dict) and set(value) == {"remote_path", "sha256"},
             f"manifest {label} must contain exactly remote_path and sha256")
    path = value["remote_path"]
    digest = value["sha256"]
    _require(isinstance(path, str) and path, f"manifest {label}.remote_path must be non-empty")
    _require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None,
             f"manifest {label}.sha256 must be lowercase SHA-256")
    return {"remote_path": path, "sha256": digest}


def load_run_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read run manifest {path}: {exc}") from exc
    _require(isinstance(payload, dict) and set(payload) == MANIFEST_KEYS,
             "run manifest has unknown or missing top-level fields")
    _require(payload["schema_version"] == 1, "unsupported run manifest schema_version")
    _require(isinstance(payload["experiment_id"], str)
             and re.fullmatch(r"[A-Za-z0-9._-]+", payload["experiment_id"]) is not None,
             "manifest experiment_id must be a safe non-empty identifier")
    _require(isinstance(payload["frozen_sha"], str)
             and SHA_RE.fullmatch(payload["frozen_sha"]) is not None,
             "manifest frozen_sha must be a lowercase full Git SHA")
    for key in ("checkout", "build_dir"):
        _require(isinstance(payload[key], str) and payload[key],
                 f"manifest {key} must be a non-empty remote path")
    payload["binary"] = _remote_file(payload["binary"], "binary")
    _require(isinstance(payload["artifacts"], list), "manifest artifacts must be a list")
    payload["artifacts"] = [
        _remote_file(item, f"artifacts[{index}]")
        for index, item in enumerate(payload["artifacts"])
    ]
    all_files = [payload["binary"], *payload["artifacts"]]
    file_paths = [item["remote_path"] for item in all_files]
    _require(len(file_paths) == len(set(file_paths)), "manifest binary/artifact paths must be unique")

    common_env = payload["common_env"]
    _require(isinstance(common_env, dict)
             and all(isinstance(k, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", k)
                     and isinstance(v, str) and v for k, v in common_env.items()),
             "manifest common_env must map safe variable names to non-empty strings")
    _require(common_env.get("STS_EXECUTABLE_GIT_SHA") == payload["frozen_sha"],
             "manifest STS_EXECUTABLE_GIT_SHA must equal frozen_sha")
    required_env = payload["required_env"]
    _require(isinstance(required_env, list) and len(required_env) == len(set(required_env))
             and all(isinstance(v, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", v)
                     for v in required_env),
             "manifest required_env must contain unique safe variable names")
    mandatory_env = {"OMP_NUM_THREADS", "STS_EXECUTABLE_GIT_SHA"}
    _require(mandatory_env <= set(required_env),
             "manifest required_env must include OMP_NUM_THREADS and STS_EXECUTABLE_GIT_SHA")
    try:
        omp_threads = int(common_env["OMP_NUM_THREADS"])
    except (KeyError, ValueError) as exc:
        raise ValueError("manifest OMP_NUM_THREADS must be a positive integer") from exc
    _require(omp_threads > 0, "manifest OMP_NUM_THREADS must be a positive integer")
    _require(isinstance(payload["expect_silver_telemetry"], bool),
             "manifest expect_silver_telemetry must be boolean")
    if payload["expect_silver_telemetry"]:
        _require("STS_SILVER_TELEMETRY" in required_env,
                 "Silver telemetry expectation requires STS_SILVER_TELEMETRY in required_env")

    command = payload["command"]
    _require(isinstance(command, list) and all(isinstance(v, str) and v for v in command),
             "manifest command must be a list of non-empty strings")
    _require(command.count("{results}") == 1 and command[-1] == "{results}",
             "manifest command must end with exactly one {results} placeholder")
    _require(command[0] == payload["binary"]["remote_path"],
             "manifest command executable must equal binary.remote_path")
    _require("bestbench" in command, "manifest command must invoke bestbench")
    mode = command.index("bestbench")
    _require(mode == len(command) - 6,
             "manifest bestbench command must be: executable bestbench sims nSeeds asc seed results")
    try:
        sims, seeds, _asc, _seed = map(int, command[mode + 1:mode + 5])
    except ValueError as exc:
        raise ValueError("manifest bestbench numeric arguments must be integers") from exc
    _require(sims > 0 and seeds > 0, "manifest simulations and seed count must be positive")

    arms = payload["arms"]
    _require(isinstance(arms, list) and arms, "manifest arms must be a non-empty list")
    names: list[str] = []
    for index, arm in enumerate(arms):
        _require(isinstance(arm, dict) and set(arm) == {"name", "results", "log", "env"},
                 f"manifest arms[{index}] has unknown or missing fields")
        _require(isinstance(arm["name"], str)
                 and re.fullmatch(r"[A-Za-z0-9._-]+", arm["name"]) is not None,
                 f"manifest arms[{index}].name must be a safe identifier")
        for key in ("results", "log"):
            _require(isinstance(arm[key], str) and arm[key],
                     f"manifest arms[{index}].{key} must be a non-empty remote path")
        env = arm["env"]
        _require(isinstance(env, dict)
                 and all(isinstance(k, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", k)
                         and isinstance(v, str) and v for k, v in env.items()),
                 f"manifest arms[{index}].env must map safe names to non-empty strings")
        overlap = sorted(set(common_env) & set(env))
        _require(not overlap,
                 f"manifest arm {arm['name']} overrides common_env: {', '.join(overlap)}")
        merged = {**common_env, **env}
        missing = [name for name in required_env if not merged.get(name)]
        _require(not missing, f"manifest arm {arm['name']} is missing required env: {', '.join(missing)}")
        if payload["expect_silver_telemetry"]:
            try:
                telemetry = int(merged["STS_SILVER_TELEMETRY"])
            except ValueError as exc:
                raise ValueError("STS_SILVER_TELEMETRY must be a nonzero integer") from exc
            _require(telemetry != 0, "STS_SILVER_TELEMETRY must be nonzero for every arm")
        names.append(arm["name"])
    _require(len(names) == len(set(names)), "manifest arm names must be unique")
    expanded_outputs = [
        path
        for arm in arms
        for path in (arm["results"], arm["results"] + ".meta.json", arm["log"])
    ]
    _require(len(expanded_outputs) == len(set(expanded_outputs)),
             "manifest result/log/sidecar paths must be unique across arms")
    _require(not (set(expanded_outputs) & set(file_paths)),
             "manifest outputs must not overwrite the binary or an artifact")
    return payload


def manifest_arm(manifest: dict, name: str) -> tuple[list[str], str, list[str]]:
    arm = next((item for item in manifest["arms"] if item["name"] == name), None)
    if arm is None:
        raise ValueError(f"manifest has no arm named {name!r}")
    env = {**manifest["common_env"], **arm["env"]}
    command = [arm["results"] if token == "{results}" else token
               for token in manifest["command"]]
    rendered = ["env", *(f"{key}={env[key]}" for key in sorted(env)), *command]
    fresh = [arm["results"], arm["results"] + ".meta.json", arm["log"]]
    return rendered, arm["log"], fresh


def copy_to(args: argparse.Namespace) -> int:
    remote = designated_remote_path(args, args.remote_path, "copy-to")
    local = Path(args.local_path)
    if not local.is_file():
        raise ValueError(f"copy-to local source is not a file: {local}")
    if args.expect_sha256:
        expected = args.expect_sha256
        if SHA256_RE.fullmatch(expected) is None:
            raise ValueError("copy-to --expect-sha256 must be a lowercase SHA-256")
        actual = sha256_file(local)
        if actual != expected:
            raise ValueError(f"copy-to local SHA-256 mismatch: {actual} != {expected}")
    result = run_gcloud(
        args, "compute", "scp", str(local), f"{args.user}@{args.instance}:{remote}"
    ).returncode
    if result or not args.expect_sha256:
        return result
    verify = (
        f"test -f {shlex.quote(remote)}; "
        f"test \"$(sha256sum {shlex.quote(remote)} | cut -d' ' -f1)\" = {args.expect_sha256.lower()}; "
        f"echo copy_sha256_verified={args.expect_sha256.lower()}"
    )
    return ssh_command(args, verify)


def copy_from(args: argparse.Namespace) -> int:
    remote = designated_remote_path(args, args.remote_path, "copy-from")
    return run_gcloud(
        args, "compute", "scp", f"{args.user}@{args.instance}:{remote}", args.local_path
    ).returncode


def job_status(args: argparse.Namespace) -> int:
    require_designated_target(args, "job-status")
    if args.pid <= 0:
        raise ValueError("job-status PID must be positive")
    remote = (
        f"if ps -p {args.pid} -o pid=,etime=,stat=,args=; then "
        "echo job_status=running; else echo job_status=not_running_or_unknown; fi"
    )
    return ssh_command(args, remote)


def status(args: argparse.Namespace) -> int:
    result = subprocess.run(
        [
            gcloud_path(),
            "compute",
            "instances",
            "describe",
            args.instance,
            *common_args(args),
            "--format=value(status)",
        ],
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def start_instance(args: argparse.Namespace) -> int:
    require_designated_target(args, "start-instance")
    state = subprocess.run(
        [
            gcloud_path(),
            "compute",
            "instances",
            "describe",
            args.instance,
            *common_args(args),
            "--format=value(status)",
        ],
        text=True,
        capture_output=True,
    )
    if state.returncode:
        print(state.stderr, end="", file=sys.stderr)
        return state.returncode
    current = state.stdout.strip()
    print(f"instance={args.instance} state={current}")
    if current == "RUNNING":
        return 0
    return run_gcloud(args, "compute", "instances", "start", args.instance).returncode


def probe(args: argparse.Namespace) -> int:
    remote = f"hostname; uptime; test -d {shlex.quote(args.remote_root)} && echo remote_root=present"
    return ssh_command(args, remote)


def remote_run(args: argparse.Namespace) -> int:
    require_designated_target(args, "run")
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("run requires a command after --")
    command_text = shlex.join(command)
    guard_mode = "guard-only " if args.guard_only else ""
    guard = (
        "env STS_GCP_RESEARCH_CONTEXT=sts-test "
        f"bash tools/seed_guard.sh --gcp-research {guard_mode}{command_text}"
    )
    check = "ps -eo pid=,comm= | awk '$2 == \"one_combat\" {print; found=1} END {exit !found}' || true"
    if args.guard_only:
        check = ":"
    elif args.allow_parallel:
        check = "echo parallel_run_explicitly_allowed; " + check
    else:
        check = (
            "if ps -eo pid=,comm= | awk '$2 == \"one_combat\" {print; found=1} END {exit !found}' >/tmp/sts_benchmark_active; then "
            "echo 'active one_combat process found; rerun with --allow-parallel only when intentional' >&2; "
            "cat /tmp/sts_benchmark_active >&2; rm -f /tmp/sts_benchmark_active; exit 2; "
            "fi"
        )
    fresh_paths = getattr(args, "fresh_paths", [])
    if fresh_paths:
        absolute = [designated_remote_path(args, path, "run-manifest") for path in fresh_paths]
        clauses = " ".join(
            f"test ! -e {shlex.quote(path)} || {{ echo 'refusing existing output: {path}' >&2; exit 2; }};"
            for path in absolute
        )
        check = clauses + " " + check

    if args.foreground:
        remote = (
            "set -euo pipefail; "
            f"cd {shlex.quote(args.remote_root)}; "
            "test -f tools/seed_guard.sh; command -v bash >/dev/null; "
            f"{check}; exec {guard}"
        )
        return ssh_command(args, remote)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log = args.log or f"{args.remote_root}/logs/gcp_benchmark_{stamp}.log"
    remote = (
        "set -euo pipefail; "
        f"cd {shlex.quote(args.remote_root)}; "
        "test -f tools/seed_guard.sh; command -v bash >/dev/null; "
        "command -v nohup >/dev/null; mkdir -p logs; "
        f"{check}; "
        f"nohup {guard} >{shlex.quote(log)} 2>&1 < /dev/null & pid=$!; "
        f"echo remote_pid=$pid; echo remote_log={shlex.quote(log)}"
    )
    return ssh_command(args, remote)


def manifest_check(args: argparse.Namespace) -> int:
    manifest = load_run_manifest(args.manifest)
    for item in (manifest["binary"], *manifest["artifacts"]):
        designated_remote_path(args, item["remote_path"], "manifest-check")
    designated_remote_path(args, manifest["checkout"], "manifest-check")
    designated_remote_path(args, manifest["build_dir"], "manifest-check")
    for arm in manifest["arms"]:
        designated_remote_path(args, arm["results"], "manifest-check")
        designated_remote_path(args, arm["log"], "manifest-check")
    print(
        f"research_manifest PASS experiment={manifest['experiment_id']} "
        f"sha={manifest['frozen_sha']} arms={len(manifest['arms'])} "
        f"telemetry_required={str(manifest['expect_silver_telemetry']).lower()}"
    )
    return 0


def manifest_run(args: argparse.Namespace) -> int:
    manifest_check(args)
    manifest = load_run_manifest(args.manifest)
    command, log, fresh = manifest_arm(manifest, args.arm)
    args.command = command
    args.log = log
    args.fresh_paths = fresh
    return remote_run(args)


def exact_sha_preflight(args: argparse.Namespace) -> int:
    require_designated_target(args, "exact-sha-preflight")
    manifest = load_run_manifest(args.manifest)
    checkout = designated_remote_path(args, manifest["checkout"], "exact-sha-preflight")
    build_dir = designated_remote_path(args, manifest["build_dir"], "exact-sha-preflight")
    binary = designated_remote_path(args, manifest["binary"]["remote_path"], "exact-sha-preflight")
    commands = [
        "set -euo pipefail",
        f"test \"$(git -C {shlex.quote(checkout)} rev-parse HEAD)\" = {manifest['frozen_sha']}",
        f"test -z \"$(git -C {shlex.quote(checkout)} status --porcelain --untracked-files=no)\"",
        f"test -f {shlex.quote(build_dir + '/CMakeCache.txt')}",
        f"grep -Fx {shlex.quote('CMAKE_HOME_DIRECTORY:INTERNAL=' + checkout)} "
        f"{shlex.quote(build_dir + '/CMakeCache.txt')} >/dev/null",
    ]
    for item, path in [
        (manifest["binary"], binary),
        *[(item, designated_remote_path(args, item["remote_path"], "exact-sha-preflight"))
          for item in manifest["artifacts"]],
    ]:
        commands.extend([
            f"test -f {shlex.quote(path)}",
            f"test \"$(sha256sum {shlex.quote(path)} | cut -d' ' -f1)\" = {item['sha256']}",
        ])
    commands.append(
        f"echo exact_sha_preflight=PASS experiment={manifest['experiment_id']} "
        f"sha={manifest['frozen_sha']} files={1 + len(manifest['artifacts'])}"
    )
    return ssh_command(args, "; ".join(commands))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", default=PROJECT)
    p.add_argument("--zone", default=ZONE)
    p.add_argument("--instance", default=INSTANCE)
    p.add_argument("--user", default=REMOTE_USER)
    p.add_argument("--remote-root", default=REMOTE_ROOT)
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("probe", help="SSH and report hostname, uptime, and remote root")
    sub.add_parser("status", help="report the existing instance state")
    sub.add_parser("start-instance", help="start sts-test when it is stopped")
    copy_to_parser = sub.add_parser(
        "copy-to", help="copy one local file beneath the designated remote root"
    )
    copy_to_parser.add_argument("local_path")
    copy_to_parser.add_argument("remote_path")
    copy_to_parser.add_argument("--expect-sha256")
    copy_from_parser = sub.add_parser(
        "copy-from", help="copy one file from beneath the designated remote root"
    )
    copy_from_parser.add_argument("remote_path")
    copy_from_parser.add_argument("local_path")
    job = sub.add_parser("job-status", help="report whether a detached remote PID is running")
    job.add_argument("pid", type=int)
    run = sub.add_parser("run", help="guard and launch a detached remote benchmark")
    run.add_argument("--foreground", action="store_true")
    run.add_argument("--guard-only", action="store_true")
    run.add_argument("--allow-parallel", action="store_true")
    run.add_argument("--log")
    run.add_argument("command", nargs=argparse.REMAINDER)
    manifest = sub.add_parser("manifest-check", help="validate a decision-bearing run manifest locally")
    manifest.add_argument("manifest", type=Path)
    manifest_run_parser = sub.add_parser("run-manifest", help="validate and launch one manifest arm")
    manifest_run_parser.add_argument("manifest", type=Path)
    manifest_run_parser.add_argument("arm")
    manifest_run_parser.add_argument("--foreground", action="store_true")
    manifest_run_parser.add_argument("--guard-only", action="store_true")
    manifest_run_parser.add_argument("--allow-parallel", action="store_true")
    preflight = sub.add_parser(
        "exact-sha-preflight", help="verify remote checkout, CMake source binding, and file hashes"
    )
    preflight.add_argument("manifest", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "probe":
            return probe(args)
        if args.action == "status":
            return status(args)
        if args.action == "start-instance":
            return start_instance(args)
        if args.action == "copy-to":
            return copy_to(args)
        if args.action == "copy-from":
            return copy_from(args)
        if args.action == "job-status":
            return job_status(args)
        if args.action == "manifest-check":
            return manifest_check(args)
        if args.action == "run-manifest":
            return manifest_run(args)
        if args.action == "exact-sha-preflight":
            return exact_sha_preflight(args)
        return remote_run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"gcp_benchmark: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
