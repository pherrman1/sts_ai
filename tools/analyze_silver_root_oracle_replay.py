#!/usr/bin/env python3
"""Summarize the bounded frozen-label Silver root oracle replay."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    args = parser.parse_args()
    with args.replay.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    expected_arms = {"current_uct", "oracle_order_uct", "oracle_rank_puct", "oracle_visit_puct"}
    expected_budgets = {16, 32, 64, 128, 1000}
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError("unexpected replay schema")
    if len(rows) != 63 * len(expected_arms) * len(expected_budgets):
        raise ValueError(f"unexpected replay row count: {len(rows)}")
    groups = {row["group_id"] for row in rows}
    if len(groups) != 63:
        raise ValueError(f"unexpected group count: {len(groups)}")
    if {row["arm"] for row in rows} != expected_arms:
        raise ValueError("unexpected replay arms")
    if {row["budget"] for row in rows} != expected_budgets:
        raise ValueError("unexpected replay budgets")

    grouped = defaultdict(list)
    for row in rows:
        if not row["accepted"]:
            raise ValueError("replay contains rejected decision")
        grouped[(row["budget"], row["arm"])].append(row)
    print("| budget | arm | anchors | B top-choice agreement | mean B regret | zero-regret anchors |")
    print("| ---: | --- | ---: | ---: | ---: | ---: |")
    summary = {}
    for key in sorted(grouped):
        bucket = grouped[key]
        top = sum(row["frozen_b_top_choice"] for row in bucket) / len(bucket)
        regret = statistics.fmean(row["frozen_b_regret"] for row in bucket)
        zero = sum(row["frozen_b_regret"] == 0 for row in bucket)
        summary[f"{key[0]}:{key[1]}"] = {
            "anchors": len(bucket),
            "top_choice_agreement": top,
            "mean_regret": regret,
            "zero_regret_anchors": zero,
        }
        print(f"| {key[0]} | {key[1]} | {len(bucket)} | {top:.6%} | {regret:.6f} | {zero} |")
    print(json.dumps({"schema": "silver_root_oracle_replay_summary_v1", "summary": summary},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
