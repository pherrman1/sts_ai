#!/usr/bin/env python3
"""Summarise context-reads telemetry JSONL files.

Accepts one or more telemetry JSONL files and reports:
  - reads by file
  - most frequently read files
  - requested read lines by file (when available)
  - most frequently searched patterns/symbols
  - searches by directory
  - counts by agent role
  - top hotspots

Usage:
  python3 tools/summarize_agent_context.py [--top N] file1.jsonl [file2.jsonl ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_records(filepaths: list[str]) -> list[dict[str, Any]]:
    """Load and return all valid JSON records from the given files.

    Skips files that cannot be opened (missing, permission denied,
    directories, etc.) — telemetry read failures are non-fatal.
    """
    records: list[dict[str, Any]] = []
    for fp in filepaths:
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
            continue
    return records


def summarise(records: list[dict[str, Any]], top_n: int = 10) -> str:
    """Return a formatted summary string."""
    lines: list[str] = []

    # --- Counts by tool ---
    tool_counter: Counter[str] = Counter()
    read_counter: Counter[str] = Counter()  # path -> read count
    read_lines: dict[str, int] = {}  # path -> sum of (limit or estimated lines)
    search_dir: Counter[str] = Counter()  # directory -> search count
    pattern_counter: Counter[str] = Counter()
    role_counter: Counter[str] = Counter()

    for r in records:
        tool = r.get("tool", "")
        tool_counter[tool] += 1

        role = r.get("agent", "") or "(no role)"
        role_counter[role] += 1

        p = r.get("path", "")
        pattern = r.get("pattern", "")

        if tool == "read" and p:
            read_counter[p] += 1
            offset = r.get("offset", 1) or 1
            limit = r.get("limit", 0) or 0
            if limit > 0:
                read_lines[p] = read_lines.get(p, 0) + limit
            else:
                # unknown length, estimate 50 lines (conservative)
                read_lines[p] = read_lines.get(p, 0) + 50

        if tool in ("grep", "find") and p:
            # extract directory
            parent = str(Path(p).parent) if not Path(p).is_dir() else p
            search_dir[parent] += 1

        if tool == "sts_git" and pattern:
            search_dir[f"git:{pattern}"] += 1

        if tool == "sts_inspect" and pattern:
            pattern_counter[pattern] += 1

        if pattern and tool in ("grep", "find"):
            pattern_counter[pattern] += 1

    total = len(records)
    lines.append(f"Total tool events: {total}")
    lines.append("")

    # Tool breakdown
    if tool_counter:
        lines.append("## Tool call counts")
        for tool, count in tool_counter.most_common():
            lines.append(f"  {tool}: {count}")
        lines.append("")

    # Top files by read count
    if read_counter:
        lines.append(f"## Most read files (top {top_n})")
        for path_, count in read_counter.most_common(top_n):
            lines.append(f"  {count:>4} reads  {path_}")
        lines.append("")

    # Top files by requested lines
    if read_lines:
        lines.append(f"## Top files by requested lines (top {top_n})")
        sorted_lines = sorted(read_lines.items(), key=lambda x: x[1], reverse=True)
        for path_, count in sorted_lines[:top_n]:
            lines.append(f"  {count:>6} lines  {path_}")
        lines.append("")

    # Most searched directories
    if search_dir:
        lines.append(f"## Most searched directories (top {top_n})")
        for d, count in search_dir.most_common(top_n):
            lines.append(f"  {count:>4}  {d}/")
        lines.append("")

    # Most frequent patterns
    if pattern_counter:
        lines.append(f"## Most searched patterns/symbols (top {top_n})")
        for pattern, count in pattern_counter.most_common(top_n):
            lines.append(f"  {count:>4}  {pattern}")
        lines.append("")

    # By role
    if role_counter:
        lines.append("## By role")
        for role, count in role_counter.most_common():
            lines.append(f"  {role}: {count}")
        lines.append("")

    # Top hotspots (files that appear across multiple tool types)
    hotspot_files: Counter[str] = Counter()
    for r in records:
        p = r.get("path", "")
        if p and r.get("tool") in ("read", "grep", "find", "edit"):
            hotspot_files[p] += 1
    if hotspot_files:
        lines.append(f"## Top hotspots (files most frequently touched by any tool, top {top_n})")
        for path_, count in hotspot_files.most_common(top_n):
            lines.append(f"  {count:>4} touches  {path_}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarise Pi agent context-reads telemetry JSONL files."
    )
    parser.add_argument(
        "files", nargs="+", help="One or more JSONL telemetry files to summarise."
    )
    parser.add_argument(
        "--top", type=int, default=10, help="Number of top entries to show (default: 10)."
    )
    args = parser.parse_args()

    records = load_records(args.files)
    if not records:
        print("No valid records found.", file=sys.stderr)
        sys.exit(1)

    print(summarise(records, top_n=args.top))


if __name__ == "__main__":
    main()
