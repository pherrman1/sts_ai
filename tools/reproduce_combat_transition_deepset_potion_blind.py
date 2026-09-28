#!/usr/bin/env python3
"""Run the frozen potion-blind paired experiment from a clean source checkout."""
from __future__ import annotations

import argparse
import importlib.machinery
import os
from pathlib import Path
import platform
import subprocess
import sys
import textwrap


EXPECTED_BASE_SHA = "1ed96f2aa564742156cc6593a1fc1915ea4e9033"
EXPECTED_EXPERIMENT_SHA = "cffe964a806891908ea1082bcca632683c4d2d37"
TRAINER_RELATIVE_PATH = Path("tools/combat_transition_deepset_potion_specialist.py")

CHILD_BOOTSTRAP = textwrap.dedent("""\
    import importlib.abc
    import importlib.machinery
    from pathlib import Path
    import runpy
    import sys
    import types

    source_root = Path(sys.argv[1]).resolve()
    tools_root = (source_root / "tools").resolve()
    if not tools_root.is_dir():
        raise SystemExit(f"validated source has no tools directory: {tools_root}")

    # Ignore a concrete `tools` package that site initialization may already
    # have imported. Recreate it as a package rooted only in this checkout.
    for name in tuple(sys.modules):
        if name == "tools" or name.startswith("tools."):
            del sys.modules[name]
    tools = types.ModuleType("tools")
    tools.__package__ = "tools"
    tools.__path__ = [str(tools_root)]
    tools.__spec__ = importlib.machinery.ModuleSpec(
        "tools", loader=None, is_package=True
    )
    tools.__spec__.submodule_search_locations = tools.__path__
    sys.modules["tools"] = tools

    class ValidatedToolsFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if not fullname.startswith("tools."):
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None:
                raise ModuleNotFoundError(
                    f"project module {fullname} is absent from {tools_root}"
                )
            locations = ([spec.origin] if spec.origin else
                         list(spec.submodule_search_locations or ()))
            for location in locations:
                resolved = Path(location).resolve()
                if not resolved.is_relative_to(tools_root):
                    raise ImportError(
                        f"project module {fullname} resolved outside validated "
                        f"source root: {resolved}"
                    )
            return spec

    sys.meta_path.insert(0, ValidatedToolsFinder())
    trainer = Path(sys.argv[2]).resolve()
    if not trainer.is_relative_to(source_root):
        raise SystemExit(f"trainer is outside validated source root: {trainer}")
    sys.argv = [str(trainer), *sys.argv[3:]]
    runpy.run_path(str(trainer), run_name="__main__")
""")


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source_root), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def validate_source_worktree(source_worktree: Path) -> tuple[Path, str]:
    source_root = Path(git(source_worktree, "rev-parse", "--show-toplevel")).resolve()
    head = git(source_root, "rev-parse", "HEAD")
    if git(source_root, "status", "--porcelain"):
        raise ValueError("experiment source worktree must be clean")
    if head != EXPECTED_EXPERIMENT_SHA:
        raise ValueError(
            "experiment source worktree must be checked out at pinned experiment "
            f"commit {EXPECTED_EXPERIMENT_SHA}; got {head}"
        )
    if subprocess.run(
        ["git", "-C", str(source_root), "merge-base", "--is-ancestor",
         EXPECTED_BASE_SHA, EXPECTED_EXPERIMENT_SHA], check=False
    ).returncode != 0:
        raise ValueError("experiment source checkout is not descended from the pinned baseline")
    if not (source_root / TRAINER_RELATIVE_PATH).is_file():
        raise ValueError(f"pinned experiment trainer is missing: {TRAINER_RELATIVE_PATH}")
    return source_root, EXPECTED_EXPERIMENT_SHA


def build_command(source_root: Path, args: argparse.Namespace) -> list[str]:
    trainer = source_root / TRAINER_RELATIVE_PATH
    return [sys.executable, "-c", CHILD_BOOTSTRAP, str(source_root), str(trainer),
            "--artifact-root", str(args.artifact_root.resolve()),
            "--output-dir", str(args.output_dir.resolve()),
            "--encoder-checkpoint", str(args.encoder_checkpoint.resolve()),
            "--decoder-checkpoint", str(args.decoder_checkpoint.resolve()),
            "--dedicated-component", str(args.dedicated_component.resolve()),
            "--reference-receipt", str(args.reference_receipt.resolve()),
            "--reference-decoder", str(args.reference_decoder.resolve()),
            "--base-sha", EXPECTED_BASE_SHA,
            "--experiment-sha", EXPECTED_EXPERIMENT_SHA]


def child_environment(source_root: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy() if base_env is None else dict(base_env)
    env["PYTHONPATH"] = str(source_root)
    # This experiment's pinned CUDA PyTorch is installed in the system Python
    # user site; keep that dependency path available. CHILD_BOOTSTRAP pins all
    # `tools` imports to the validated checkout even if site initialization
    # imports a concrete user-site `tools` package first.
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
    source_root, _ = validate_source_worktree(args.source_worktree)
    command = build_command(source_root, args)
    if args.print_command:
        print("sourceSha=" + EXPECTED_EXPERIMENT_SHA)
        print("python=" + sys.executable + " " + platform.python_version())
        print(" ".join(command))
        return
    subprocess.run(command, cwd=source_root,
                   env=child_environment(source_root), check=True)


if __name__ == "__main__":
    main()
