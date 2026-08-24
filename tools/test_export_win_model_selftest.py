#!/usr/bin/env python3
"""Deterministic compact-export regression: truncation and logistic handling."""
import math
import os
import pathlib
import sys
import tempfile

import numpy as np
import xgboost as xgb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from export_win_model import export_booster


def compact_predict(path, row):
    tokens = iter(open(path, encoding="utf-8").read().split())
    assert next(tokens) == "nfeat"; nfeat = int(next(tokens))
    names = []
    for _ in range(nfeat):
        assert next(tokens) == "feat"; names.append(next(tokens))
    assert next(tokens) == "logistic"; logistic = int(next(tokens))
    assert next(tokens) == "base_score"; base = float(next(tokens))
    assert next(tokens) == "ntrees"; ntrees = int(next(tokens))
    margin = math.log(base / (1 - base)) if logistic else base
    for expected_tree in range(ntrees):
        assert next(tokens) == "tree" and int(next(tokens)) == expected_tree
        count = int(next(tokens)); nodes = []
        for _ in range(count):
            tag = next(tokens)
            if tag == "L": nodes.append(("L", float(next(tokens))))
            else: nodes.append(("S", int(next(tokens)), float(next(tokens)), int(next(tokens)), int(next(tokens))))
        node = 0
        while nodes[node][0] == "S":
            _, feat, threshold, yes, no = nodes[node]
            node = yes if row[feat] < threshold else no
        margin += nodes[node][1]
    return 1 / (1 + math.exp(-margin)) if logistic else margin, ntrees, names


rng = np.random.default_rng(7)
x = rng.normal(size=(32, 2)).astype(np.float32)
y = (x[:, 0] + .4 * x[:, 1] > 0).astype(np.float32)
d = xgb.DMatrix(x, label=y, feature_names=["curHp", "room_type"])
booster = xgb.train({"objective": "binary:logistic", "max_depth": 2, "eta": .4,
                     "seed": 3, "tree_method": "hist"}, d, num_boost_round=3)
with tempfile.TemporaryDirectory() as tmp:
    output = os.path.join(tmp, "model.txt")
    info = export_booster(booster, output, tree_count=2)
    assert info["tree_count"] == 2 and info["logistic"]
    native, ntrees, names = compact_predict(output, x[0])
    expected = float(booster.predict(d, iteration_range=(0, 2))[0])
    assert ntrees == 2 and names == ["curHp", "room_type"]
    assert abs(native - expected) < 1e-6, (native, expected)
    try: export_booster(booster, output, tree_count=4)
    except ValueError: pass
    else: raise AssertionError("out-of-range truncation accepted")
print("compact export self-test: PASS")
