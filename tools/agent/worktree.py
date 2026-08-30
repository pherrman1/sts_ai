#!/usr/bin/env python3
"""Create, validate, repair, and remove linked worktrees with pinned submodules."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUBMODULES = ("json", "pybind11")
STATUS_RE = re.compile(r"^([ +\-U])([0-9a-f]{40})\s+([^\s]+)(?:\s+.*)?$")


class WorktreeError(RuntimeError):
    """An actionable worktree lifecycle failure."""


def git(cwd: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.rstrip() if capture else ""


def resolved(path: Path) -> Path:
    return Path(os.path.normcase(os.path.realpath(path)))


def require_checkout(path: Path) -> Path:
    candidate = path.resolve()
    try:
        top = Path(git(candidate, "rev-parse", "--show-toplevel", capture=True))
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WorktreeError(f"not a Git checkout: {candidate}") from exc
    if resolved(top) != resolved(candidate):
        raise WorktreeError(f"path is not a checkout root: {candidate} (root is {top})")
    return candidate


def pinned_revisions(worktree: Path) -> dict[str, str]:
    revisions: dict[str, str] = {}
    for name in SUBMODULES:
        line = git(worktree, "ls-tree", "HEAD", "--", name, capture=True)
        fields = line.split()
        if len(fields) < 4 or fields[0] != "160000" or fields[1] != "commit":
            raise WorktreeError(f"{name} is not a gitlink at {worktree}/HEAD")
        revisions[name] = fields[2]
    return revisions


def status_records(worktree: Path) -> dict[str, tuple[str, str]]:
    output = git(worktree, "submodule", "status", "--", *SUBMODULES, capture=True)
    records: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        match = STATUS_RE.match(line)
        if not match:
            raise WorktreeError(f"unrecognized submodule status: {line!r}")
        prefix, revision, name = match.groups()
        records[name] = (prefix, revision)
    return records


def check(worktree: Path) -> None:
    worktree = require_checkout(worktree)
    pinned = pinned_revisions(worktree)
    records = status_records(worktree)
    failures: list[str] = []
    for name, expected in pinned.items():
        record = records.get(name)
        if record is None:
            failures.append(f"{name}: missing status")
            continue
        prefix, actual = record
        if prefix != " ":
            meaning = {"-": "uninitialized", "+": "wrong revision", "U": "conflicted"}.get(
                prefix, "invalid"
            )
            failures.append(f"{name}: {meaning} ({actual})")
            continue
        if actual != expected:
            failures.append(f"{name}: {actual} != pinned {expected}")
            continue
        submodule_root = Path(
            git(worktree / name, "rev-parse", "--show-toplevel", capture=True)
        )
        if resolved(submodule_root) != resolved(worktree / name):
            failures.append(f"{name}: Git metadata resolves to {submodule_root}")
    if failures:
        raise WorktreeError("submodule check failed: " + "; ".join(failures))
    print(
        "worktree_submodules_ok "
        + " ".join(f"{name}={revision[:12]}" for name, revision in pinned.items())
    )


def initialize(worktree: Path) -> None:
    worktree = require_checkout(worktree)
    git(worktree, "submodule", "sync", "--recursive")
    for name in SUBMODULES:
        git(worktree, "submodule", "update", "--init", "--recursive", "--", name)
    check(worktree)


def registered_worktrees() -> list[Path]:
    output = git(ROOT, "worktree", "list", "--porcelain", capture=True)
    return [Path(line[9:]) for line in output.splitlines() if line.startswith("worktree ")]


def create(args: argparse.Namespace) -> None:
    target = args.path.resolve()
    if target.exists():
        raise WorktreeError(f"target already exists: {target}")
    command = ["worktree", "add"]
    if args.detach:
        command.append("--detach")
    elif args.branch:
        command.extend(["-b", args.branch])
    command.extend([str(target), args.start_point])
    git(ROOT, *command)
    try:
        initialize(target)
    except Exception as exc:
        raise WorktreeError(
            f"worktree was created but dependency setup failed: {target}; "
            f"fix the cause, then run: {Path(sys.executable).name} "
            f"tools/agent/worktree.py repair {target}"
        ) from exc
    print(f"worktree_created path={target}")


def repair(path: Path) -> None:
    initialize(path)
    print(f"worktree_repaired path={path.resolve()}")


def remove(path: Path) -> None:
    target = require_checkout(path)
    registered = {resolved(item) for item in registered_worktrees()}
    if resolved(target) == resolved(ROOT):
        raise WorktreeError("refusing to remove the primary checkout")
    if resolved(target) not in registered:
        raise WorktreeError(f"not a registered linked worktree: {target}")
    dirty = git(
        target,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--ignore-submodules=none",
        capture=True,
    )
    if dirty:
        raise WorktreeError(f"refusing to remove dirty worktree {target}:\n{dirty}")
    git(target, "submodule", "deinit", "-f", "--all")
    git(ROOT, "worktree", "remove", str(target))
    print(f"worktree_removed path={target}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="create and fully initialize a worktree")
    create_parser.add_argument("path", type=Path)
    branch = create_parser.add_mutually_exclusive_group(required=True)
    branch.add_argument("--branch")
    branch.add_argument("--detach", action="store_true")
    create_parser.add_argument("--start-point", default="HEAD")

    for command in ("check", "repair", "remove"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("path", nargs="?", type=Path, default=ROOT)
    return result


def run(args: argparse.Namespace) -> None:
    if args.command == "create":
        create(args)
    elif args.command == "check":
        check(args.path)
    elif args.command == "repair":
        repair(args.path)
    elif args.command == "remove":
        remove(args.path)
    else:  # pragma: no cover - argparse enforces the command set
        raise WorktreeError(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        run(parser().parse_args(argv))
        return 0
    except (OSError, subprocess.CalledProcessError, WorktreeError) as exc:
        print(f"worktree: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
