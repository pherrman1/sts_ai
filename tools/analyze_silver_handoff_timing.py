#!/usr/bin/env python3
"""Summarize STS_SILVER_HANDOFF_TIMING `[silver-handoff]` lines.

Each line covers one Silver combat. The handoff buckets are live-state
conversion, private-state materialization, root setup (exact reroot or fresh
root) and semantic-action resolution. `other` is decision wall time spent
outside those buckets and the search, such as diagnostics and prior inference.
"""
import argparse
import json
import sys

PREFIX = "[silver-handoff] "
BUCKETS = ("conversion_micros", "materialize_micros", "root_setup_micros",
           "search_micros", "resolution_micros")


def parse(lines):
    rows = []
    for line in lines:
        start = line.find(PREFIX)
        if start < 0:
            continue
        fields = dict(item.split("=", 1) for item in line[start + len(PREFIX):].split())
        rows.append({key: float(value) for key, value in fields.items()})
    return rows


def summarize(rows):
    total = {key: sum(row[key] for row in rows)
             for key in ("decisions", "simulations", "decision_micros") + BUCKETS}
    decision = total["decision_micros"]
    handoff = (total["conversion_micros"] + total["materialize_micros"]
               + total["root_setup_micros"] + total["resolution_micros"])
    other = decision - handoff - total["search_micros"]
    decisions = total["decisions"]
    return {
        "combats": len(rows),
        "decisions": int(decisions),
        "simulations": int(total["simulations"]),
        "decision_seconds": decision / 1e6,
        "fraction": {key.removesuffix("_micros"): (total[key] / decision if decision else 0.0)
                     for key in BUCKETS}
        | {"handoff": handoff / decision if decision else 0.0,
           "other": other / decision if decision else 0.0},
        "mean_micros_per_decision": {key.removesuffix("_micros"):
                                     (total[key] / decisions if decisions else 0.0)
                                     for key in BUCKETS}
        | {"handoff": handoff / decisions if decisions else 0.0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", help="one_combat stdout logs (default: stdin)")
    args = parser.parse_args()
    lines = []
    if args.logs:
        for path in args.logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines.extend(handle)
    else:
        lines = sys.stdin.readlines()
    rows = parse(lines)
    if not rows:
        sys.exit("no [silver-handoff] lines found; run with STS_SILVER_HANDOFF_TIMING=1")
    print(json.dumps(summarize(rows), indent=2))


if __name__ == "__main__":
    main()
