#!/usr/bin/env python3
"""Validate and summarize Searcher3 RNG-exposure root telemetry."""

import argparse
import collections
import csv
import math
from pathlib import Path


HIST = {
    "ai": ["ai_first_0", "ai_first_1", "ai_first_2", "ai_first_3", "ai_first_4plus", "ai_never"],
    "card": ["card_first_0", "card_first_1", "card_first_2", "card_first_3", "card_first_4plus", "card_never"],
}

FAMILIES = {
    "ORACLE",
    "DRAW_ORDER",
    "SHUFFLE_RNG",
    "CARD_RANDOM_RNG",
    "AI_RNG",
    "MISC_RNG",
    "MONSTER_HP_RNG",
    "POTION_RNG",
    "ALL_FRESH",
}


def quantile(values, p):
    values = sorted(values)
    if not values:
        raise ValueError("quantile of empty group")
    x = (len(values) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] if lo == hi else values[lo] + (values[hi] - values[lo]) * (x - lo)


def root_key(row):
    return tuple(row[k] for k in ("seed", "encounter", "floor", "source_filter_decision_idx"))


def validate(rows):
    required = {"source_filter_decision_idx", "search_decision_idx", "root_observation_hash", "action_bits"}
    missing = required - set(rows[0])
    if missing:
        raise AssertionError(f"missing required columns: {sorted(missing)}")
    groups = collections.defaultdict(list)
    for row in rows:
        groups[root_key(row)].append(row)
        assert int(row["search_decision_idx"]) == int(row["source_filter_decision_idx"]) + 1
        assert 0 <= float(row["ai_fraction"]) <= 1
        assert 0 <= float(row["card_fraction"]) <= 1
        simulations = int(row["simulations"])
        for stream, hist in HIST.items():
            assert sum(int(row[k]) for k in hist) == simulations, (root_key(row), stream)
    roots = [r for r in rows if r["action_bits"] == "4294967295"]
    assert len(roots) == len(groups), "root identifiers are not unique"
    for key, group in groups.items():
        root = next(r for r in group if r["action_bits"] == "4294967295")
        assert len({r["root_observation_hash"] for r in group}) == 1
        action_total = sum(int(r["simulations"]) for r in group if r["action_bits"] != "4294967295")
        assert action_total == int(root["simulations"]), (key, action_total, root["simulations"])
    return roots, groups


def summary(rows, field):
    values = [float(r[field]) for r in rows]
    return {
        "roots": len(rows),
        "median": quantile(values, .5),
        "q25": quantile(values, .25),
        "q75": quantile(values, .75),
        "min": min(values),
        "max": max(values),
        "any": sum(v > 0 for v in values) / len(values),
        "ge10": sum(v >= .1 for v in values) / len(values),
        "ge50": sum(v >= .5 for v in values) / len(values),
    }


def print_summary(label, rows):
    for field in ("ai_fraction", "card_fraction"):
        s = summary(rows, field)
        assert s["any"] + 1e-12 >= s["ge10"] >= s["ge50"] - 1e-12
        print(label, field, " ".join(f"{k}={v:.6f}" if isinstance(v, float) else f"{k}={v}" for k, v in s.items()))


def grouped(rows, field):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    for key in sorted(groups, key=lambda x: int(x)):
        print_summary(f"{field}={key}", groups[key])


def mobility_join(roots, geometry):
    by_key = {(r["seed"], r["encounter"], r["floor"], r["decision_idx"], r["proposal_family"]): r for r in geometry}
    for family, counter, exposure in (("AI_RNG", "ai_consumed", "ai_fraction"), ("CARD_RANDOM_RNG", "card_random_consumed", "card_fraction")):
        joined = []
        for root in roots:
            key = (root["seed"], root["encounter"], root["floor"], root["source_filter_decision_idx"], family)
            geo = by_key.get(key)
            if geo and int(geo[counter]) > 0 and int(root["source_filter_decision_idx"]) >= 8:
                joined.append((root, geo))
        print(f"JOIN family={family} late_used_roots={len(joined)}")
        cells = collections.Counter()
        for root, geo in joined:
            mobility = "ge8" if int(geo["unique"]) >= 8 else "ge4" if int(geo["unique"]) >= 4 else "any" if int(geo["unique"]) else "zero"
            exposure_class = "ge50" if float(root[exposure]) >= .5 else "ge10" if float(root[exposure]) >= .1 else "positive" if float(root[exposure]) > 0 else "zero"
            cells[(mobility, exposure_class)] += 1
        for key in sorted(cells):
            print(" ", key[0], key[1], cells[key])


def validate_geometry(geometry, expected_proposals):
    groups = collections.defaultdict(list)
    for row in geometry:
        groups[(row["seed"], row["encounter"], row["floor"], row["decision_idx"])].append(row)
    assert groups, "geometry has no trigger groups"
    for key, group in groups.items():
        families = [r["proposal_family"] for r in group]
        assert len(group) == 9, (key, len(group))
        assert set(families) == FAMILIES, (key, sorted(set(families)))
        assert len(families) == len(set(families)), (key, families)
        assert families.count("ORACLE") == 1, key
        for row in group:
            proposals = int(row["proposals"])
            expected = 1 if row["proposal_family"] == "ORACLE" else expected_proposals
            assert proposals == expected, (key, row["proposal_family"], proposals, expected)
    return set(groups)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exposure", type=Path)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--proposals", type=int, default=64)
    args = parser.parse_args()
    with args.exposure.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    roots, groups = validate(rows)
    print(f"VALIDATION PASS rows={len(rows)} roots={len(roots)} groups={len(groups)}")
    print_summary("overall", roots)
    grouped(roots, "source_filter_decision_idx")
    grouped(roots, "seed")
    grouped(roots, "encounter")
    grouped(roots, "floor")
    print("ROOT_ACTION_ROWS", len(rows) - len(roots))
    action_groups = collections.defaultdict(list)
    for row in rows:
        if row["action_bits"] != "4294967295":
            action_groups[row["action_bits"]].append(row)
    for action, action_rows in sorted(action_groups.items(), key=lambda item: -sum(int(r["simulations"]) for r in item[1])):
        print_summary(f"action_bits={action}", action_rows)
    with args.geometry.open(newline="") as handle:
        geometry = list(csv.DictReader(handle))
    geometry_keys = validate_geometry(geometry, args.proposals)
    mobility_join(roots, geometry)
    exposure_keys = {root_key(r) for r in roots}
    unexpected = exposure_keys - geometry_keys
    assert not unexpected, f"exposure source keys absent from same-run geometry: {sorted(unexpected)[:5]}"
    print("COVERAGE geometry_trigger_groups", len(geometry_keys), "exposure_source_groups", len(exposure_keys), "matched", len(exposure_keys), "geometry_only", len(geometry_keys - exposure_keys), "unexpected", len(unexpected))


if __name__ == "__main__":
    main()