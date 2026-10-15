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
CCACHE_FALLBACKS = {
    ("linux-gcc-release-ccache", "linux-gcc-release-ccache-build"): (
        "linux-gcc-release", "linux-gcc-build"
    ),
    ("linux-gcc-debug-ccache", "linux-gcc-debug-ccache-build"): (
        "linux-gcc-debug", "linux-gcc-debug-build"
    ),
}


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


def ccache_usable() -> tuple[bool, str]:
    if shutil.which("ccache") is None:
        return False, "ccache executable is unavailable"
    # The checked-in presets derive CCACHE_DIR from HOME, so inspect that exact
    # location rather than a process-level CCACHE_DIR that the preset replaces.
    cache_dir = Path.home() / ".cache/sts_ai/ccache"
    probe = cache_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir() or not os.access(probe, os.W_OK):
        return False, f"cache directory is read-only: {cache_dir}"
    return True, f"cache directory is writable: {cache_dir}"


def wsl_ccache_usable(wsl: str) -> tuple[bool, str]:
    script = """
cache_dir="$HOME/.cache/sts_ai/ccache"
if ! command -v ccache >/dev/null 2>&1; then
    echo "ccache executable is unavailable in WSL"
    exit 1
fi
probe="$cache_dir"
while [ ! -e "$probe" ] && [ "$probe" != / ]; do
    probe="${probe%/*}"
    [ -n "$probe" ] || probe=/
done
if [ ! -d "$probe" ] || [ ! -w "$probe" ]; then
    echo "cache directory is read-only in WSL: $cache_dir"
    exit 1
fi
echo "cache directory is writable in WSL: $cache_dir"
""".strip()
    result = subprocess.run(
        [wsl, "-e", "bash", "-lc", script],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    reason = result.stdout.strip() or f"WSL ccache probe exited {result.returncode}"
    return result.returncode == 0, reason


def apply_ccache_fallback(
    args: argparse.Namespace, probe=None
) -> None:
    requested = (args.configure_preset, args.build_preset)
    fallback = CCACHE_FALLBACKS.get(requested)
    if fallback is None:
        return
    usable, reason = (probe or ccache_usable)()
    if usable:
        return
    args.configure_preset, args.build_preset = fallback
    configure_forced = args.no_configure
    args.no_configure = False
    print(
        f"ccache_fallback={args.configure_preset} "
        f"build_preset={args.build_preset} "
        f"configure_forced={'true' if configure_forced else 'false'} reason={reason}"
    )


def run(args: argparse.Namespace) -> int:
    cmake = shutil.which("cmake")
    if cmake:
        apply_ccache_fallback(args)
        commands = cmake_commands(args)
        print(f"build_route=native root={ROOT}")
        for command in commands:
            subprocess.run([cmake, *command[1:]], cwd=ROOT, check=True)
        return 0

    if os.name == "nt":
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl:
            apply_ccache_fallback(args, lambda: wsl_ccache_usable(wsl))
            commands = cmake_commands(args)
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
