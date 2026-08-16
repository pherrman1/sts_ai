#!/usr/bin/env python3
"""Focused tests for the pure-analysis helpers in train_postcombat_runwin."""
import importlib.util
import pathlib

import numpy as np

path = pathlib.Path(__file__).with_name("train_postcombat_runwin.py")
spec = importlib.util.spec_from_file_location("postcombat", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

y = np.array([0, 1, 0, 1, 1, 0], dtype=float)
p = np.array([.1, .8, .2, .7, .6, .3])
assert 0 <= mod.ece(y, p) <= 1
assert mod.metrics(y, p)["logloss"] < 1
assert len(mod.calibration(y, p)) == 10

seeds = np.array([10, 10, 20, 20, 30, 30])
tr, va = mod.grouped_split(seeds)
assert not set(seeds[tr]) & set(seeds[va])

run = np.array([0, 0, 1, 1, 2, 2])
d1 = mod.bootstrap_deltas(y, p, np.full(6, .5), run, n=20, seed=7)
d2 = mod.bootstrap_deltas(y, p, np.full(6, .5), run, n=20, seed=7)
assert d1 == d2
assert set(d1) == {"logloss", "brier", "auc"}
print("postcombat run-win selftest: PASS")