#!/usr/bin/env python3
"""Screen-aware OOC leaf as a gradient-boosted residual on X2-B.

value(state, screen) = sigmoid(logit(X2-B(state)) + residual(state, screen))

XGBoost is trained with X2-B's margin as base_margin, so it starts at X2-B
and only learns screen-dependent corrections. Inputs: the 461 X2-B run
features plus fixed-width public screen features (all seven DECISION screen
families). Trained on the frozen #334 TRAIN split, early-stopped on
VALIDATION; TEST is never read. Exported to the native CompactTreeNet text
format (non-logistic margin) for live OOC MCTS. Research only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import numpy as np
import screen_leaf_data_379 as data379

SCREENS = ('boss_relic', 'rest', 'shop', 'treasure', 'rewards', 'event', 'selector')
X2B_UBJ = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/model.ubj')
CARD_IDS, RELIC_IDS, POTION_IDS = range(372), range(178), range(44)  # trained vocabularies (Cards.h, Relics.h, Potions.h)
OOV_RELIC_IDS = range(178, 180)  # RelicId::CIRCLET, RED_CIRCLET: counted as offers, no one-hot slot
SCALAR = ['sf_screen', 'sf_nopt', 'sf_remove_cost', 'sf_price_min', 'sf_price_mean', 'sf_affordable',
          'sf_n_offers', 'sf_reward_gold', 'sf_n_card_groups', 'sf_emerald', 'sf_sapphire', 'sf_chest',
          'sf_event', 'sf_neow', 'sf_selector_type', 'sf_required', 'sf_completed', 'sf_n_selector_cards'] + \
         [f'sf_eff{e}' for e in range(30)]
NAMES = SCALAR + [f'sf_card{i}' for i in CARD_IDS] + [f'sf_relic{i}' for i in RELIC_IDS] + \
        [f'sf_potion{i}' for i in POTION_IDS]
INDEX = {n: i for i, n in enumerate(NAMES)}
EFFECT = re.compile(r'ooc:v1:effect=(\d+):')


def screen_features(c, keys, gold):
    """Fixed-width public screen summary. Mirrored by apps/one_combat/screen_leaf_gbm.cpp."""
    f = np.zeros(len(NAMES), dtype=np.float32)
    screen = c['screen']
    f[INDEX['sf_screen']] = SCREENS.index(screen)
    f[INDEX['sf_nopt']] = len(keys)
    for k in keys:
        f[INDEX[f'sf_eff{int(EFFECT.match(k)[1])}']] += 1
    prices = []

    def offer(kind, ident):
        # CIRCLET/RED_CIRCLET (178, 179) are outside the trained relic vocabulary.
        if kind != 'relic' or ident not in OOV_RELIC_IDS:
            f[INDEX[f'sf_{kind}{ident}']] += 1
        f[INDEX['sf_n_offers']] += 1

    if screen == 'shop':
        f[INDEX['sf_remove_cost']] = c['removeCost']
        for field, kind in (('cards', 'card'), ('relics', 'relic'), ('potionSlots', 'potion')):
            for item in c[field]:
                if item['price'] < 0: continue
                offer(kind, item['card']['id'] if kind == 'card' else item['id'])
                prices.append(item['price'])
    elif screen == 'boss_relic':
        for r in c['relics']: offer('relic', r)
    elif screen == 'rewards':
        f[INDEX['sf_reward_gold']] = sum(c['gold'])
        f[INDEX['sf_n_card_groups']] = len(c['cardRewards'])
        f[INDEX['sf_emerald']] = int(c['emeraldKey']); f[INDEX['sf_sapphire']] = int(c['sapphireKey'])
        for g in c['cardRewards']:
            for card in g['cards']: offer('card', card['id'])
        for r in c['relics']: offer('relic', r)
        for p in c['potions']: offer('potion', p)
    elif screen == 'treasure':
        f[INDEX['sf_chest']] = c['chestSize']
    elif screen == 'event':
        f[INDEX['sf_event']] = c['eventId']
        f[INDEX['sf_neow']] = len(c.get('neowOffers', []))
    elif screen == 'selector':
        f[INDEX['sf_selector_type']] = c['selectorTypeId']
        f[INDEX['sf_required']] = c['requiredPicks']; f[INDEX['sf_completed']] = c['completedPicks']
        f[INDEX['sf_n_selector_cards']] = len(c['cards'])
        for item in c['cards']: offer('card', item['card']['id'])
    if prices:
        f[INDEX['sf_price_min']] = min(prices); f[INDEX['sf_price_mean']] = sum(prices) / len(prices)
        f[INDEX['sf_affordable']] = sum(p <= gold for p in prices)
    return f


def rows(split):
    old = data379.PROVISIONAL_MASK
    data379.PROVISIONAL_MASK = SCREENS
    try:
        yield from data379.DecisionCorpus().iter_rows(split, screens=SCREENS)
    finally:
        data379.PROVISIONAL_MASK = old


def load(split, cache):
    if cache.exists():
        z = np.load(cache); return np.load(cache.with_suffix('.x.npy'), mmap_mode='r'), z['y'], z['screen'], z['source']
    names = data379.DecisionCorpus().feature_names
    gold = names.index('gold')
    count = {'TRAIN': 1509014, 'VALIDATION': 329425}[split]  # audited DECISION row totals
    x = np.empty((count, 461 + len(NAMES)), dtype=np.float32)
    y, screens, sources = np.empty(count, np.float32), np.empty(count, np.int64), np.empty(count, np.int64)
    n = 0
    for r in rows(split):
        base = np.asarray(r['base461'], dtype=np.float32)
        x[n, :461] = base; x[n, 461:] = screen_features(r['screenContents'], r['optionKeys'], base[gold])
        y[n] = r['label']; screens[n] = SCREENS.index(r['screen']); sources[n] = r['identity']['sourceSeed']; n += 1
    if n != count: raise ValueError('unexpected DECISION row count')
    np.save(cache.with_suffix('.x.npy'), x)
    np.savez(cache, y=y, screen=screens, source=sources)
    return x, y, screens, sources


def x2b_margin(x461):
    import xgboost as xgb
    b = xgb.Booster(); b.load_model(X2B_UBJ)
    return b.predict(xgb.DMatrix(x461, feature_names=data379.DecisionCorpus().feature_names), output_margin=True)


def nll(y, p):
    p = np.clip(p, 1e-7, 1 - 1e-7); return -(y * np.log(p) + (1 - y) * np.log1p(-p))


def train(output, cache_root, params):
    import xgboost as xgb
    output.mkdir(parents=True, exist_ok=False); cache_root.mkdir(parents=True, exist_ok=True)
    names = list(data379.DecisionCorpus().feature_names) + NAMES
    x, y, _, _ = load('TRAIN', cache_root / 'TRAIN.npz')
    vx, vy, vs, _ = load('VALIDATION', cache_root / 'VALIDATION.npz')
    m, vm = x2b_margin(x[:, :461]), x2b_margin(vx[:, :461])
    dtrain = xgb.QuantileDMatrix(x, y, base_margin=m, feature_names=names, max_bin=256)
    dval = xgb.QuantileDMatrix(vx, vy, base_margin=vm, feature_names=names, ref=dtrain, max_bin=256)
    start = time.monotonic()
    booster = xgb.train(params, dtrain, num_boost_round=3000, evals=[(dval, 'validation')],
                        early_stopping_rounds=100, verbose_eval=50)
    booster.save_model(output / 'residual.ubj')
    p = booster.predict(dval, iteration_range=(0, booster.best_iteration + 1))
    base = 1 / (1 + np.exp(-vm))
    a, b = nll(vy, base), nll(vy, p)
    report = {'params': params, 'best_iteration': booster.best_iteration, 'wall_seconds': time.monotonic() - start,
              'train_rows': len(y), 'validation_rows': len(vy),
              'x2b_nll': float(a.mean()), 'residual_nll': float(b.mean()),
              'by_screen': {s: {'rows': int((vs == i).sum()), 'x2b_nll': float(a[vs == i].mean()),
                                'residual_nll': float(b[vs == i].mean())} for i, s in enumerate(SCREENS)}}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report, indent=1))


def export(output, path, parity, parity_rows):
    """CompactTreeNet text: non-logistic margin trees (x < thr -> yes)."""
    import xgboost as xgb
    booster = xgb.Booster(); booster.load_model(output / 'residual.ubj')
    best = int(json.loads((output / 'result.json').read_text())['best_iteration'])
    names = list(data379.DecisionCorpus().feature_names) + NAMES
    booster.feature_names = names
    dumps = booster.get_dump(dump_format='json')[:best + 1]
    used = sorted({n for d in dumps for n in re.findall(r'"split": "([^"]+)"', d)}, key=names.index)
    lines = [f'nfeat {len(used)}'] + [f'feat {n}' for n in used] + ['logistic 0', 'base_score 0', f'ntrees {len(dumps)}']
    position = {n: i for i, n in enumerate(used)}
    for t, d in enumerate(dumps):
        tree = json.loads(d); order, queue = [], [tree]
        while queue:  # breadth-first, so the last node is always a leaf
            node = queue.pop(0); order.append(node); queue += node.get('children', [])
        index = {n['nodeid']: i for i, n in enumerate(order)}
        lines.append(f'tree {t} {len(order)}')
        for n in order:
            if 'leaf' in n: lines.append(f'L {n["leaf"]!r}')
            else:
                if n['missing'] != n['yes'] and n['missing'] != n['no']: raise ValueError('unexpected missing branch')
                lines.append(f'S {position[n["split"]]} {float(n["split_condition"])!r} {index[n["yes"]]} {index[n["no"]]}')
    path.write_text('\n'.join(lines) + '\n')
    vx, vy, vs, _ = load('VALIDATION', output.parent / 'cache' / 'VALIDATION.npz')
    rng = np.random.default_rng(379); pick = np.sort(rng.choice(len(vy), parity_rows, replace=False))
    # base_margin=0: with base_margin supplied, XGBoost ignores base_score, so the residual has no intercept.
    margin = booster.predict(xgb.DMatrix(vx[pick], feature_names=names, base_margin=np.zeros(len(pick))), output_margin=True,
                             iteration_range=(0, best + 1))
    with parity.open('w') as stream:
        for i, mg in zip(pick, margin): stream.write(json.dumps({'x': vx[i].tolist(), 'margin': float(mg)}) + '\n')
    print(path, len(dumps), 'trees', len(used), 'features')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train'); t.add_argument('--output', type=Path, required=True)
    t.add_argument('--cache-root', type=Path, required=True)
    e = sub.add_parser('export'); e.add_argument('--output', type=Path, required=True)
    e.add_argument('--model', type=Path, required=True); e.add_argument('--parity', type=Path, required=True)
    e.add_argument('--parity-rows', type=int, default=2048)
    a = ap.parse_args()
    if a.cmd == 'train':
        train(a.output.resolve(), a.cache_root.resolve(),
              {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'device': 'cuda',
               'max_depth': 6, 'eta': 0.03, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 50,
               'lambda': 5.0, 'seed': 379})
    else:
        export(a.output.resolve(), a.model.resolve(), a.parity.resolve(), a.parity_rows)
