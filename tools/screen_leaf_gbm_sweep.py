#!/usr/bin/env python3
"""Label/parameter sweep for the GBM screen leaf residual (VALIDATION only).

Every variant trains on TRAIN with X2-B's decision-state margin as
base_margin and is scored by NLL against the real win outcome on VALIDATION
(the leaf's job), overall and by screen. Labels: the outcome (won), the
next-MAP X2-B value (TD), or a mix. TEST is never read.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import numpy as np
from screen_leaf_gbm import SCREENS, NAMES, x2b_margin, nll
import screen_leaf_data_379 as data379

BASE = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'device': 'cpu', 'nthread': 6,
        'max_depth': 6, 'eta': 0.03, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 50,
        'lambda': 5.0, 'seed': 379}


def main():
    import xgboost as xgb
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--variants', type=Path, required=True)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    names = list(data379.DecisionCorpus().feature_names) + NAMES
    x = np.load(a.cache_root / 'TRAIN.x.npy', mmap_mode='r'); t = np.load(a.cache_root / 'TRAIN.npz')
    vx = np.load(a.cache_root / 'VALIDATION.x.npy', mmap_mode='r'); v = np.load(a.cache_root / 'VALIDATION.npz')
    td, vtd = np.load(a.cache_root / 'TRAIN.td.npz')['target'], np.load(a.cache_root / 'VALIDATION.td.npz')['target']
    y, vy, vs = t['y'], v['y'], v['screen']
    m, vm = x2b_margin(np.asarray(x[:, :461])), x2b_margin(np.asarray(vx[:, :461]))
    base = nll(vy, 1 / (1 + np.exp(-vm)))
    results = {'x2b': {'nll': float(base.mean()), 'by_screen': {s: float(base[vs == i].mean()) for i, s in enumerate(SCREENS)}}}
    dval = None
    for variant in json.loads(a.variants.read_text()):
        name, lam = variant['name'], variant['label_weight']
        label = (lam * y + (1 - lam) * td).astype(np.float32)
        params = dict(BASE, **variant.get('params', {}))
        start = time.monotonic(); preds = []
        for seed in variant.get('seeds', [379]):
            params['seed'] = seed
            dtrain = xgb.QuantileDMatrix(np.asarray(x), label, base_margin=m, feature_names=names, max_bin=256)
            # Early stopping always on the outcome label: that is what the leaf must predict.
            dval = xgb.QuantileDMatrix(np.asarray(vx), vy, base_margin=vm, feature_names=names, ref=dtrain, max_bin=256)
            booster = xgb.train(params, dtrain, num_boost_round=4000, evals=[(dval, 'validation')],
                                early_stopping_rounds=100, verbose_eval=False)
            booster.save_model(a.output / f'{name}-seed{seed}.ubj')
            preds.append(booster.predict(dval, iteration_range=(0, booster.best_iteration + 1), output_margin=True))
            del dtrain
        p = 1 / (1 + np.exp(-np.mean(preds, axis=0)))
        loss = nll(vy, p)
        results[name] = {'label_weight': lam, 'params': variant.get('params', {}), 'seeds': variant.get('seeds', [379]),
                         'best_iterations': None, 'nll': float(loss.mean()), 'delta_vs_x2b': float(loss.mean() - base.mean()),
                         'by_screen': {s: float(loss[vs == i].mean()) for i, s in enumerate(SCREENS)},
                         'wall_seconds': time.monotonic() - start}
        print(json.dumps({name: results[name]['nll']}), flush=True)
        (a.output / 'results.json').write_text(json.dumps(results, indent=1) + '\n')


if __name__ == '__main__':
    main()
