#!/usr/bin/env python3
"""Export XGBoost win boosters as one CompactTreeNet file (margin average).

Each booster's trees are kept with leaf values divided by N, and the base
margin is the mean of the boosters' base margins, so the native value is
sigmoid(mean margin). This is the margin average of the seeds, not the
probability average `tools.vwin_e3_cf` reports; `--check` prints both.

    python3 -m tools.vwin_export_ensemble OUT.txt F2-s0.ubj F2-s1.ubj F2-s2.ubj \
        --check E3_ROOT/w00/chunk0/part0.map.csv
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from tools.analysis.vwin_tree_utils import load_trees, predict_rows


def _booster(path):
    import xgboost as xgb
    booster = xgb.Booster()
    booster.load_model(str(path))
    if not booster.feature_names:
        raise ValueError(f"{path}: booster has no feature names")
    base = float(json.loads(booster.save_config())["learner"]["learner_model_param"]["base_score"].strip("[]"))
    return booster, base


def export(out, paths):
    boosters = [_booster(p) for p in paths]
    names = list(boosters[0][0].feature_names)
    if any(list(b.feature_names) != names for b, _ in boosters):
        raise ValueError("boosters disagree on feature names")
    dumps = [d for b, _ in boosters for d in b.get_dump(dump_format="json")]
    used = sorted({n for d in dumps for n in re.findall(r'"split": "([^"]+)"', d)}, key=names.index)
    margin = sum(math.log(p / (1 - p)) for _, p in boosters) / len(boosters)
    scale = 1.0 / len(boosters)
    lines = [f"nfeat {len(used)}"] + [f"feat {n}" for n in used]
    lines += ["logistic 1", f"base_score {1 / (1 + math.exp(-margin))!r}", f"ntrees {len(dumps)}"]
    position = {n: i for i, n in enumerate(used)}
    for t, d in enumerate(dumps):
        order, queue = [], [json.loads(d)]
        while queue:   # breadth-first, as tools/screen_leaf_gbm.py
            node = queue.pop(0)
            order.append(node)
            queue += node.get("children", [])
        index = {n["nodeid"]: i for i, n in enumerate(order)}
        lines.append(f"tree {t} {len(order)}")
        for n in order:
            if "leaf" in n:
                lines.append(f"L {n['leaf'] * scale!r}")
            else:
                if n["missing"] not in (n["yes"], n["no"]):
                    raise ValueError("unexpected missing branch")
                lines.append(f"S {position[n['split']]} {float(n['split_condition'])!r} "
                             f"{index[n['yes']]} {index[n['no']]}")
    Path(out).write_text("\n".join(lines) + "\n")
    return boosters, names


def check(out, boosters, names, csv):
    """Max |difference| of the export against the boosters' mean margin."""
    import pandas as pd
    import xgboost as xgb
    df = pd.read_csv(csv)
    X = df[names].to_numpy(np.float32)
    dm = xgb.DMatrix(X, feature_names=names)
    margins = np.array([b.predict(dm, output_margin=True) for b, _ in boosters])
    probs = 1 / (1 + np.exp(-margins))
    feats, trees, logistic, _, base_margin = load_trees(out)
    native = predict_rows(df[feats].to_numpy(np.float32), trees, logistic, base_margin)
    return dict(rows=len(df), max_abs_vs_margin_mean=float(np.max(np.abs(native - 1 / (1 + np.exp(-margins.mean(0)))))),
                max_abs_vs_prob_mean=float(np.max(np.abs(native - probs.mean(0)))))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("boosters", nargs="+")
    ap.add_argument("--check", help="CSV with the boosters' feature columns (e.g. an E3 .map.csv)")
    args = ap.parse_args()
    boosters, names = export(args.out, args.boosters)
    report = dict(out=args.out, sha256=hashlib.sha256(Path(args.out).read_bytes()).hexdigest(),
                  inputs={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in args.boosters},
                  trees=sum(b.num_boosted_rounds() for b, _ in boosters), features=len(names))
    if args.check:
        report["check"] = check(args.out, boosters, names, args.check)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
