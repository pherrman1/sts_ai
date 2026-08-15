#!/usr/bin/env python3
"""Validate Phase-13A candidate ownership before outcome evaluation."""
import argparse
import csv
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", type=Path)
    args = ap.parse_args()
    rows = list(csv.DictReader(args.candidates.open(newline="")))
    if not rows:
        raise SystemExit("no candidates")
    failures = []
    for row in rows:
        if row["gateOwned"] != "1":
            failures.append((row, "gateOwned != 1"))
        if row["liveV4Idx"] != row["v4Idx"]:
            failures.append((row, "liveV4Idx != v4Idx"))
        if abs(float(row["liveV4Margin"]) - float(row["v4Margin"])) > 1e-9:
            failures.append((row, "liveV4Margin != v4Margin"))
        if row["screen"] == "2" and any(
            int(row[name]) != 0 for name in ("goldRewardCount", "relicCount", "potionCount")
        ):
            failures.append((row, "REWARDS has pending automatic reward"))
    if failures:
        for row, reason in failures[:20]:
            print(f"{row['sourceSeed']},{row['decisionId']}: {reason}")
        raise SystemExit(f"ownership validation failed: {len(failures)} failures")
    print(f"ownership_smoke_passed candidates={len(rows)}")


if __name__ == "__main__":
    main()