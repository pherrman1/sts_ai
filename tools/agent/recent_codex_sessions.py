#!/usr/bin/env python3
"""List recent Codex sessions for a repository without emitting transcripts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


class SessionDiscoveryError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project", type=Path, required=True)
    result.add_argument("--limit", type=int, default=5)
    result.add_argument("--json", action="store_true")
    result.add_argument("--codex-home", type=Path, help=argparse.SUPPRESS)
    return result


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _project_roots(project: Path) -> list[Path]:
    resolved = project.resolve()
    roots = [resolved]
    parts = resolved.parts
    if ".worktrees" in parts:
        roots.append(Path(*parts[: parts.index(".worktrees")]))
    return roots


def _belongs_to_project(cwd: Path, roots: list[Path]) -> bool:
    resolved = cwd.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _read_metadata(path: Path, bucket: str) -> dict[str, object] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            record = json.loads(handle.readline())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if record.get("type") != "session_meta" or not isinstance(record.get("payload"), dict):
        return None
    payload = record["payload"]
    started = payload.get("timestamp") or record.get("timestamp")
    parsed = _timestamp(started)
    cwd = payload.get("cwd")
    session_id = payload.get("session_id") or payload.get("id")
    if parsed is None or not isinstance(cwd, str) or not isinstance(session_id, str):
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return {
        "path": str(path.resolve()),
        "started_at": started,
        "cwd": cwd,
        "size_bytes": size,
        "_started": parsed,
        "_id": session_id,
        "_bucket": bucket,
    }


def discover(project: Path, codex_home: Path, limit: int) -> list[dict[str, object]]:
    if limit < 1:
        raise SessionDiscoveryError("--limit must be at least 1")
    roots = _project_roots(project)
    by_id: dict[str, dict[str, object]] = {}
    for bucket in ("active", "archived"):
        location = codex_home / ("sessions" if bucket == "active" else "archived_sessions")
        if not location.is_dir():
            continue
        for path in location.rglob("*.jsonl"):
            item = _read_metadata(path, bucket)
            if item is None or not _belongs_to_project(Path(str(item["cwd"])), roots):
                continue
            session_id = str(item["_id"])
            previous = by_id.get(session_id)
            if previous is None or (previous["_bucket"] == "archived" and bucket == "active"):
                by_id[session_id] = item
    ordered = sorted(by_id.values(), key=lambda item: item["_started"], reverse=True)[:limit]
    if not ordered:
        raise SessionDiscoveryError(
            f"no usable Codex sessions found for {project.resolve()} under {codex_home.resolve()}"
        )
    return [
        {key: item[key] for key in ("path", "started_at", "cwd", "size_bytes")}
        for item in ordered
    ]


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    codex_home = args.codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    try:
        sessions = discover(args.project, codex_home, args.limit)
    except SessionDiscoveryError as exc:
        print(f"recent_codex_sessions: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(sessions, indent=2))
    else:
        for item in sessions:
            print(f"{item['started_at']}  {item['cwd']}  {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
