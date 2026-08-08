#!/usr/bin/env python3
"""Summarise Pi agent context-reads telemetry JSONL files.

Accepts one or more telemetry JSONL files and produces a comprehensive report:

  1.  Overview & operation breakdown
  2.  Top files by read calls
  3.  Top files by requested lines (content volume)
  4.  Unique vs repeated line coverage (duplication ratios)
  5.  Hot-region analysis (configurable bucket size)
  6.  Per-session duplication
  7.  Cross-agent duplication (architect vs investigator overlap)
  8.  Repeated search analysis
  9.  CODE_MAP usage tracking
  10. Human-readable report (default)
  11. Machine-readable JSON output (--json PATH)

Usage:
  python3 tools/summarize_agent_context.py [--json out.json] \\
      [--hot-file FILE] [--bucket-lines N] \\
      file1.jsonl [file2.jsonl ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


# ── load & session helpers ──────────────────────────────────────────────

def _session_from_path(filepath: str) -> str:
    """Derive a session label from the parent directory of a JSONL file."""
    return Path(filepath).parent.name


def load_records(filepaths: list[str]) -> list[dict[str, Any]]:
    """Load all valid JSON records, annotating each with its session path.

    Skips files that cannot be opened (missing, permission, directories,
    etc.) — telemetry read failures are non-fatal.
    """
    records: list[dict[str, Any]] = []
    for fp in filepaths:
        session = _session_from_path(fp)
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rec.setdefault("_session", session)
                    records.append(rec)
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
            continue
    return records


# ── classification helpers ──────────────────────────────────────────────

_READ_TOOLS = {"read"}
_SEARCH_TOOLS = {"grep", "find"}
_LIST_TOOLS = {"ls"}
_GIT_TOOLS = {"sts_git"}
_INSPECT_TOOLS = {"sts_inspect"}

def _tool_class(tool: str) -> str:
    if tool in _READ_TOOLS:  return "read"
    if tool in _SEARCH_TOOLS: return "search"
    if tool in _LIST_TOOLS: return "list"
    if tool in _GIT_TOOLS: return "git"
    if tool in _INSPECT_TOOLS: return "inspect"
    return "other"


_CODE_MAP_PATH = "docs/knowledge-base/CODE_MAP.md"
_PRODUCTION_DIRS = ("apps/", "src/")
_PRODUCTION_SCRIPTS = ("train_", "export_")

def _is_production_read(path: str) -> bool:
    return (
        path.startswith(_PRODUCTION_DIRS)
        or any(path.startswith(s) for s in _PRODUCTION_SCRIPTS)
        or path == "EXPERIMENTS.md"
    )


# ── interval helpers ────────────────────────────────────────────────────

def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge a list of [start, end) intervals, sorted by start."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[int, int]] = [sorted_ivs[0]]
    for lo, hi in sorted_ivs[1:]:
        if lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _interval_length(iv: tuple[int, int]) -> int:
    return max(0, iv[1] - iv[0])


# ── metrics collectors ──────────────────────────────────────────────────

def _collect_file_reads(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-file read stats: calls, requested_lines, intervals, sessions."""
    per: dict[str, dict] = defaultdict(lambda: {
        "reads": 0,
        "requested_lines": 0,
        "intervals": [],
        "sessions": set(),
    })
    for r in records:
        if r.get("tool") != "read":
            continue
        path = r.get("path", "")
        if not path:
            continue
        sess = r.get("_session", "")
        per[path]["reads"] += 1
        per[path]["sessions"].add(sess)
        limit = r.get("limit", 0) or 0
        if limit > 0:
            per[path]["requested_lines"] += limit
            offset = r.get("offset", 1) or 1
            # interval is [offset, offset+limit) i.e. start_line .. end_line+1
            per[path]["intervals"].append((offset, offset + limit))
    return dict(per)


def _collect_searches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return search-operation records with normalized fields."""
    searches: list[dict[str, Any]] = []
    for r in records:
        tool = r.get("tool", "")
        if tool not in _SEARCH_TOOLS | _GIT_TOOLS | _INSPECT_TOOLS:
            continue
        entry = {
            "tool": tool,
            "path": r.get("path", "") or "",
            "pattern": r.get("pattern", "") or "",
            "session": r.get("_session", ""),
            "turn": r.get("turn", 0) or 0,
        }
        # For sts_git, the "subcommand" field is stored in pattern
        if tool == "sts_git" and not entry["pattern"]:
            entry["pattern"] = r.get("subcommand", r.get("pattern", "")) or ""
        searches.append(entry)
    return searches


def _collect_session_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-session aggregates."""
    by_session: dict[str, dict] = defaultdict(lambda: {
        "total_ops": 0,
        "reads": [],
        "search_count": 0,
        "files_read": set(),
    })
    for r in records:
        sess = r.get("_session", "")
        tool = r.get("tool", "")
        by_session[sess]["total_ops"] += 1
        if tool == "read":
            path = r.get("path", "") or ""
            limit = r.get("limit", 0) or 0
            offset = r.get("offset", 1) or 1
            by_session[sess]["reads"].append({
                "path": path,
                "offset": offset,
                "limit": limit,
                "turn": r.get("turn", 0) or 0,
            })
            if path:
                by_session[sess]["files_read"].add(path)
        elif tool in _SEARCH_TOOLS:
            by_session[sess]["search_count"] += 1
    return dict(by_session)


# ── report generation ───────────────────────────────────────────────────

def _code_map_first_rate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute CODE_MAP usage stats across sessions."""
    # First, determine per-session read order
    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("tool") != "read":
            continue
        sess = r.get("_session", "")
        by_session[sess].append({
            "path": r.get("path", "") or "",
            "turn": r.get("turn", 0) or 0,
            "ts": r.get("ts", ""),
        })

    total_sessions = len(by_session)
    sessions_reading_codemap = 0
    sessions_reading_kb_index = 0
    codemap_first = 0  # reading CODE_MAP before first production read

    for _sess, reads in by_session.items():
        # sort by turn then ts
        reads.sort(key=lambda x: (x["turn"], x["ts"]))
        paths = [r["path"] for r in reads]
        saw_codemap = _CODE_MAP_PATH in paths
        saw_kb_index = "docs/knowledge-base/README.md" in paths

        if saw_codemap:
            sessions_reading_codemap += 1
        if saw_kb_index:
            sessions_reading_kb_index += 1

        # CODE_MAP-first: reading CODE_MAP before first production read
        codemap_turn = next((i for i, p in enumerate(paths) if p == _CODE_MAP_PATH), None)
        first_prod_turn = next((i for i, p in enumerate(paths) if _is_production_read(p)), None)
        if codemap_turn is not None and (first_prod_turn is None or codemap_turn < first_prod_turn):
            codemap_first += 1

    return {
        "total_sessions": total_sessions,
        "sessions_reading_codemap": sessions_reading_codemap,
        "sessions_reading_kb_index": sessions_reading_kb_index,
        "codemap_first_count": codemap_first,
        "codemap_first_rate": (codemap_first / max(total_sessions, 1)),
    }


def _file_extension(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix:
        return suffix
    # no extension — use filename if it looks like a known name
    name = Path(path).name
    if name in ("EXPERIMENTS", "CMakeLists", "AGENTS"):
        return f".{name}"
    return "(no ext)"


def summarise(
    records: list[dict[str, Any]],
    top_n: int = 10,
    hot_files: list[str] | None = None,
    bucket_lines: int = 200,
) -> str:
    """Return a comprehensive human-readable summary string."""
    lines: list[str] = []
    warnings: list[str] = []

    total = len(records)
    lines.append(f"# Context-Usage Telemetry Report")
    lines.append(f"Total telemetry records: {total}")
    lines.append("")

    # ── 1. Operation breakdown ──────────────────────────────────────
    tool_counter: Counter[str] = Counter()
    for r in records:
        tool_counter[r.get("tool", "")] += 1

    read_count   = sum(tool_counter[t] for t in _READ_TOOLS)
    search_count = sum(tool_counter[t] for t in _SEARCH_TOOLS)
    list_count   = sum(tool_counter[t] for t in _LIST_TOOLS)
    git_count    = sum(tool_counter[t] for t in _GIT_TOOLS)
    inspect_count = sum(tool_counter[t] for t in _INSPECT_TOOLS)
    other_count  = total - read_count - search_count - list_count - git_count - inspect_count

    lines.append("## Operation Breakdown")
    lines.append(f"  Read operations:      {read_count}")
    lines.append(f"  Search operations:    {search_count}")
    lines.append(f"  Directory/list ops:   {list_count}")
    lines.append(f"  Git inspection ops:   {git_count}")
    lines.append(f"  Artifact inspection:  {inspect_count}")
    lines.append(f"  Other tool ops:       {other_count}")
    lines.append("")

    # Detailed tool breakdown
    lines.append("### Tool call counts")
    for tool, count in tool_counter.most_common():
        lines.append(f"  {tool}: {count}")
    lines.append("")

    # ── 2 & 3. File read stats ─────────────────────────────────────
    file_stats = _collect_file_reads(records)

    # Sort by reads for table 2
    by_reads = sorted(file_stats.items(), key=lambda x: x[1]["reads"], reverse=True)
    if by_reads:
        lines.append(f"## Top Files by Read Calls (top {top_n})")
        for path, s in by_reads[:top_n]:
            lines.append(f"  {s['reads']:>4} reads  {path}")
        lines.append("")

    # Sort by requested lines for table 3
    by_lines = sorted(file_stats.items(), key=lambda x: x[1]["requested_lines"], reverse=True)
    if by_lines:
        lines.append(f"## Top Files by Requested Lines (top {top_n})")
        lines.append(f"  {'File':<40s} {'Reads':>6s}  {'Requested':>10s}  {'Mean/read':>9s}  {'Median':>7s}  {'Max/read':>8s}")
        lines.append("  " + "-" * 90)
        for path, s in by_lines[:top_n]:
            reads = s["reads"]
            rl = s["requested_lines"]
            intervals = s["intervals"]
            limits = sorted([_interval_length(iv) for iv in intervals])
            mean_r = (rl / reads) if reads > 0 else 0
            med_r = limits[len(limits)//2] if limits else 0
            max_r = max(limits) if limits else 0
            disp = path[:40]
            lines.append(
                f"  {disp:<40s} {reads:>6d}  {rl:>10,d}  {mean_r:>9.1f}  {med_r:>7.0f}  {max_r:>8d}"
            )
        lines.append("")

    # Read-extension breakdown (reads only)
    ext_counter: Counter[str] = Counter()
    for r in records:
        if r.get("tool") == "read":
            p = r.get("path", "")
            ext_counter[_file_extension(p) if p else "(no ext)"] += 1

    ext_total = sum(ext_counter.values())
    if ext_total > 0:
        lines.append("### File type counts for reads")
        for ext, count in ext_counter.most_common(top_n):
            lines.append(f"  {ext}: {count}")
        # Invariant check
        assert ext_total == read_count, (
            f"Extension sum {ext_total} != read operation count {read_count}"
        )
        lines.append("")

    # Unknown-range reads
    no_range = sum(1 for r in records
                   if r.get("tool") == "read" and r.get("path") and not r.get("limit"))
    if no_range > 0:
        lines.append(f"unknown_range_reads: {no_range}")
        warnings.append(f"{no_range} reads lacked offset/limit and were excluded "
                        f"from unique-line analysis.")
        lines.append("")

    # ── 4. Unique vs repeated line coverage ─────────────────────────
    lines.append("## Duplication Ratios (unique vs repeated line coverage)")
    lines.append(f"  {'File':<40s} {'Reads':>6s}  {'Requested':>10s}  {'Unique':>8s}  {'Repeated':>10s}  Dup%")
    lines.append("  " + "-" * 95)
    dup_stats: dict[str, dict[str, Any]] = {}
    for path, s in by_lines[:top_n]:
        intervals = s["intervals"]
        total_req = s["requested_lines"]
        if not intervals:
            dup_stats[path] = {"duplication": None, "unique": 0, "repeated": 0}
            continue
        merged = _merge_intervals(intervals)
        unique = sum(_interval_length(iv) for iv in merged)
        repeated = total_req - unique
        dup_ratio = (repeated / total_req * 100) if total_req > 0 else 0
        dup_stats[path] = {"duplication": dup_ratio, "unique": unique, "repeated": repeated}

    for path, s in by_lines[:top_n]:
        ds = dup_stats.get(path, {})
        unique = ds.get("unique", 0)
        repeated = ds.get("repeated", 0)
        dup_ratio = ds.get("duplication")
        dup_str = f"{dup_ratio:>6.1f}%" if dup_ratio is not None else "  n/a"
        lines.append(
            f"  {path[:40]:<40s} {s['reads']:>6d}  {s['requested_lines']:>10,d}  "
            f"{unique:>8,d}  {repeated:>10,d}  {dup_str}"
        )
    lines.append("")

    if no_range > 0:
        lines.append(f"  Note: {no_range} reads without range data excluded from duplication analysis.")
        lines.append("")

    # ── 5. Hot-region analysis ──────────────────────────────────────
    if hot_files is None:
        # default to top 3 files by requested lines
        hot_files = [p for p, _s in by_lines[:3]]

    if hot_files:
        lines.append(f"## Hot-Region Analysis (bucket size: {bucket_lines} lines)")
        for fpath in hot_files:
            fs = file_stats.get(fpath, {})
            intervals = fs.get("intervals", [])
            if not intervals:
                lines.append(f"\n### {fpath}")
                lines.append("  (no range data available)")
                continue

            # bucket boundaries
            bucketed: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for lo, hi in intervals:
                # which buckets does this interval touch?
                start_bucket = (lo - 1) // bucket_lines
                end_bucket = (hi - 1) // bucket_lines
                for b in range(start_bucket, end_bucket + 1):
                    b_start = b * bucket_lines + 1
                    b_end = b_start + bucket_lines
                    overlap_start = max(lo, b_start)
                    overlap_end = min(hi, b_end)
                    overlap = max(0, overlap_end - overlap_start)
                    if overlap > 0:
                        bucketed[b].append((overlap_start, overlap_end))

            # aggregate per bucket
            bucket_counts: list[tuple[int, int, int]] = []  # (bucket_idx, reads, lines)
            for b_idx, ivs in bucketed.items():
                # merge intervals within this bucket for unique line count
                merged = _merge_intervals(ivs)
                bucket_lines_total = sum(_interval_length(iv) for iv in merged)
                bucket_counts.append((b_idx, len(ivs), bucket_lines_total))

            bucket_counts.sort(key=lambda x: -x[1])  # sort by reads touching

            lines.append(f"\n### {fpath}")
            if not bucket_counts:
                lines.append("  (no reads fell into any bucket)")
                continue
            lines.append(
                f"  {'Lines':>14s}  {'Reads touching':>15s}  {'Requested lines':>16s}"
            )
            lines.append("  " + "-" * 50)
            for b_idx, nreads, blines in bucket_counts[:top_n]:
                b_start = b_idx * bucket_lines + 1
                b_end = min(b_start + bucket_lines - 1, b_start + bucket_lines)
                lines.append(
                    f"  {b_start:>6d}-{b_end:<7d}  {nreads:>15d}  {blines:>16,d}"
                )
        lines.append("")

    # ── 6. Per-session duplication ──────────────────────────────────
    session_data = _collect_session_stats(records)
    # Build per-session duplication stats
    sess_dup: list[dict[str, Any]] = []
    for sess, sdata in session_data.items():
        total_reads = len(sdata["reads"])
        total_req = 0
        intervals: list[tuple[int, int]] = []
        for rd in sdata["reads"]:
            limit = rd["limit"]
            if limit > 0:
                total_req += limit
                offset = rd["offset"]
                intervals.append((offset, offset + limit))
        merged = _merge_intervals(intervals)
        unique = sum(_interval_length(iv) for iv in merged)
        repeated = total_req - unique
        dup_ratio = (repeated / total_req * 100) if total_req > 0 else 0
        sess_dup.append({
            "session": sess,
            "reads": total_reads,
            "requested_lines": total_req,
            "unique_lines": unique,
            "repeated_lines": repeated,
            "duplication": dup_ratio,
            "search_count": sdata["search_count"],
            "total_ops": sdata["total_ops"],
        })

    # Threshold: at least 10 reads OR at least 500 requested lines
    threshold = 10
    line_threshold = 500
    qualified = [s for s in sess_dup
                 if s["reads"] >= threshold or s["requested_lines"] >= line_threshold]
    qualified.sort(key=lambda x: -x["duplication"])

    lines.append("## Per-Session Duplication")
    lines.append(f"  (sessions with <{threshold} reads AND <{line_threshold} requested lines excluded)")
    lines.append(f"  Total sessions: {len(session_data)}, qualified: {len(qualified)}")
    lines.append("")
    if qualified:
        lines.append(f"  {'Session':<30s} {'Reads':>6s}  {'ReqLines':>10s}  {'Unique':>8s}  {'Dup%':>7s}")
        lines.append("  " + "-" * 70)
        for s in qualified[:top_n]:
            lines.append(
                f"  {s['session'][:30]:<30s} {s['reads']:>6d}  {s['requested_lines']:>10,d}  "
                f"{s['unique_lines']:>8,d}  {s['duplication']:>6.1f}%"
            )
    lines.append("")

    # ── 7. Cross-agent duplication ─────────────────────────────────
    lines.append("## Cross-Agent Duplication")
    # Check if any records have agent/role metadata
    agent_records = sum(1 for r in records if r.get("agent"))
    if agent_records == 0:
        lines.append("  Parent/subagent relationship unavailable for all historical sessions.")
        lines.append("  No agent/role metadata present in existing telemetry records.")
        lines.append("  New sessions (2026-08-09+) will include `agent` and `parent_session` fields.")
        lines.append("  Re-run after collecting new telemetry to populate this section.")
        warnings.append(
            "All historical records lack agent/parent_session metadata; "
            "cross-agent duplication analysis unavailable."
        )
    else:
        lines.append(f"  (agent metadata present in {agent_records} records)")
        lines.append("  Cross-agent analysis will be populated after re-collection with new telemetry.")
    lines.append("")

    # ── 8. Repeated search analysis ─────────────────────────────────
    searches = _collect_searches(records)

    # Count search patterns
    search_key_counter: Counter[tuple[str, str, str]] = Counter()
    for s in searches:
        key = (s["tool"], s["path"], s["pattern"])
        search_key_counter[key] += 1

    lines.append("## Repeated Searches")
    lines.append(f"  Total search operations: {len(searches)}")
    lines.append("")
    if search_key_counter:
        lines.append(f"### Most Repeated Searches (top {top_n})")
        lines.append(f"  {'Count':>5s}  {'Tool':<12s}  {'Path':<30s}  Pattern")
        lines.append("  " + "-" * 80)
        for (tool, path, pattern), count in search_key_counter.most_common(top_n):
            lines.append(f"  {count:>5d}  {tool:<12s}  {path[:30]:<30s}  {pattern}")
        lines.append("")

    # Same-session duplicate searches
    sess_patt_counter: Counter[tuple[str, str, str, str]] = Counter()
    for s in searches:
        key = (s["session"], s["tool"], s["path"], s["pattern"])
        sess_patt_counter[key] += 1
    same_sess_dups = sum(1 for _k, c in sess_patt_counter.items() if c > 1)
    cross_sess = sum(1 for _k, c in search_key_counter.items() if c > 1)
    lines.append(f"  Same-session duplicate searches: {same_sess_dups}")
    lines.append(f"  Cross-session repeated searches (unique keys): {cross_sess}")
    lines.append("")

    # ── 9. CODE_MAP usage ──────────────────────────────────────────
    cm = _code_map_first_rate(records)
    lines.append("## CODE_MAP Usage")
    lines.append(f"  Sessions reading CODE_MAP.md: {cm['sessions_reading_codemap']} / {cm['total_sessions']}")
    lines.append(f"  Sessions reading KB index:     {cm['sessions_reading_kb_index']} / {cm['total_sessions']}")
    lines.append(f"  CODE_MAP-first sessions:       {cm['codemap_first_count']} / {cm['total_sessions']} "
                 f"({cm['codemap_first_rate']:.1%})")
    lines.append("")

    # ── 10. Highest-cost sessions ───────────────────────────────────
    sess_dup.sort(key=lambda x: -x["requested_lines"])
    lines.append("## Highest-Cost Sessions (by requested lines)")
    lines.append(f"  {'Session':<30s} {'Ops':>5s}  {'Reads':>6s}  {'ReqLines':>10s}  {'Searches':>8s}")
    lines.append("  " + "-" * 65)
    for s in sess_dup[:top_n]:
        lines.append(
            f"  {s['session'][:30]:<30s} {s['total_ops']:>5d}  {s['reads']:>6d}  "
            f"{s['requested_lines']:>10,d}  {s['search_count']:>8d}"
        )
    lines.append("")

    # ── DQ warnings ─────────────────────────────────────────────────
    if warnings:
        lines.append("## Data-Quality Warnings")
        for w in warnings:
            lines.append(f"  {w}")
        lines.append("")

    return "\n".join(lines)


def summarise_json(
    records: list[dict[str, Any]],
    top_n: int = 10,
    hot_files: list[str] | None = None,
    bucket_lines: int = 200,
) -> dict[str, Any]:
    """Return the same metrics as a JSON-serializable dict."""
    total = len(records)

    tool_counter: Counter[str] = Counter()
    for r in records:
        tool_counter[r.get("tool", "")] += 1

    read_count   = sum(tool_counter[t] for t in _READ_TOOLS)
    search_count = sum(tool_counter[t] for t in _SEARCH_TOOLS)
    list_count   = sum(tool_counter[t] for t in _LIST_TOOLS)
    git_count    = sum(tool_counter[t] for t in _GIT_TOOLS)
    inspect_count = sum(tool_counter[t] for t in _INSPECT_TOOLS)
    other_count  = total - read_count - search_count - list_count - git_count - inspect_count

    file_stats = _collect_file_reads(records)
    searches = _collect_searches(records)
    session_data = _collect_session_stats(records)
    cm = _code_map_first_rate(records)

    # Duplication
    dup_stats: dict[str, dict[str, Any]] = {}
    for path, s in file_stats.items():
        intervals = s["intervals"]
        total_req = s["requested_lines"]
        if intervals:
            merged = _merge_intervals(intervals)
            unique = sum(_interval_length(iv) for iv in merged)
            repeated = total_req - unique
            dup_stats[path] = {
                "duplication_ratio": (repeated / total_req) if total_req > 0 else 0,
                "unique_lines": unique,
                "repeated_lines": repeated,
            }
        else:
            dup_stats[path] = {"duplication_ratio": None, "unique_lines": 0, "repeated_lines": 0}

    # Per-session
    sess_dup: list[dict[str, Any]] = []
    for sess, sdata in session_data.items():
        total_reads = len(sdata["reads"])
        total_req = 0
        intervals: list[tuple[int, int]] = []
        for rd in sdata["reads"]:
            if rd["limit"] > 0:
                total_req += rd["limit"]
                intervals.append((rd["offset"], rd["offset"] + rd["limit"]))
        merged = _merge_intervals(intervals)
        unique = sum(_interval_length(iv) for iv in merged)
        sess_dup.append({
            "session": sess,
            "total_ops": sdata["total_ops"],
            "reads": total_reads,
            "requested_lines": total_req,
            "unique_lines": unique,
            "repeated_lines": total_req - unique,
            "duplication_ratio": ((total_req - unique) / total_req) if total_req > 0 else 0,
            "search_count": sdata["search_count"],
            "files_read": sorted(sdata["files_read"]),
        })

    # Search repeats
    search_key_counter: Counter[tuple[str, str, str]] = Counter()
    sess_patt_counter: Counter[tuple[str, str, str, str]] = Counter()
    for s in searches:
        search_key_counter[(s["tool"], s["path"], s["pattern"])] += 1
        sess_patt_counter[(s["session"], s["tool"], s["path"], s["pattern"])] += 1

    # Hot regions
    if hot_files is None:
        by_lines = sorted(file_stats.items(), key=lambda x: x[1]["requested_lines"], reverse=True)
        hot_files = [p for p, _s in by_lines[:3]]

    hot_result: dict[str, list[dict]] = {}
    for fpath in hot_files:
        fs = file_stats.get(fpath)
        if not fs:
            hot_result[fpath] = []
            continue
        intervals = fs["intervals"]
        bucketed: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for lo, hi in intervals:
            start_bucket = (lo - 1) // bucket_lines
            end_bucket = (hi - 1) // bucket_lines
            for b in range(start_bucket, end_bucket + 1):
                b_start = b * bucket_lines + 1
                b_end = b_start + bucket_lines
                overlap_start = max(lo, b_start)
                overlap_end = min(hi, b_end)
                overlap = max(0, overlap_end - overlap_start)
                if overlap > 0:
                    bucketed[b].append((overlap_start, overlap_end))
        regions: list[dict] = []
        for b_idx, ivs in bucketed.items():
            merged_ivs = _merge_intervals(ivs)
            b_start = b_idx * bucket_lines + 1
            b_end = b_start + bucket_lines - 1
            regions.append({
                "line_range": f"{b_start}-{b_end}",
                "start": b_start,
                "end": b_end,
                "reads_touching": len(ivs),
                "requested_lines_in_bucket": sum(_interval_length(iv) for iv in merged_ivs),
            })
        regions.sort(key=lambda x: -x["reads_touching"])
        hot_result[fpath] = regions[:top_n]

    # Extension counts (reads only)
    ext_counter: Counter[str] = Counter()
    for r in records:
        if r.get("tool") == "read":
            p = r.get("path", "")
            ext_counter[_file_extension(p) if p else "(no ext)"] += 1

    # Warnings
    warnings: list[str] = []
    no_range = sum(1 for r in records
                   if r.get("tool") == "read" and r.get("path") and not r.get("limit"))
    if no_range:
        warnings.append(f"{no_range} reads lacked offset/limit and were excluded "
                        f"from unique-line analysis.")
    agent_records = sum(1 for r in records if r.get("agent"))
    if agent_records == 0:
        warnings.append("All historical records lack agent/parent_session metadata; "
                        "cross-agent duplication analysis unavailable.")
    parent_sessions = sum(1 for r in records if r.get("parent_session"))
    if parent_sessions > 0:
        warnings.append(f"{parent_sessions} records have parent_session metadata.")
    else:
        warnings.append("No records have parent_session metadata; "
                        "subagent parent relationship unavailable.")

    return {
        "total_records": total,
        "operation_breakdown": {
            "read_operations": read_count,
            "search_operations": search_count,
            "list_operations": list_count,
            "git_inspection_operations": git_count,
            "artifact_inspection_operations": inspect_count,
            "other_operations": other_count,
            "by_tool": dict(tool_counter),
        },
        "file_reads": {
            "extension_counts_reads_only": dict(ext_counter),
            "top_by_reads": [
                {"path": p, "reads": s["reads"], "requested_lines": s["requested_lines"]}
                for p, s in sorted(file_stats.items(), key=lambda x: -x[1]["reads"])[:top_n]
            ],
            "top_by_requested_lines": [
                {
                    "path": p,
                    "reads": s["reads"],
                    "requested_lines": s["requested_lines"],
                    **dup_stats.get(p, {}),
                }
                for p, s in sorted(file_stats.items(), key=lambda x: -x[1]["requested_lines"])[:top_n]
            ],
        },
        "duplication": {
            "top_by_ratio": [
                {"path": p, **ds}
                for p, ds in sorted(
                    dup_stats.items(),
                    key=lambda x: x[1].get("duplication_ratio") or 0,
                    reverse=True,
                )[:top_n]
            ],
        },
        "hot_regions": hot_result,
        "per_session": sess_dup,
        "cross_agent": {
            "available": agent_records > 0,
            "note": "Cross-agent analysis unavailable for historical data"
                    if agent_records == 0 else "Cross-agent analysis pending",
        },
        "repeated_searches": {
            "most_repeated": [
                {"tool": tool, "path": path, "pattern": pattern, "count": count}
                for (tool, path, pattern), count in search_key_counter.most_common(top_n)
            ],
            "same_session_duplicate_count": sum(1 for _k, c in sess_patt_counter.items() if c > 1),
            "cross_session_repeated_keys": sum(1 for _k, c in search_key_counter.items() if c > 1),
        },
        "code_map_usage": cm,
        "unknown_range_reads": no_range,
        "warnings": warnings,
    }


# ── CLI ────────────────────────────────────────────────────────────────

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
    parser.add_argument(
        "--json", type=str, default=None, dest="json_path",
        help="Write machine-readable JSON summary to PATH."
    )
    parser.add_argument(
        "--hot-file", type=str, action="append", default=None, dest="hot_files",
        help="Add a file to hot-region analysis (repeatable). Default: top 3 by lines."
    )
    parser.add_argument(
        "--bucket-lines", type=int, default=200,
        help="Hot-region bucket size in lines (default: 200)."
    )
    args = parser.parse_args()

    records = load_records(args.files)
    if not records:
        print("No valid records found.", file=sys.stderr)
        sys.exit(1)

    # Write JSON if requested
    if args.json_path:
        result = summarise_json(records, top_n=args.top,
                                hot_files=args.hot_files,
                                bucket_lines=args.bucket_lines)
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"JSON summary written to {args.json_path}", file=sys.stderr)

    # Always print human-readable report
    print(summarise(records, top_n=args.top,
                    hot_files=args.hot_files,
                    bucket_lines=args.bucket_lines))


if __name__ == "__main__":
    main()
