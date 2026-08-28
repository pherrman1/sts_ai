#!/usr/bin/env python3
import argparse
import csv
import json

import numpy as np
import xgboost as xgb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features")
    parser.add_argument("relabels")
    parser.add_argument("model_json")
    parser.add_argument("native_predictions")
    parser.add_argument("--tolerance", type=float, default=1e-5)
    args = parser.parse_args()
    anchors = set()
    with open(args.relabels, encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if (row.get("budget") == 25000 and row.get("replicate") == "B"
                    and row.get("valid", True)):
                anchors.add(row["group_id"])
    rows = []
    with open(args.features, encoding="utf-8") as source:
        next(source)
        for line in source:
            row = json.loads(line)
            if row["group_id"] in anchors:
                rows.append(row)
    booster = xgb.Booster()
    booster.load_model(args.model_json)
    matrix = xgb.DMatrix(np.asarray([row["features"] for row in rows], dtype=np.float32),
                         feature_names=booster.feature_names)
    python_predictions = booster.predict(matrix, iteration_range=(0, 97))
    with open(args.native_predictions, encoding="utf-8", newline="") as source:
        native_predictions = np.asarray(
            [float(row["native_prediction"]) for row in csv.DictReader(source)])
    delta = np.abs(python_predictions - native_predictions)
    report = {"anchor_parents": len(anchors), "anchor_actions": len(rows),
              "max_abs_error": float(delta.max()), "mean_abs_error": float(delta.mean()),
              "tolerance": args.tolerance, "passed": bool(np.all(delta <= args.tolerance))}
    print(json.dumps(report, sort_keys=True))
    if len(anchors) != 93 or len(rows) != 370 or not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
