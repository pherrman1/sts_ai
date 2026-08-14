#!/usr/bin/env python3
"""Small, repository-owned launcher for the designated GCP benchmark VM.

This helper deliberately operates only through the existing ``gcloud compute``
SSH path. It does not create, resize, delete, or reconfigure cloud resources;
credentials remain in the user's local gcloud configuration.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    run = sub.add_parser("run", help="guard and launch a detached remote benchmark")
    run.add_argument("--foreground", action="store_true")
    run.add_argument("--guard-only", action="store_true")
    run.add_argument("--allow-parallel", action="store_true")
    run.add_argument("--log")
    run.add_argument("command", nargs=argparse.REMAINDER)
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
        return remote_run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"gcp_benchmark: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())