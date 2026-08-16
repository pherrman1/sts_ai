#!/usr/bin/env python3
"""Focused invariants for the E2b schema mask and matched bootstrap."""
import importlib.util
import pathlib

import numpy as np

path = pathlib.Path(__file__).with_name("analyze_postcombat_leaf_available.py")
spec = importlib.util.spec_from_file_location("e2b", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

header = ["seed", "curHp", "maxHp", "nextFight0", "gold", "r7", "pot3", "redKey", "d1", "fmDElite", "mystery", "won"]
rows = {r["feature"]: r for r in mod.manifest(header)}
assert rows["nextFight0"]["family"] == "hidden/future"
assert rows["fmDElite"]["family"] == "hidden/future"
assert rows["gold"]["family"] == "reward-mutated"
assert rows["r7"]["family"] == "reward-mutated"
assert rows["pot3"]["family"] == "reward-mutated"
assert rows["redKey"]["family"] == "fair+post-reward-stable"
assert rows["mystery"]["family"] == "ambiguous"
full, fair, masked = mod.feature_sets(header, set(header) - mod.LABELS - {"seed"})
assert set(fair) < set(full) and set(masked) < set(fair)
assert "mystery" not in masked and "nextFight0" not in fair and "gold" not in masked
seeds = np.array([10, 10, 20, 20, 30, 30])
tr, va = mod.grouped_split(seeds)
assert not set(seeds[tr]) & set(seeds[va])
y = np.array([0, 1, 0, 1, 1, 0], float)
p = np.array([.1, .8, .2, .7, .6, .3])
r = np.array([100, 100, 700, 700, 1200, 1200])
_, contiguous = np.unique(r, return_inverse=True)
expected = mod.bootstrap_pair(y, p, np.full(6, .5), np.array([0, 0, 1, 1, 2, 2]), n=20, seed=7)
assert mod.bootstrap_pair(y, p, np.full(6, .5), contiguous, n=20, seed=7) == expected
assert not (set(mod.LABELS) & set(masked))
print("postcombat leaf-available masked selftest: PASS")