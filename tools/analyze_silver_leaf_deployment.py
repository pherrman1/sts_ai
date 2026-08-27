#!/usr/bin/env python3
"""Compare Silver M10 with the deployed combat VNet on independent 25k-B."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
import xgboost as xgb

from train_silver_leaf_models import load_features, load_labels, metrics, sha256


class CompactValueNet:
    def __init__(self, path: Path, canonical_names: list[str]):
        tokens = path.read_text(encoding="utf-8").split()
        pos = 0
        def take(expected=None):
            nonlocal pos
            value = tokens[pos]; pos += 1
            if expected is not None and value != expected:
                raise ValueError(f"expected {expected}, got {value}")
            return value
        take("nfeat"); count = int(take())
        index = {name: i for i, name in enumerate(canonical_names)}
        self.selection = []
        for _ in range(count):
            take("feat"); self.selection.append(index[take()])
        take("base_score"); self.base = float(take())
        take("ntrees"); tree_count = int(take())
        self.trees = []
        for tree_index in range(tree_count):
            take("tree")
            if int(take()) != tree_index: raise ValueError("non-sequential tree index")
            nodes = []
            for _ in range(int(take())):
                kind = take()
                if kind == "L": nodes.append((-1, float(take()), 0, 0))
                elif kind == "S": nodes.append((int(take()), float(take()), int(take()), int(take())))
                else: raise ValueError(f"unknown node kind {kind}")
            self.trees.append(nodes)
        if pos != len(tokens): raise ValueError("trailing compact-model tokens")

    def predict(self, canonical: np.ndarray) -> np.ndarray:
        selected = canonical[:, self.selection]
        output = np.full(len(canonical), self.base, dtype=np.float64)
        for tree in self.trees:
            for row_index, row in enumerate(selected):
                node_index = 0
                while tree[node_index][0] >= 0:
                    feature, threshold, yes, no = tree[node_index]
                    node_index = yes if row[feature] < threshold else no
                output[row_index] += tree[node_index][1]
        return output


def timed(callable_, repeats):
    durations = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = callable_()
        durations.append(time.perf_counter() - start)
    return result, durations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("m10_json", type=Path)
    parser.add_argument("current_compact", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("parity_csv", type=Path)
    parser.add_argument("--m10-trees", type=int, default=501)
    parser.add_argument("--timing-repeats", type=int, default=10)
    args = parser.parse_args()

    names, feature_rows = load_features(args.features)
    labels, anchor_groups = load_labels(args.relabels)
    rows = []
    for leaf, feature in sorted(feature_rows.items()):
        reference = labels.get((leaf, 25000, "B"))
        if feature["group_id"] in anchor_groups and reference and reference.get("teacher_valid", True):
            rows.append({**feature, "reference": reference["original_root_corrected_teacher_value"]})
    matrix = np.asarray([row["features"] for row in rows], dtype=np.float32)

    booster = xgb.Booster(); booster.load_model(args.m10_json)
    if booster.feature_names != names: raise SystemExit("M10 feature names/order differ from stored canonical rows")
    if args.m10_trees > booster.num_boosted_rounds(): raise SystemExit("M10 tree limit exceeds stored rounds")
    dmatrix = xgb.DMatrix(matrix, feature_names=names)
    m10, m10_times = timed(lambda: booster.predict(
        dmatrix, iteration_range=(0, args.m10_trees)), args.timing_repeats)
    current_model = CompactValueNet(args.current_compact, names)
    current, current_times = timed(lambda: current_model.predict(matrix), args.timing_repeats)

    report = {
        "schema": "silver_leaf_deployment_sanity_v1",
        "inputs": {"features_sha256": sha256(args.features), "relabels_sha256": sha256(args.relabels),
                   "m10_json_sha256": sha256(args.m10_json),
                   "current_compact_sha256": sha256(args.current_compact)},
        "anchor": {"groups": len({row["group_id"] for row in rows}), "rows": len(rows)},
        "m10_tree_count": args.m10_trees,
        "metrics": {"current_combat_vnet": metrics(rows, current), "m10": metrics(rows, m10)},
        "python_inference": {
            "repeats": args.timing_repeats,
            "current_compact_seconds": {"min": min(current_times), "median": float(np.median(current_times))},
            "m10_xgboost_seconds": {"min": min(m10_times), "median": float(np.median(m10_times))},
            "warning": "Diagnostic implementation timing only; Release native timing is decision-bearing."
        }
    }
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.parity_csv.open("w", newline="", encoding="utf-8") as stream:
        # vnettest parses a deliberately strict comma header and does not strip
        # a Windows CR from the final field.
        writer = csv.writer(stream, lineterminator="\n"); writer.writerow([*names, "pyPred"])
        writer.writerows([*matrix[index], float(m10[index])] for index in range(len(rows)))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
