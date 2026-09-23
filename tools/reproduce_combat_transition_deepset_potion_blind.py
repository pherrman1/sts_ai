#!/usr/bin/env python3
"""Run the frozen potion-blind paired experiment from a clean source checkout."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys


EXPECTED_BASE_SHA = "1ed96f2aa564742156cc6593a1fc1915ea4e9033"
TRAINER_RELATIVE_PATH = Path("tools/combat_transition_deepset_potion_specialist.py")


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source_root), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def validate_source_worktree(source_worktree: Path) -> tuple[Path, str]:
    source_root = Path(git(source_worktree, "rev-parse", "--show-toplevel")).resolve()
    head = git(source_root, "rev-parse", "HEAD")
    if git(source_root, "status", "--porcelain"):
        raise ValueError("experiment source worktree must be clean")
    if subprocess.run(
        ["git", "-C", str(source_root), "merge-base", "--is-ancestor",
         EXPECTED_BASE_SHA, head], check=False
    ).returncode != 0:
        raise ValueError("experiment source checkout is not descended from the pinned baseline")
    if not (source_root / TRAINER_RELATIVE_PATH).is_file():
        raise ValueError(f"pinned experiment trainer is missing: {TRAINER_RELATIVE_PATH}")
    return source_root, head


def build_command(source_root: Path, experiment_sha: str, args: argparse.Namespace) -> list[str]:
    trainer = source_root / TRAINER_RELATIVE_PATH
    return [sys.executable, str(trainer),
            "--artifact-root", str(args.artifact_root.resolve()),
            "--output-dir", str(args.output_dir.resolve()),
            "--encoder-checkpoint", str(args.encoder_checkpoint.resolve()),
            "--decoder-checkpoint", str(args.decoder_checkpoint.resolve()),
            "--dedicated-component", str(args.dedicated_component.resolve()),
            "--reference-receipt", str(args.reference_receipt.resolve()),
            "--reference-decoder", str(args.reference_decoder.resolve()),
            "--base-sha", EXPECTED_BASE_SHA,
            "--experiment-sha", experiment_sha]


def child_environment(source_root: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy() if base_env is None else dict(base_env)
    env["PYTHONPATH"] = str(source_root)
    # This experiment's pinned CUDA PyTorch is installed in the system Python
    # user site; keep that dependency path available while source code resolves
    # first from the validated checkout.
    env.pop("PYTHONNOUSERSITE", None)
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
    parser.add_argument("--reference-decoder", type=Path, required=True)
    parser.add_argument("--print-command", action="store_true")
    args = parser.parse_args()
    source_root, experiment_sha = validate_source_worktree(args.source_worktree)
    command = build_command(source_root, experiment_sha, args)
    if args.print_command:
        print("sourceSha=" + experiment_sha)
        print("python=" + sys.executable + " " + platform.python_version())
        print(" ".join(command))
        return
    subprocess.run(command, cwd=source_root,
                   env=child_environment(source_root), check=True)


if __name__ == "__main__":
    main()
