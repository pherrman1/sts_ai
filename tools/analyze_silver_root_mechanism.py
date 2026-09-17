#!/usr/bin/env python3
"""Frozen 64-root, four-replicate Silver mechanism analysis; no game execution."""

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


CONTRASTS = ("C-A", "B-A", "D-A", "D-C", "D-B")
RESAMPLES = 10000
SEED = 20260917
CLASSIFICATIONS = ("ROOT_PRIOR_SIGNAL_CONFIRMED", "ROOT_ORDER_SIGNAL_ONLY",
                   "ROOT_COMBINATION_ONLY", "ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED",
                   "ROOT_GUIDANCE_INCONCLUSIVE")


def select(rows):
    identities = [row["root_id"] for row in rows]
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ValueError("invalid root identity")
    if len(set(identities)) != len(identities) or len(rows) < 64:
        raise ValueError("need at least 64 unique eligible roots")
    return sorted(rows, key=lambda row: (
        hashlib.sha256(row["root_id"].encode()).hexdigest(), row["root_id"]))[:64]


def analyze(rows, expected_roots=64):
    indexed = {}
    seeds = {}
    sources = {}
    for row in rows:
        root, arm, replicate = row["root_id"], row["arm"], row["replicate"]
        if (not isinstance(root, str) or not root or arm not in tuple("ABCD")
                or type(replicate) is not int or replicate not in range(4)
                or type(row["simulations"]) is not int or row["simulations"] != 32
                or type(row["source_seed"]) is not int or row["source_seed"] < 0
                or type(row["search_seed"]) is not int or row["search_seed"] <= 0
                or type(row["b_best"]) is not bool
                or type(row["b_regret"]) not in (int, float)
                or not math.isfinite(row["b_regret"]) or row["b_regret"] < 0
                or not isinstance(row["selected_action_fingerprint"], str)
                or not row["selected_action_fingerprint"]):
            raise ValueError("invalid replay row")
        key = root, arm, replicate
        if key in indexed:
            raise ValueError("duplicate root/arm/replicate")
        indexed[key] = row
        seed_key = root, replicate
        if seeds.setdefault(seed_key, row["search_seed"]) != row["search_seed"]:
            raise ValueError("search replicate identities differ between arms")
        if sources.setdefault(root, row["source_seed"]) != row["source_seed"]:
            raise ValueError("root source identity changed")
    roots = sorted(sources)
    expected = {(root, arm, replicate) for root in roots for arm in "ABCD"
                for replicate in range(4)}
    if len(roots) != expected_roots or not roots or set(indexed) != expected:
        raise ValueError("incomplete root/arm/replicate population")
    for root in roots:
        if len({seeds[root, replicate] for replicate in range(4)}) != 4:
            raise ValueError("replicate RNG identities must be distinct")
    reduced = {}
    for root in roots:
        reduced[root] = {}
        for arm in "ABCD":
            samples = [indexed[root, arm, replicate] for replicate in range(4)]
            regrets = [sample["b_regret"] for sample in samples]
            reduced[root][arm] = {
                "regret": statistics.mean(regrets),
                "b_best_probability": statistics.mean(sample["b_best"] for sample in samples),
                "regret_sd": statistics.pstdev(regrets),
                "regret_range": max(regrets) - min(regrets)}
    generator = random.Random(SEED)
    draws = [[generator.randrange(len(roots)) for _ in roots] for _ in range(RESAMPLES)]

    def interval(values):
        means = sorted(statistics.mean(values[index] for index in draw) for draw in draws)
        return [means[249], means[9749]]

    contrasts = {}
    for contrast in CONTRASTS:
        treatment, control = contrast.split("-")
        deltas = [reduced[root][treatment]["regret"] - reduced[root][control]["regret"]
                  for root in roots]
        probabilities = [reduced[root][treatment]["b_best_probability"]
                         - reduced[root][control]["b_best_probability"] for root in roots]
        contrasts[contrast] = {
            "mean_regret_delta": statistics.mean(deltas), "regret_ci95": interval(deltas),
            "b_best_probability_delta": statistics.mean(probabilities),
            "b_best_probability_ci95": interval(probabilities),
            "improved": sum(delta < 0 for delta in deltas),
            "worsened": sum(delta > 0 for delta in deltas),
            "tied": sum(delta == 0 for delta in deltas),
            "root_deltas": dict(zip(roots, deltas)),
            "worst_harms": sorted(zip(roots, deltas), key=lambda pair: pair[1], reverse=True)[:10]}
    return {"roots": len(roots), "replicates_per_root": 4, "bootstrap_resamples": RESAMPLES,
            "bootstrap_seed": SEED, "bootstrap_unit": "root", "contrasts": contrasts,
            "arms": {arm: {field: statistics.mean(reduced[root][arm][field] for root in roots)
                           for field in reduced[roots[0]][arm]} for arm in "ABCD"},
            "root_results": reduced, "source_seeds": sources, "classification": None,
            "predeclared_classifications": CLASSIFICATIONS,
            "interpretation": "Statistical screen only; correctness and harmful-tail review remain required."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "analyze"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest_path = Path(str(args.output) + ".manifest.json")
    if args.output.exists() or manifest_path.exists():
        raise ValueError("refusing existing output/manifest")
    raw = args.input.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if args.mode == "select":
        result = select(rows)
        content = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in result)
        manifest = {"schema": "silver_root_mechanism_selection_v1",
                    "source_capture_sha256": hashlib.sha256(raw).hexdigest(),
                    "selected_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "selection": "lowest 64 SHA256(UTF8(root_id)); root_id breaks hash ties",
                    "selected_root_ids": [row["root_id"] for row in result],
                    "source_root_count": len(rows),
                    "source_seeds": sorted({row["source_seed"] for row in rows})}
    else:
        for row in rows:
            if row.get("schema") != "silver_root_mechanism_replay_v1" or row.get("fixture_only") is not False:
                raise ValueError("analysis requires scientific replay records, not fixtures")
        result = analyze(rows)
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        content = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with args.output.open("x") as output:
        output.write(content)
    if args.mode == "select":
        with manifest_path.open("x") as output:
            json.dump(manifest, output, indent=2)


if __name__ == "__main__":
    main()
