#!/usr/bin/env python3
"""Analyze sampled Silver rollout-start VNet observations.

The unit of train/test separation is the complete run seed.  Sibling metrics
use the nearest non-random Silver parent identity recorded by the observer;
leaves from different combats are never compared as siblings.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED = {
    "run_seed", "act", "floor", "encounter", "combat_decision_ordinal",
    "root_state_hash", "parent_state_hash", "leaf_state_hash", "depth",
    "leaf_cur_hp", "leaf_max_hp", "vnet_raw_prediction",
    "rollout_terminal_outcome", "rollout_utility", "rollout_action_count",
    "rollout_turn_delta", "rollout_wall_micros",
}


def finite(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite numeric value: {value!r}")
    return result


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return _read_rows_reader(csv.DictReader(stream), path)


def _read_rows_reader(reader: csv.DictReader, path: Path | str) -> list[dict]:
    missing = REQUIRED - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
    rows = []
    for line, raw in enumerate(reader, 2):
        if not raw.get("rollout_utility", "").strip():
            continue
        try:
            row = dict(raw)
            row["seed"] = row["run_seed"]
            row["act_n"] = int(row["act"])
            row["hp_ratio"] = finite(row["leaf_cur_hp"]) / max(1.0, finite(row["leaf_max_hp"]))
            row["v"] = finite(row["vnet_raw_prediction"])
            row["u"] = finite(row["rollout_utility"])
            row["length"] = int(row["rollout_action_count"])
            row["group"] = (
                row["run_seed"], row["act"], row["floor"], row["encounter"],
                row["combat_decision_ordinal"], row["root_state_hash"],
                row["parent_state_hash"],
            )
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{path}:{line}: invalid row: {exc}") from exc
        rows.append(row)
    return rows


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    xx = sum((x - mx) ** 2 for x in xs)
    yy = sum((y - my) ** 2 for y in ys)
    if xx == 0 or yy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(xx * yy)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            result[ordered[k][0]] = rank
        i = j
    return result


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(ranks(xs), ranks(ys))


def fmt(value: float | int | None) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.6f}"


def pair_metrics(groups: dict[tuple, list[dict]]) -> dict:
    all_pairs = strict_concordant = strict_discordant = both_ties = 0
    v_ties = u_ties = 0
    centered_sq = centered_abs = centered_n = 0
    top_n = top_agree = 0
    regrets = []
    for group_rows in groups.values():
        if len(group_rows) < 2:
            continue
        v_mean = statistics.fmean(row["v"] for row in group_rows)
        u_mean = statistics.fmean(row["u"] for row in group_rows)
        for row in group_rows:
            dv, du = row["v"] - v_mean, row["u"] - u_mean
            centered_sq += (dv - du) ** 2
            centered_abs += abs(dv - du)
            centered_n += 1
        for index, left in enumerate(group_rows):
            for right in group_rows[index + 1:]:
                sv = (left["v"] > right["v"]) - (left["v"] < right["v"])
                su = (left["u"] > right["u"]) - (left["u"] < right["u"])
                all_pairs += 1
                if sv == su == 0:
                    both_ties += 1
                elif sv == 0:
                    v_ties += 1
                elif su == 0:
                    u_ties += 1
                elif sv == su:
                    strict_concordant += 1
                else:
                    strict_discordant += 1
        selected = max(enumerate(group_rows), key=lambda item: (item[1]["v"], -item[0]))[1]
        best_u = max(row["u"] for row in group_rows)
        top_n += 1
        top_agree += selected["u"] == best_u
        regrets.append(best_u - selected["u"])
    strict_total = strict_concordant + strict_discordant
    return {
        "groups": sum(len(rows) >= 2 for rows in groups.values()),
        "all_pairs": all_pairs,
        "strict_concordant": strict_concordant,
        "strict_discordant": strict_discordant,
        "both_ties": both_ties,
        "vnet_ties_only": v_ties,
        "utility_ties_only": u_ties,
        "concordance": strict_concordant / strict_total if strict_total else None,
        "centered_rmse": math.sqrt(centered_sq / centered_n) if centered_n else None,
        "centered_mae": centered_abs / centered_n if centered_n else None,
        "top_groups": top_n,
        "top_agreement": top_agree / top_n if top_n else None,
        "mean_regret": statistics.fmean(regrets) if regrets else None,
        "median_regret": statistics.median(regrets) if regrets else None,
    }


def describe(rows: list[dict]) -> dict:
    xs, ys = [row["v"] for row in rows], [row["u"] for row in rows]
    return {"n": len(rows), "pearson": pearson(xs, ys), "spearman": spearman(xs, ys)}


def affine(rows: list[dict], train_seeds: set[str], test_seeds: set[str]) -> dict:
    train = [row for row in rows if row["seed"] in train_seeds]
    test = [row for row in rows if row["seed"] in test_seeds]
    if len(train) < 2:
        return {"train_rows": len(train), "test_rows": len(test), "status": "insufficient_train"}
    mean_v = statistics.fmean(row["v"] for row in train)
    mean_u = statistics.fmean(row["u"] for row in train)
    denom = sum((row["v"] - mean_v) ** 2 for row in train)
    if denom == 0:
        return {"train_rows": len(train), "test_rows": len(test), "status": "constant_vnet"}
    a = sum((row["v"] - mean_v) * (row["u"] - mean_u) for row in train) / denom
    b = mean_u - a * mean_v
    def errors(data: list[dict]) -> dict:
        if not data:
            return {"n": 0, "rmse": None, "mae": None, "pearson": None}
        predicted = [a * row["v"] + b for row in data]
        actual = [row["u"] for row in data]
        return {
            "n": len(data),
            "rmse": math.sqrt(statistics.fmean((x - y) ** 2 for x, y in zip(predicted, actual))),
            "mae": statistics.fmean(abs(x - y) for x, y in zip(predicted, actual)),
            "pearson": pearson(predicted, actual),
        }
    return {"status": "ok", "a": a, "b": b, "train": errors(train), "held_out": errors(test)}


def breakdown(rows: list[dict], label: str, predicate) -> list[tuple[str, list[dict]]]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[predicate(row)].append(row)
    return sorted(buckets.items(), key=lambda item: str(item[0]))


def report(rows: list[dict], holdout_mod: int) -> str:
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    lines = [
        f"rows={len(rows)} seeds={len({row['seed'] for row in rows})} groups={len(groups)}",
        "global: " + " ".join(f"{key}={fmt(value)}" for key, value in describe(rows).items()),
        "sibling: " + " ".join(f"{key}={fmt(value)}" for key, value in pair_metrics(groups).items()),
        "sibling metrics exclude groups with fewer than 2 observations; concordance excludes strict ties.",
        "breakdown (n, spearman, concordance, centered_rmse, top_agreement, mean_regret):",
    ]
    sections = [
        ("act", lambda row: f"act{row['act_n']}"),
        ("hp", lambda row: "low_hp" if row["hp_ratio"] < 0.5 else "high_hp"),
        ("rollout_length", lambda row: "short_0_5" if row["length"] <= 5 else ("medium_6_15" if row["length"] <= 15 else "long_16_plus")),
    ]
    for name, predicate in sections:
        lines.append(f"  {name}:")
        for bucket, bucket_rows in breakdown(rows, name, predicate):
            bucket_groups = defaultdict(list)
            for row in bucket_rows:
                bucket_groups[row["group"]].append(row)
            metric = pair_metrics(bucket_groups)
            desc = describe(bucket_rows)
            lines.append("    " + str(bucket) + " " + " ".join([
                f"n={len(bucket_rows)}", f"spearman={fmt(desc['spearman'])}",
                f"concordance={fmt(metric['concordance'])}", f"centered_rmse={fmt(metric['centered_rmse'])}",
                f"top_agreement={fmt(metric['top_agreement'])}", f"mean_regret={fmt(metric['mean_regret'])}",
            ]))
    seeds = sorted({row["seed"] for row in rows})
    held_out = {seed for index, seed in enumerate(seeds) if index % holdout_mod == 0}
    train = set(seeds) - held_out
    cal = affine(rows, train, held_out)
    lines.append(f"affine calibration: holdout every {holdout_mod}th sorted seed; train_seeds={len(train)} held_out_seeds={len(held_out)}")
    lines.append("  " + " ".join(f"{key}={value}" for key, value in cal.items()))
    return "\n".join(lines)


def self_test() -> int:
    header = [
        "run_seed,act,floor,encounter,combat_decision_ordinal,root_state_hash,parent_state_hash,leaf_state_hash,depth,leaf_cur_hp,leaf_max_hp,vnet_raw_prediction,rollout_terminal_outcome,rollout_utility,rollout_action_count,rollout_turn_delta,rollout_wall_micros",
    ]
    rows = []
    for seed, values in (("1", ((1, 2), (2, 4), (3, 1))), ("2", ((1, 3), (2, 5), (3, 2)))):
        for index, (v, u) in enumerate(values):
            rows.append(f"{seed},1,4,CULTIST,0,r,p,{index},1,50,80,{v},0,{u},2,1,10")
    parsed = _read_rows_reader(csv.DictReader(io.StringIO("\n".join(header + rows) + "\n")), "fixture.csv")
    metrics = pair_metrics({key: list(value) for key, value in _group(parsed).items()})
    assert len(parsed) == 6 and metrics["concordance"] == 1 / 3
    assert affine(parsed, {"1"}, {"2"})["status"] == "ok"
    print("analyze_silver_vnet_leaf self-test PASS")
    return 0


def _group(rows: list[dict]) -> dict:
    result = defaultdict(list)
    for row in rows:
        result[row["group"]].append(row)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--holdout-mod", type=int, default=2)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.csv is None or args.holdout_mod < 2:
        parser.error("CSV path and --holdout-mod >= 2 are required")
    print(report(read_rows(args.csv), args.holdout_mod))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, ValueError) as exc:
        print(f"analyze_silver_vnet_leaf: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
