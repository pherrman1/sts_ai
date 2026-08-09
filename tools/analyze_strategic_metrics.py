#!/usr/bin/env python3
"""Analyze deployment-aligned strategic prediction CSVs without retraining.

Input columns are: screen, margin, fired, modelIdx, fallbackIdx, bestIdx,
predQ, labelQ. ``predQ`` and ``labelQ`` are pipe-delimited candidate values.
Optional ``threshold`` and ``outcome`` columns are accepted. The same format
can be emitted by an offline checkpoint evaluator or a deployment replay.
"""
import argparse
import csv
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategic_metrics import analyze_decisions

REQUIRED = {"screen", "margin", "fired", "modelIdx", "fallbackIdx", "bestIdx",
            "predQ", "labelQ"}

def _list(value):
    return [float(x) for x in value.split("|")] if value else []


def load(path, owned_only=False):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        rows = []
        for line, raw in enumerate(reader, 2):
            try:
                if owned_only and int(raw.get("owned", "1")) == 0:
                    continue
                rows.append({"screen": raw["screen"], "margin": float(raw["margin"]),
                             "threshold": float(raw.get("threshold", "nan")),
                             "fired": int(raw["fired"]) != 0,
                             "model_idx": int(raw["modelIdx"]),
                             "fallback_idx": int(raw["fallbackIdx"]),
                             "best_idx": int(raw["bestIdx"]),
                             "pred_q": _list(raw["predQ"]),
                             "label_q": _list(raw["labelQ"]),
                             "outcome": raw.get("outcome")})
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed row {line}: {exc}") from exc
        return rows


def selftest():
    groups = [
        {"screen": "REWARDS", "margin": 2.0, "fired": True,
         "model_idx": 1, "fallback_idx": 0, "best_idx": 1,
         "pred_q": [0.1, 0.9], "label_q": [0.2, 0.8]},
        {"screen": "EVENT", "margin": 0.2, "fired": False,
         "model_idx": 0, "fallback_idx": 1, "best_idx": 1,
         "pred_q": [0.7, 0.6], "label_q": [0.2, 0.9]},
        {"screen": "REWARDS", "margin": 5.0, "fired": True,
         "model_idx": 1, "fallback_idx": 0, "best_idx": 0,
         "pred_q": [0.8, 0.9], "label_q": [0.7, 0.1]},
    ]
    result = analyze_decisions(groups)
    assert result["opportunities"] == 3
    assert result["overrides"]["fires"] == 2
    assert result["overrides"]["harmful"] == 1
    assert result["overrides"]["beneficial"] == 1
    assert result["per_screen"]["REWARDS"]["opportunities"] == 2
    assert result["gate_fire_curves"][3]["fires"] == 2  # threshold 1.0
    print("analyze_strategic_metrics self-test: PASS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--owned-only", action="store_true",
                    help="restrict to rows where owned=1")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        selftest(); return 0
    if not args.csv:
        ap.error("CSV path required (or --self-test)")
    rows = load(args.csv, owned_only=args.owned_only)
    report = analyze_decisions(rows)
    if args.json: print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps({"opportunities": report["opportunities"],
                          "overrides": report["overrides"],
                          "regret": report["regret"],
                          "per_screen": report["per_screen"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
