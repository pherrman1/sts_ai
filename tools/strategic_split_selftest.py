#!/usr/bin/env python3
"""Regression test that the strategic split cannot leak a seed."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from strategic_split import seed_disjoint_split


seeds = np.repeat(np.arange(10), [1, 3, 2, 4, 1, 5, 2, 3, 1, 2])
rows, train, val = seed_disjoint_split(seeds, random_seed=0)
assert np.intersect1d(train, val).size == 0
assert set(seeds[rows]) == set(train)
assert set(seeds[~rows]) == set(val)
assert rows.sum() + (~rows).sum() == len(seeds)
print("strategic seed split self-test: PASS")
