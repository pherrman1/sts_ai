#!/usr/bin/env python3
"""Next-MAP X2-B targets for the GBM screen leaf (TD-style label).

For each DECISION row, the target is X2-B evaluated at the first recorded MAP
row in the same branch at or after the decision's floor. When the branch has
no later MAP row (death, or the Act-3 win), the target is the outcome label.
Row order matches tools/screen_leaf_gbm.py caches (DecisionCorpus order).
The join was checked against the exact replay links on VALIDATION.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import numpy as np
import screen_leaf_data_379 as data379
from screen_leaf_gbm import X2B_UBJ

csv.field_size_limit(10**9)


def targets(split, cache):
    import xgboost as xgb
    corpus = data379.DecisionCorpus()
    names = corpus.feature_names
    booster = xgb.Booster(); booster.load_model(X2B_UBJ)
    z = np.load(cache)
    sources, labels = z['source'], z['y']
    out = np.empty(len(labels), dtype=np.float32); kind = np.empty(len(labels), dtype=np.int8)
    n = 0
    for comp in [c for c in corpus.components if c['split'] == split]:
        base = str(comp['manifest']).removesuffix('.manifest.json')
        maps = defaultdict(list); feats = []
        with open(base + '.map.csv') as f:
            reader = csv.reader(f); header = next(reader)
            idx = None
            for row in reader:
                if idx is None:
                    # MAP prefix: sourceSeed, branchId, deviationIdx, rowIdx, act, floor, mapX, mapY, teacherId
                    rich_names = header[9:]
                    idx = [9 + rich_names.index(nm) for nm in names]
                maps[row[1]].append((int(row[5]), len(feats)))
                feats.append([float(row[i]) for i in idx])
        value = booster.predict(xgb.DMatrix(np.asarray(feats, np.float32), feature_names=names)) if feats else []
        for key in maps: maps[key].sort()
        with open(base + '.decision.csv') as f:
            reader = csv.reader(f); next(reader)
            for row in reader:
                if int(row[0]) != sources[n]: raise ValueError('row order differs from cache')
                floor = int(row[6])
                later = [i for fl, i in maps[row[1]] if fl >= floor]
                if later: out[n] = value[later[0]]; kind[n] = 0
                else: out[n] = labels[n]; kind[n] = 1
                n += 1
    if n != len(labels): raise ValueError('row count differs from cache')
    return out, kind


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache-root', type=Path, required=True)
    a = ap.parse_args()
    for split in ('TRAIN', 'VALIDATION'):
        t, k = targets(split, a.cache_root / f'{split}.npz')
        np.savez(a.cache_root / f'{split}.td.npz', target=t, terminal=k)
        print(json.dumps({'split': split, 'rows': len(t), 'terminal_fallback': int(k.sum()), 'mean_target': float(t.mean())}))
