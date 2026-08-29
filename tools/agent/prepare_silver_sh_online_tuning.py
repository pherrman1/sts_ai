#!/usr/bin/env python3
"""Emit exact-SHA GCP manifests for the preregistered online SH tuner."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHAPES = ("half", "gentle", "aggressive", "screen_two")
ALLOCATIONS = ("finalist_heavy", "balanced", "cautious")
SHA_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REQUIRED_ARTIFACTS = {
    "models/v_rich_trees.txt",
    "models/v_win_trees.txt",
    "models/v_combat_7k_tuned.txt",
}


def schedule(value: str) -> tuple[str, str]:
    try:
        shape, allocation = value.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("schedule must be SHAPE:ALLOCATION") from exc
    if shape not in SHAPES or allocation not in ALLOCATIONS:
        raise argparse.ArgumentTypeError(
            f"schedule must use {SHAPES} and {ALLOCATIONS}")
    return shape, allocation


def artifact(value: str) -> dict[str, str]:
    try:
        remote_path, digest = value.rsplit(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("artifact must be REMOTE_PATH:SHA256") from exc
    if not remote_path or SHA256_RE.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError("artifact requires a path and lowercase SHA-256")
    return {"remote_path": remote_path, "sha256": digest}


def arm(name: str, experiment_id: str, env: dict[str, str]) -> dict:
    return {
        "name": name,
        "results": f"results/{experiment_id}-{name}.csv",
        "log": f"logs/{experiment_id}-{name}.log",
        "env": {"STS_EXPERIMENT_ARM": name, **env},
    }


def manifest(args: argparse.Namespace, experiment_id: str, budget: int,
             seeds: int, seed_lo: int, arms: list[dict]) -> dict:
    return {
        "schema_version": 2,
        "clear_env": True,
        "experiment_id": experiment_id,
        "frozen_sha": args.frozen_sha,
        "checkout": f"checkouts/{experiment_id}",
        "build_dir": f"checkouts/{experiment_id}/build/linux-gcc-release",
        "binary": {"remote_path": args.binary_remote, "sha256": args.binary_sha256},
        "artifacts": args.artifact,
        "common_env": {
            "OMP_NUM_THREADS": "24",
            "STS_EXECUTABLE_GIT_SHA": args.frozen_sha,
            "STS_FAIR": "1",
            "STS_SILVER_SEARCH": "1",
            "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
            "STS_SILVER_REUSE_CAP_MODE": "none",
            "STS_SILVER_ADAPTIVE": "0",
            "STS_SILVER_TELEMETRY": "1",
            "STS_VNET": "0",
            "STS_POLICY": "0",
        },
        "required_env": [
            "OMP_NUM_THREADS", "STS_EXECUTABLE_GIT_SHA", "STS_FAIR",
            "STS_SILVER_SEARCH", "STS_SILVER_EXACT_ROOT_BUDGETS",
            "STS_SILVER_REUSE_CAP_MODE", "STS_SILVER_ADAPTIVE",
            "STS_SILVER_TELEMETRY",
        ],
        "expect_silver_telemetry": True,
        "command": [
            args.binary_remote, "bestbench", str(budget), str(seeds), "0",
            str(seed_lo), "{results}",
        ],
        "arms": arms,
    }


def emit(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("broad", "narrow", "confirm"))
    parser.add_argument("--frozen-sha", required=True)
    parser.add_argument("--binary-remote", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--artifact", action="append", type=artifact, default=[])
    parser.add_argument("--schedule", action="append", type=schedule, default=[])
    parser.add_argument("--budget", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if SHA_RE.fullmatch(args.frozen_sha) is None:
        parser.error("--frozen-sha must be a lowercase full Git SHA")
    if SHA256_RE.fullmatch(args.binary_sha256) is None:
        parser.error("--binary-sha256 must be lowercase SHA-256")
    artifact_paths = {item["remote_path"] for item in args.artifact}
    if artifact_paths != REQUIRED_ARTIFACTS:
        parser.error("--artifact must provide exactly the three pinned runtime models: "
                     + ", ".join(sorted(REQUIRED_ARTIFACTS)))

    if args.stage == "broad":
        if args.schedule or args.budget is not None:
            parser.error("broad stage predeclares all schedules at budget 3000")
        experiment_id = "silver-sh-online-broad-933000"
        arms = [arm("uct-c25", experiment_id, {})]
        for shape in SHAPES:
            for allocation in ALLOCATIONS:
                name = f"sh-{shape}-{allocation}"
                arms.append(arm(name, experiment_id, {
                    "STS_SILVER_SH_SHAPE": shape,
                    "STS_SILVER_SH_ALLOCATION": allocation,
                }))
        emit(args.output, manifest(args, experiment_id, 3000, 16, 933000, arms))
        return 0

    if args.stage == "narrow":
        if not 1 <= len(args.schedule) <= 3 or args.budget is not None:
            parser.error("narrow stage requires one to three promoted --schedule values")
        args.output.mkdir(parents=True, exist_ok=True)
        for budget in (1000, 3000, 6000):
            experiment_id = f"silver-sh-online-narrow-{budget}-933100"
            arms = [arm("uct-c25", experiment_id, {})]
            for shape, allocation in args.schedule:
                name = f"sh-{shape}-{allocation}"
                arms.append(arm(name, experiment_id, {
                    "STS_SILVER_SH_SHAPE": shape,
                    "STS_SILVER_SH_ALLOCATION": allocation,
                }))
            emit(args.output / f"{experiment_id}.json",
                 manifest(args, experiment_id, budget, 64, 933100, arms))
        return 0

    if len(args.schedule) != 1 or args.budget not in (1000, 3000, 6000):
        parser.error("confirm stage requires one --schedule and --budget in {1000,3000,6000}")
    shape, allocation = args.schedule[0]
    experiment_id = f"silver-sh-online-confirm-{args.budget}-933300"
    arms = [
        arm("uct-c25", experiment_id, {}),
        arm("uct-c35", experiment_id, {"STS_SILVER_ROOT_EXPLORATION": "35"}),
        arm(f"sh-{shape}-{allocation}", experiment_id, {
            "STS_SILVER_SH_SHAPE": shape,
            "STS_SILVER_SH_ALLOCATION": allocation,
        }),
    ]
    emit(args.output, manifest(args, experiment_id, args.budget, 128, 933300, arms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
