#!/usr/bin/env python3
"""Build one target from a Git archive without creating another worktree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUBMODULES = ("json", "pybind11")


class BaselineBuildError(RuntimeError):
    pass


def capture(*command: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.rstrip()


def extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as bundle:
        root = destination.resolve()
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(root):
                raise BaselineBuildError(f"archive member escapes destination: {member.name}")
            if member.issym() or member.islnk():
                link_base = target.parent if member.issym() else root
                link = (link_base / member.linkname).resolve()
                if not link.is_relative_to(root):
                    raise BaselineBuildError(
                        f"archive link escapes destination: {member.name}"
                    )
        bundle.extractall(destination)


def export_source(commit: str, destination: Path) -> None:
    superproject_archive = destination.parent / "superproject.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", f"--output={superproject_archive}", commit],
        cwd=ROOT,
        check=True,
    )
    extract_archive(superproject_archive, destination)

    for name in SUBMODULES:
        record = capture("git", "ls-tree", commit, "--", name)
        fields = record.split()
        if len(fields) < 3 or fields[0] != "160000" or fields[1] != "commit":
            raise BaselineBuildError(f"{name} is not a gitlink at {commit}")
        revision = fields[2]
        module = ROOT / name
        try:
            capture("git", "cat-file", "-e", f"{revision}^{{commit}}", cwd=module)
        except subprocess.CalledProcessError as exc:
            raise BaselineBuildError(
                f"{name} lacks baseline object {revision}; repair or fetch dependencies first"
            ) from exc
        module_archive = destination.parent / f"{name}.tar"
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                f"--output={module_archive}",
                revision,
            ],
            cwd=module,
            check=True,
        )
        module_destination = destination / name
        # Superproject archives may preserve the gitlink as an empty directory.
        module_destination.mkdir(exist_ok=True)
        extract_archive(module_archive, module_destination)


def preset_binary_dir(source: Path, build_preset: str) -> Path:
    presets = json.loads((source / "CMakePresets.json").read_text(encoding="utf-8"))
    builds = {item["name"]: item for item in presets.get("buildPresets", [])}
    configures = {item["name"]: item for item in presets.get("configurePresets", [])}
    try:
        configure_name = builds[build_preset]["configurePreset"]
        value = configures[configure_name]["binaryDir"]
    except KeyError as exc:
        raise BaselineBuildError(f"unknown or incomplete build preset: {build_preset}") from exc
    return Path(value.replace("${sourceDir}", str(source)))


def run(args: argparse.Namespace) -> int:
    commit = capture("git", "rev-parse", "--verify", f"{args.ref}^{{commit}}")
    output = args.output or ROOT / "build" / "baselines" / commit[:12] / args.target
    output = output.resolve()
    if output.exists():
        raise BaselineBuildError(f"refusing to overwrite existing baseline artifact: {output}")

    with tempfile.TemporaryDirectory(prefix="sts-ai-baseline-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        export_source(commit, source)
        subprocess.run(
            ["cmake", "--preset", args.configure_preset], cwd=source, check=True
        )
        subprocess.run(
            [
                "cmake",
                "--build",
                "--preset",
                args.build_preset,
                "--target",
                args.target,
            ],
            cwd=source,
            check=True,
        )
        artifact = preset_binary_dir(source, args.build_preset) / args.target
        if not artifact.is_file():
            raise BaselineBuildError(f"built artifact not found: {artifact}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, output)

    print(
        f"baseline_built ref={args.ref} commit={commit} "
        f"target={args.target} output={output}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("ref", help="Git commit or ref to export")
    result.add_argument("--target", default="one_combat")
    result.add_argument("--configure-preset", default="linux-gcc-release")
    result.add_argument("--build-preset", default="linux-gcc-build")
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except (BaselineBuildError, OSError, subprocess.CalledProcessError) as exc:
        print(f"baseline-build: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
