#!/usr/bin/env python3
"""Configure and build with the checked-in Linux presets from native Linux or WSL."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]


def windows_to_wsl(path: Path) -> str:
    text = str(path.resolve())
    if len(text) < 3 or text[1:3] != ":\\" or not text[0].isalpha():
        raise ValueError(f"cannot map non-drive Windows path into WSL: {text}")
    parts = text[3:].replace("\\", "/")
    return str(PurePosixPath("/mnt", text[0].lower(), parts))


def cmake_commands(args: argparse.Namespace) -> list[list[str]]:
    commands: list[list[str]] = []
    if not args.no_configure:
        commands.append(["cmake", "--preset", args.configure_preset])
    build = ["cmake", "--build", "--preset", args.build_preset]
    if args.target:
        build.extend(["--target", *args.target])
    commands.append(build)
    return commands


def run(args: argparse.Namespace) -> int:
    commands = cmake_commands(args)
    cmake = shutil.which("cmake")
    if cmake:
        print(f"build_route=native root={ROOT}")
        for command in commands:
            subprocess.run([cmake, *command[1:]], cwd=ROOT, check=True)
        return 0

    if os.name == "nt":
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl:
            wsl_root = windows_to_wsl(ROOT)
            shell = " && ".join(
                [f"cd {shlex.quote(wsl_root)}", *(
                    " ".join(shlex.quote(token) for token in command)
                    for command in commands
                )]
            )
            print(f"build_route=wsl root={wsl_root}")
            subprocess.run([wsl, "-e", "bash", "-lc", shell], check=True)
            return 0

    raise RuntimeError(
        "cmake is unavailable; on Windows install CMake or enable WSL with CMake installed"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--configure-preset", default="linux-gcc-release")
    result.add_argument("--build-preset", default="linux-gcc-build")
    result.add_argument("--target", action="append", default=[])
    result.add_argument("--no-configure", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"build: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
