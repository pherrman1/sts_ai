#!/usr/bin/env python3
"""Read-only repository data inspector for AI architect/reviewer agents.

This helper intentionally supports only inspection operations. It never writes
repository files and refuses paths outside the current Git repository.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


def find_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).resolve().parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


ROOT = find_repo_root()


def resolve_repo_path(raw: str) -> Path:
    candidate = (ROOT / raw).resolve()

    try:
        candidate.relative_to(ROOT)
    except ValueError as exc:
        raise SystemExit(f"path escapes repository: {raw}") from exc

    if not candidate.exists():
        raise SystemExit(f"file not found: {raw}")

    if not candidate.is_file():
        raise SystemExit(f"not a file: {raw}")

    return candidate


def display_path(path: Path) -> str:
    return str(path.relative_to(ROOT))


def open_csv(path: Path):
    return path.open("r", encoding="utf-8", newline="")


def csv_rows(paths: Iterable[str]) -> int:
    rc = 0
    for raw in paths:
        path = resolve_repo_path(raw)
        with open_csv(path) as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                print(f"{display_path(path)}: rows=0 columns=0")
                continue
            rows = sum(1 for _ in reader)
        print(
            f"{display_path(path)}: rows={rows} "
            f"columns={len(header)}"
        )
    return rc


def csv_columns(paths: Iterable[str]) -> int:
    for raw in paths:
        path = resolve_repo_path(raw)
        with open_csv(path) as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                header = []
        print(f"{display_path(path)}:")
        for index, name in enumerate(header):
            print(f"  {index}: {name}")
    return 0


def csv_key_summary(paths: Iterable[str], key: str) -> int:
    exit_code = 0

    for raw in paths:
        path = resolve_repo_path(raw)

        with open_csv(path) as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or key not in reader.fieldnames:
                print(
                    f"{display_path(path)}: missing column {key!r}",
                    file=sys.stderr,
                )
                exit_code = 2
                continue

            counts: Counter[str] = Counter()
            rows = 0
            for row in reader:
                rows += 1
                counts[row.get(key, "")] += 1

        duplicates = sum(1 for count in counts.values() if count > 1)
        duplicate_rows = sum(count - 1 for count in counts.values() if count > 1)

        values = list(counts)
        minimum = min(values) if values else "-"
        maximum = max(values) if values else "-"

        print(
            f"{display_path(path)}: "
            f"rows={rows} "
            f"unique_{key}={len(counts)} "
            f"duplicated_{key}_values={duplicates} "
            f"duplicate_rows={duplicate_rows} "
            f"min_{key}={minimum} "
            f"max_{key}={maximum}"
        )

    return exit_code


def csv_value_counts(path_raw: str, column: str, limit: int) -> int:
    path = resolve_repo_path(path_raw)

    with open_csv(path) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None or column not in reader.fieldnames:
            raise SystemExit(
                f"{display_path(path)}: missing column {column!r}"
            )

        counts = Counter(row.get(column, "") for row in reader)

    print(
        f"{display_path(path)} column={column!r} "
        f"unique_values={len(counts)}"
    )

    for value, count in counts.most_common(limit):
        print(f"{count}\t{value}")

    return 0


def _to_finite_float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def csv_numeric_summary(path_raw: str, columns: list[str]) -> int:
    path = resolve_repo_path(path_raw)

    with open_csv(path) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise SystemExit(f"{display_path(path)}: CSV has no header")

        missing = [column for column in columns if column not in reader.fieldnames]
        if missing:
            raise SystemExit(
                f"{display_path(path)}: missing columns: {', '.join(missing)}"
            )

        data: dict[str, list[float]] = {column: [] for column in columns}
        invalid: Counter[str] = Counter()

        for row in reader:
            for column in columns:
                value = _to_finite_float(row.get(column, ""))
                if value is None:
                    invalid[column] += 1
                else:
                    data[column].append(value)

    print(f"{display_path(path)}:")

    for column in columns:
        values = data[column]
        if not values:
            print(
                f"  {column}: n=0 invalid_or_nonfinite={invalid[column]}"
            )
            continue

        mean = statistics.fmean(values)
        std = statistics.stdev(values) if len(values) >= 2 else 0.0

        print(
            f"  {column}: "
            f"n={len(values)} "
            f"invalid_or_nonfinite={invalid[column]} "
            f"min={min(values):.10g} "
            f"max={max(values):.10g} "
            f"mean={mean:.10g} "
            f"std={std:.10g}"
        )

    return 0


def preview(path_raw: str, lines: int) -> int:
    path = resolve_repo_path(path_raw)

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            if index >= lines:
                break
            print(line, end="")

    return 0


def json_keys(path_raw: str) -> int:
    path = resolve_repo_path(path_raw)

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        for key in data:
            print(key)
        return 0

    raise SystemExit(
        f"{display_path(path)}: top-level JSON value is not an object"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only structured inspection of repository data files."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "csv-rows",
        help="Report row and column counts for one or more CSV files.",
    )
    p.add_argument("paths", nargs="+")

    p = sub.add_parser(
        "csv-columns",
        help="Print CSV column names with indices.",
    )
    p.add_argument("paths", nargs="+")

    p = sub.add_parser(
        "csv-key-summary",
        help=(
            "Report rows, unique values, duplicates, and min/max for a key "
            "column such as seed."
        ),
    )
    p.add_argument("--key", required=True)
    p.add_argument("paths", nargs="+")

    p = sub.add_parser(
        "csv-value-counts",
        help="Print the most common values in one CSV column.",
    )
    p.add_argument("path")
    p.add_argument("column")
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser(
        "csv-numeric-summary",
        help="Report basic finite numeric statistics for selected columns.",
    )
    p.add_argument("path")
    p.add_argument("columns", nargs="+")

    p = sub.add_parser(
        "preview",
        help="Print the first N lines of a repository text file.",
    )
    p.add_argument("path")
    p.add_argument("--lines", type=int, default=40)

    p = sub.add_parser(
        "json-keys",
        help="Print keys of a top-level JSON object.",
    )
    p.add_argument("path")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "csv-rows":
        return csv_rows(args.paths)

    if args.command == "csv-columns":
        return csv_columns(args.paths)

    if args.command == "csv-key-summary":
        return csv_key_summary(args.paths, args.key)

    if args.command == "csv-value-counts":
        if args.limit <= 0:
            raise SystemExit("--limit must be positive")
        return csv_value_counts(args.path, args.column, args.limit)

    if args.command == "csv-numeric-summary":
        return csv_numeric_summary(args.path, args.columns)

    if args.command == "preview":
        if args.lines <= 0 or args.lines > 1000:
            raise SystemExit("--lines must be between 1 and 1000")
        return preview(args.path, args.lines)

    if args.command == "json-keys":
        return json_keys(args.path)

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
