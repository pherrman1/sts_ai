#!/usr/bin/env python3
"""Run the potion-specialist experiment from its fixed historical source.

Create a clean worktree at EXPECTED_EXPERIMENT_SHA with
tools/agent/worktree.py, then invoke this wrapper from a newer checkout. The
low-level trainer in the historical worktree receives fixed provenance
arguments only after this wrapper verifies that worktree's actual Git state.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


EXPECTED_BASE_SHA = "c62f3694517bf622d2670a9fbf3c20a70380a763"
EXPECTED_EXPERIMENT_SHA = "3d1db667f0859c5a1d4788cb4232eaf6f6670bb7"
TRAINER_RELATIVE_PATH = Path("tools/combat_transition_deepset_potion_specialist.py")


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source_root), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def validate_source_worktree(source_worktree: Path) -> Path:
    source_root = Path(git(source_worktree, "rev-parse", "--show-toplevel")).resolve()
    head = git(source_root, "rev-parse", "HEAD")
    if head != EXPECTED_EXPERIMENT_SHA:
        raise ValueError(
            "experiment source worktree must be checked out at "
            f"{EXPECTED_EXPERIMENT_SHA}; got {head}"
        )
    if git(source_root, "status", "--porcelain"):
        raise ValueError("experiment source worktree must be clean")
    if subprocess.run(
        ["git", "-C", str(source_root), "merge-base", "--is-ancestor",
         EXPECTED_BASE_SHA, EXPECTED_EXPERIMENT_SHA], check=False
    ).returncode != 0:
        raise ValueError("pinned experiment commit is not descended from the pinned baseline")
    trainer = source_root / TRAINER_RELATIVE_PATH
    if not trainer.is_file():
        raise ValueError(f"pinned experiment trainer is missing: {trainer}")
    return source_root


def build_command(source_root: Path, args: argparse.Namespace) -> list[str]:
    trainer = source_root / TRAINER_RELATIVE_PATH
    return [sys.executable, "-s", str(trainer),
            "--artifact-root", str(args.artifact_root.resolve()),
            "--output-dir", str(args.output_dir.resolve()),
            "--encoder-checkpoint", str(args.encoder_checkpoint.resolve()),
            "--decoder-checkpoint", str(args.decoder_checkpoint.resolve()),
            "--dedicated-component", str(args.dedicated_component.resolve()),
            "--reference-receipt", str(args.reference_receipt.resolve()),
            "--base-sha", EXPECTED_BASE_SHA,
            "--experiment-sha", EXPECTED_EXPERIMENT_SHA]


def child_environment(
    source_root: Path, base_env: dict[str, str] | None = None
) -> dict[str, str]:
    """Preserve runtime/GPU settings while isolating Python module resolution."""
    env = os.environ.copy() if base_env is None else dict(base_env)
    env["PYTHONPATH"] = str(source_root)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-worktree", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--encoder-checkpoint", type=Path, required=True)
    parser.add_argument("--decoder-checkpoint", type=Path, required=True)
    parser.add_argument("--dedicated-component", type=Path, required=True)
    parser.add_argument("--reference-receipt", type=Path, required=True)
    parser.add_argument("--print-command", action="store_true",
                        help="validate provenance and print the fixed child command without running it")
    args = parser.parse_args()
    source_root = validate_source_worktree(args.source_worktree)
    command = build_command(source_root, args)
    if args.print_command:
        print(json.dumps(command, indent=2))
        return
    subprocess.run(
        command, cwd=source_root, env=child_environment(source_root), check=True
    )


if __name__ == "__main__":
    main()
