#!/usr/bin/env python3
"""Read-only, deterministic repository-health checks."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_BASELINE = "3b314c3d85f02315de7666d8c6542b568190c6e6"
DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
SESSION_DECISION = re.compile(r"^docs/knowledge-base/decision-log/\d{4}-\d{2}-\d{2}-.+\.md$")
MARKDOWN_LINK = re.compile(r"(?<![\w`])!?(?:\[[^]\n]*\])\(([^)\n]+)\)")
GENERATED = re.compile(
    r"^(?:build|dist|out|generated|cmake-build[^/]*)/|"
    r"(?:^|/)(?:CMakeCache\.txt|compile_commands\.json)$|"
    r"\.(?:o|obj|a|so|dylib|dll|exe|pyc)$"
)


def git_files(repo: Path, revision: str | None = None) -> list[str]:
    command = ["git", "-C", str(repo), "ls-files"] if not revision else ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", revision]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return sorted(line for line in result.stdout.splitlines() if line)


def classify_path(path: str) -> set[str]:
    """Return policy categories for a tracked path."""
    categories: set[str] = set()
    if GENERATED.search(path):
        categories.add("generated_or_build")
    if path.startswith("docs/archive/"):
        categories.add("docs_archive")
    if SESSION_DECISION.match(path):
        categories.add("session_decision_log")
    if "/" not in path and path.endswith((".py", ".sh")):
        categories.add("root_script")
    return categories


def _content(repo: Path, path: str, revision: str | None = None) -> bytes:
    if revision:
        result = subprocess.run(["git", "-C", str(repo), "show", f"{revision}:{path}"], check=False, capture_output=True)
        return result.stdout if result.returncode == 0 else b""
    try:
        return (repo / path).read_bytes()
    except OSError:
        return b""


def _bytes(repo: Path, paths: Iterable[str], revision: str | None = None) -> int:
    return sum(len(_content(repo, path, revision)) for path in paths)


def _lines(repo: Path, path: str, revision: str | None = None) -> int:
    try:
        return len(_content(repo, path, revision).decode("utf-8").splitlines())
    except UnicodeDecodeError:
        return 0


def broken_documentation_links(repo: Path, files: Iterable[str], revision: str | None = None) -> list[dict[str, str]]:
    """Find missing local links in current documentation, in stable order."""
    tracked = set(files)
    broken: list[dict[str, str]] = []
    for source in sorted(path for path in tracked if Path(path).suffix.lower() in DOC_EXTENSIONS):
        try:
            text = _content(repo, source, revision).decode("utf-8")
        except UnicodeDecodeError:
            continue
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().split()[0].strip("<>")
            if target in {"s", "z[mm]"} or target.startswith(("%", "#")):
                continue
            if not target or target.startswith(("#", "/", "http:", "https:", "mailto:", "ftp:")):
                continue
            target_path = target.split("#", 1)[0].split("?", 1)[0]
            if not target_path:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target_path))
            if resolved not in tracked and (revision or not (repo / resolved).exists()):
                broken.append({"source": source, "target": target})
    return broken


def metrics(repo: Path, files: list[str], revision: str | None = None) -> dict[str, object]:
    active_md = [p for p in files if p.endswith((".md", ".markdown")) and not p.startswith("docs/archive/")]
    archive = [p for p in files if p.startswith("docs/archive/")]
    decisions = [p for p in files if SESSION_DECISION.match(p)]
    one_combat = "apps/one_combat.cpp"
    return {
        "tracked_files": len(files),
        "tracked_bytes": _bytes(repo, files, revision),
        "active_markdown": {"files": len(active_md), "bytes": _bytes(repo, active_md, revision)},
        "docs_archive": {"files": len(archive), "bytes": _bytes(repo, archive, revision)},
        "session_decision_log": {"files": len(decisions), "bytes": _bytes(repo, decisions, revision)},
        "one_combat_cpp": {"bytes": _bytes(repo, [one_combat], revision), "lines": _lines(repo, one_combat, revision)},
        "root_scripts": sorted(p for p in files if "root_script" in classify_path(p)),
    }


def report(repo: Path, baseline: str) -> dict[str, object]:
    current_files = git_files(repo)
    baseline_files = git_files(repo, baseline)
    added = sorted(set(current_files) - set(baseline_files))
    categories = {category: [p for p in added if category in classify_path(p)] for category in (
        "generated_or_build", "docs_archive", "session_decision_log", "root_script")}
    current_broken = broken_documentation_links(repo, current_files)
    baseline_broken = broken_documentation_links(repo, baseline_files, baseline)
    current_metrics = metrics(repo, current_files)
    baseline_metrics = metrics(repo, baseline_files, baseline)
    warnings = []
    if current_metrics["active_markdown"]["bytes"] > baseline_metrics["active_markdown"]["bytes"]:
        warnings.append("active Markdown growth")
    if current_metrics["one_combat_cpp"]["bytes"] > baseline_metrics["one_combat_cpp"]["bytes"]:
        warnings.append("one_combat.cpp growth")
    if categories["root_script"]:
        warnings.append("new root-level one-off scripts")
    hard_failures = {key: value for key, value in categories.items() if key != "root_script" and value}
    if current_broken:
        hard_failures["broken_current_documentation_references"] = current_broken
    return {
        "baseline": baseline,
        "current": {"head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip(), "metrics": current_metrics},
        "baseline_metrics": baseline_metrics,
        "added_tracked_paths": added,
        "hard_failures": hard_failures,
        "warnings": sorted(set(warnings)),
        "documentation": {"current_broken": current_broken, "baseline_broken": baseline_broken},
        "status": "fail" if hard_failures else "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--json", action="store_true", help="emit the complete report as JSON")
    args = parser.parse_args()
    result = report(args.repo.resolve(), args.baseline)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"repo-health: {result['status']} (baseline {args.baseline[:12]})")
        for name, paths in result["hard_failures"].items():
            print(f"  HARD {name}: {len(paths)}")
        for warning in result["warnings"]:
            print(f"  WARN {warning}")
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
