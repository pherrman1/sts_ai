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


SESSION_DECISION = re.compile(r"^docs/knowledge-base/decision-log/\d{4}-\d{2}-\d{2}-.+\.md$")
LINK = re.compile(r"!?(?:\[[^]\n]*\])\(\s*(?:<([^>\n]+)>|([^\s)]+))")
FENCED = re.compile(r"(?ms)^\s*```.*?^\s*```\s*$")
INLINE_CODE = re.compile(r"`[^`\n]*`")
GENERATED_EXTENSION = re.compile(r"\.(?:o|obj|a|so|dylib|dll|exe|pyc)$", re.IGNORECASE)
GENERATED_NAMES = {"CMakeCache.txt", "compile_commands.json"}
GENERATED_ROOTS = ("build/", "dist/", "out/", "generated/")


def tree_inventory(repo: Path, revision: str) -> dict[str, int]:
    """Return tracked blob sizes from one NUL-delimited ls-tree pass."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "-l", "-z", revision],
        check=True,
        capture_output=True,
    )
    inventory: dict[str, int] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        header, path = record.split(b"\t", 1)
        fields = header.split()
        if len(fields) >= 4 and fields[3] != b"-":
            inventory[path.decode("utf-8")] = int(fields[3])
    return dict(sorted(inventory.items()))


def ignored_paths(repo: Path, paths: list[str]) -> set[str]:
    """Batch-check newly tracked paths against the repository's gitignore."""
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "-z", "--stdin"],
        input=b"\0".join(path.encode("utf-8") for path in paths) + b"\0",
        capture_output=True,
        check=False,
    )
    return {path.decode("utf-8") for path in result.stdout.split(b"\0") if path}


def classify_path(path: str, ignored: bool = False) -> set[str]:
    """Return policy categories for a newly tracked path."""
    categories: set[str] = set()
    if ignored or path.startswith(GENERATED_ROOTS) or path.rsplit("/", 1)[-1] in GENERATED_NAMES or GENERATED_EXTENSION.search(path):
        categories.add("generated_or_build")
    if path.startswith("docs/archive/"):
        categories.add("docs_archive")
    if SESSION_DECISION.fullmatch(path):
        categories.add("session_decision_log")
    if "/" not in path and path.endswith((".py", ".sh")):
        categories.add("root_script")
    return categories


def broken_documentation_links(repo: Path, files: list[str]) -> list[dict[str, str]]:
    """Find missing relative file or directory links in current Markdown."""
    tracked = set(files)
    broken: list[dict[str, str]] = []
    markdown = sorted(path for path in files if Path(path).suffix.lower() in {".md", ".markdown"})
    for source in markdown:
        try:
            text = (repo / source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = INLINE_CODE.sub("", FENCED.sub("", text))
        for angle_target, bare_target in LINK.findall(text):
            target = (angle_target or bare_target).strip()
            if not target or target.startswith(("#", "/")) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            target_path = target.split("#", 1)[0].split("?", 1)[0]
            if not target_path:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target_path))
            if resolved not in tracked and not (repo / resolved).exists():
                broken.append({"source": source, "target": target})
    return broken


def metrics(inventory: dict[str, int]) -> dict[str, object]:
    files = sorted(inventory)
    active_md = [p for p in files if p.endswith((".md", ".markdown")) and not p.startswith("docs/archive/")]
    archive = [p for p in files if p.startswith("docs/archive/")]
    decisions = [p for p in files if SESSION_DECISION.fullmatch(p)]
    return {
        "tracked_files": len(files),
        "tracked_bytes": sum(inventory.values()),
        "active_markdown": {"files": len(active_md), "bytes": sum(inventory[p] for p in active_md)},
        "docs_archive": {"files": len(archive), "bytes": sum(inventory[p] for p in archive)},
        "session_decision_log": {"files": len(decisions), "bytes": sum(inventory[p] for p in decisions)},
        "one_combat_cpp": {"bytes": inventory.get("apps/one_combat.cpp", 0)},
        "root_scripts": sorted(p for p in files if "root_script" in classify_path(p)),
    }


def report(repo: Path, baseline: str) -> dict[str, object]:
    current = tree_inventory(repo, "HEAD")
    base = tree_inventory(repo, baseline)
    added = sorted(set(current) - set(base))
    ignored = ignored_paths(repo, added)
    categories = {category: [p for p in added if category in classify_path(p, p in ignored)] for category in (
        "generated_or_build", "docs_archive", "session_decision_log", "root_script")}
    current_broken = broken_documentation_links(repo, sorted(current))
    current_metrics = metrics(current)
    base_metrics = metrics(base)
    warnings = []
    if current_metrics["active_markdown"]["bytes"] > base_metrics["active_markdown"]["bytes"]:
        warnings.append("active Markdown growth")
    if current_metrics["one_combat_cpp"]["bytes"] > base_metrics["one_combat_cpp"]["bytes"]:
        warnings.append("one_combat.cpp growth")
    if categories["root_script"]:
        warnings.append("new root-level one-off scripts")
    hard_failures = {key: value for key, value in categories.items() if key != "root_script" and value}
    if current_broken:
        hard_failures["broken_current_documentation_references"] = current_broken
    return {
        "baseline": baseline,
        "current": {"head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip(), "metrics": current_metrics},
        "baseline_metrics": base_metrics,
        "added_tracked_paths": added,
        "hard_failures": hard_failures,
        "warnings": sorted(set(warnings)),
        "documentation": {"current_broken": current_broken},
        "status": "fail" if hard_failures else "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", required=True, help="event base commit to compare against")
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
