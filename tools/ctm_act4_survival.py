#!/usr/bin/env python3
"""Act-4 survival model for the CTM (§TBD): death in SHIELD_AND_SPEAR / THE_HEART from the CTM predictor input.

  fit    ROWS.jsonl BASE.csv OUT_DIR   grid on VALIDATION, candidate on TRAIN, writes model.ubj + fit.json
  gate   ROWS.jsonl BASE.csv OUT_DIR   opens TEST once for the fitted candidate, writes gate.json
  export ROWS.jsonl OUT_DIR TREES.txt  CompactTreeNet text (x < thr -> yes) + parity.csv of TEST predictions

ROWS are combat_transition_row_v2 Act-4 rows; BASE is `one_combat ctmscorerows` of the same rows with the deployed
stack. The features mirror act4SurvivalFeatures in apps/one_combat/combat_transition_runtime.cpp; keep them in
lockstep. The pre-registration is docs/experiments/evidence/ctm_act4_survival_20261018/PREREG.md.
"""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

SHIELD_AND_SPEAR, THE_HEART = 56, 57
CARDS, RELICS, POTIONS = 400, 200, 50
SCALARS = ['heart', 'cur_hp', 'max_hp', 'hp_frac', 'gold', 'potion_capacity', 'potion_count', 'deck_size', 'upgraded']
NAMES = (SCALARS + [f'card_{i}' for i in range(CARDS)] + [f'relic_{i}' for i in range(RELICS)]
         + [f'potion_{i}' for i in range(POTIONS)])
SEED = 527


def split(seed):
    b = int.from_bytes(hashlib.sha256(f'combat-transition-model-v1:{int(seed)}'.encode()).digest()[:8], 'big') % 100
    return 'train' if b < 80 else 'validation' if b < 90 else 'test'


def features(p):
    g = p['globals']
    x = np.zeros(len(NAMES), dtype=np.float32)
    x[:len(SCALARS)] = [g['encounter'] == THE_HEART, g['curHp'], g['maxHp'],
                        np.float32(g['curHp']) / np.float32(g['maxHp']), g['gold'], g['potionCapacity'],
                        g['potionCount'], len(p['cards']), sum(c['upgraded'] for c in p['cards'])]
    base = len(SCALARS)
    for c in p['cards']:
        x[base + c['cardId']] += 1
    for r in p['relics']:
        x[base + CARDS + r['relicId']] = 1
    for q in p['potions']:
        if q['slot'] < g['potionCapacity'] and q['potionId'] > 1:  # 0 invalid, 1 empty slot
            x[base + CARDS + RELICS + q['potionId']] += 1
    return x


def load(rows_path, base_path=None):
    rows = [json.loads(line) for line in open(rows_path) if line.strip()]
    for r in rows:
        assert r['encounter'] in (SHIELD_AND_SPEAR, THE_HEART) and r['runValid'] and not r['quarantineReason']
    X = np.stack([features(r['predictorInput']) for r in rows])
    y = np.array([r['transition']['combatOutcome'] == 2 for r in rows], dtype=np.float32)
    d = {'X': X, 'y': y, 'enc': np.array([r['encounter'] for r in rows]),
         'seed': np.array([r['sourceSeed'] for r in rows]), 'split': np.array([split(r['sourceSeed']) for r in rows])}
    if base_path:
        base = list(csv.DictReader(open(base_path)))
        assert len(base) == len(rows)
        for b, r in zip(base, rows):
            assert int(b['source_seed']) == r['sourceSeed'] and int(b['encounter']) == r['encounter']
            assert b['scored'] == '1'
        d['base'] = np.array([float(b['p_death']) for b in base])
    return d


def bce(p, y):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def auc(p, y):
    order = np.argsort(p, kind='mergesort')
    ranks = np.empty(len(p))
    sp = p[order]
    i = 0
    while i < len(p):  # average ranks over ties
        j = i
        while j + 1 < len(p) and sp[j + 1] == sp[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def fit(rows_path, base_path, out):
    import xgboost as xgb
    d = load(rows_path, base_path)
    tr, va = d['split'] == 'train', d['split'] == 'validation'
    dtr = xgb.DMatrix(d['X'][tr], label=d['y'][tr], feature_names=NAMES)
    dva = xgb.DMatrix(d['X'][va], label=d['y'][va], feature_names=NAMES)
    cells = []
    for depth in (2, 3, 4):
        for mcw in (5, 20):
            params = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03,
                      'subsample': 0.8, 'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth,
                      'min_child_weight': mcw, 'seed': SEED, 'nthread': 4}
            bst = xgb.train(params, dtr, 3000, evals=[(dva, 'validation')], early_stopping_rounds=100,
                            verbose_eval=False)
            p = bst.predict(dva, iteration_range=(0, bst.best_iteration + 1))
            cell = {'max_depth': depth, 'min_child_weight': mcw, 'best_iteration': int(bst.best_iteration),
                    'validation_bce': float(bce(p, d['y'][va]).mean())}
            for enc, name in ((THE_HEART, 'heart'), (SHIELD_AND_SPEAR, 'shield_and_spear')):
                m = d['enc'][va] == enc
                cell[f'validation_bce_{name}'] = float(bce(p[m], d['y'][va][m]).mean())
                cell[f'validation_bce_{name}_incumbent'] = float(bce(d['base'][va][m], d['y'][va][m]).mean())
            print(json.dumps(cell))
            cells.append((cell, params, bst))
    cell, params, bst = min(cells, key=lambda c: c[0]['validation_bce'])
    out.mkdir(parents=True, exist_ok=True)
    bst.save_model(out / 'model.ubj')
    (out / 'fit.json').write_text(json.dumps({
        'rows_sha256': hashlib.sha256(Path(rows_path).read_bytes()).hexdigest(), 'xgboost': xgb.__version__,
        'numpy': np.__version__, 'counts': {s: int((d['split'] == s).sum()) for s in ('train', 'validation', 'test')},
        'grid': [c[0] for c in cells], 'selected': cell, 'params': params}, indent=1) + '\n')
    print('selected', json.dumps(cell))


def predict(d, out):
    import xgboost as xgb
    fitted = json.loads((out / 'fit.json').read_text())
    bst = xgb.Booster()
    bst.load_model(out / 'model.ubj')
    return bst.predict(xgb.DMatrix(d['X'], feature_names=NAMES),
                       iteration_range=(0, fitted['selected']['best_iteration'] + 1))


def hp_logistic(d, tr, enc):
    """Reported only: logistic regression on the HP scalars, per encounter, fit on TRAIN."""
    from sklearn.linear_model import LogisticRegression
    cols = [NAMES.index(n) for n in ('cur_hp', 'max_hp', 'hp_frac')]
    m = tr & (d['enc'] == enc)
    lr = LogisticRegression(C=1e6, max_iter=5000).fit(d['X'][m][:, cols], d['y'][m])
    return lambda X: lr.predict_proba(X[:, cols])[:, 1]


def gate(rows_path, base_path, out):
    d = load(rows_path, base_path)
    cand = predict(d, out)
    tr, te = d['split'] == 'train', d['split'] == 'test'
    rng = np.random.default_rng(SEED)
    result = {'criteria': {}, 'reported': {}}
    passed = True
    for enc, name in ((THE_HEART, 'heart'), (SHIELD_AND_SPEAR, 'shield_and_spear')):
        m = te & (d['enc'] == enc)
        y, pc, pb, seeds = d['y'][m], cand[m], d['base'][m], d['seed'][m]
        # One row per (seed, encounter): a source-seed cluster is a single row here.
        assert len(np.unique(seeds)) == len(seeds)
        dl = bce(pc, y) - bce(pb, y)
        boot_bce, boot_auc = [], []
        for _ in range(2000):
            i = rng.integers(0, len(y), len(y))
            boot_bce.append(dl[i].mean())
            boot_auc.append(auc(pc[i], y[i]) - auc(pb[i], y[i]) if 0 < y[i].sum() < len(i) else np.nan)
        lo_b, hi_b = np.percentile(boot_bce, [2.5, 97.5])
        lo_a, hi_a = np.nanpercentile(boot_auc, [2.5, 97.5])
        bias = float(pc.mean() - y.mean())
        c = {'n': int(m.sum()), 'observed_death': float(y.mean()), 'candidate_mean': float(pc.mean()),
             'incumbent_mean': float(pb.mean()), 'bce_candidate': float(bce(pc, y).mean()),
             'bce_incumbent': float(bce(pb, y).mean()), 'bce_delta': float(dl.mean()),
             'bce_delta_ci': [float(lo_b), float(hi_b)], 'c1_bce_pass': bool(hi_b < 0),
             'bias': bias, 'c2_bias_pass': bool(abs(bias) <= 0.05),
             'auc_candidate': float(auc(pc, y)), 'auc_incumbent': float(auc(pb, y)),
             'auc_delta': float(auc(pc, y) - auc(pb, y)), 'auc_delta_ci': [float(lo_a), float(hi_a)],
             'c3_auc_pass': bool(lo_a > -0.03)}
        passed &= c['c1_bce_pass'] and c['c2_bias_pass'] and c['c3_auc_pass']
        result['criteria'][name] = c
        rate = d['y'][tr & (d['enc'] == enc)].mean()
        hp = hp_logistic(d, tr, enc)(d['X'][m])
        frac = d['X'][m][:, NAMES.index('hp_frac')]
        buckets = {}
        for lo, hi in ((0, .3), (.3, .6), (.6, .9), (.9, 1.01)):
            b = (frac >= lo) & (frac < hi)
            if b.any():
                buckets[f'{lo}-{min(hi, 1)}'] = {'n': int(b.sum()), 'observed': float(y[b].mean()),
                                                 'candidate': float(pc[b].mean()), 'incumbent': float(pb[b].mean())}
        result['reported'][name] = {'bce_train_rate': float(bce(np.full(len(y), rate), y).mean()),
                                    'bce_hp_logistic': float(bce(hp, y).mean()),
                                    'auc_hp_logistic': float(auc(hp, y)), 'hp_buckets': buckets}
    result['verdict'] = 'PASS' if passed else 'FAIL'
    (out / 'gate.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result, indent=1))


def export(rows_path, out, trees_path):
    import xgboost as xgb
    fitted = json.loads((out / 'fit.json').read_text())
    best = fitted['selected']['best_iteration']
    bst = xgb.Booster()
    bst.load_model(out / 'model.ubj')
    bst.feature_names = NAMES
    dumps = bst.get_dump(dump_format='json')[:best + 1]
    used = sorted({n for t in dumps for n in re.findall(r'"split": "([^"]+)"', t)}, key=NAMES.index)
    base_score = float(json.loads(bst.save_config())['learner']['learner_model_param']['base_score'].strip('[]'))
    lines = [f'nfeat {len(used)}'] + [f'feat {n}' for n in used] + ['logistic 1', f'base_score {base_score!r}',
                                                                      f'ntrees {len(dumps)}']
    position = {n: i for i, n in enumerate(used)}
    for t, text in enumerate(dumps):
        order, queue = [], [json.loads(text)]
        while queue:  # breadth-first, so the last node is a leaf
            node = queue.pop(0)
            order.append(node)
            queue += node.get('children', [])
        index = {n['nodeid']: i for i, n in enumerate(order)}
        lines.append(f'tree {t} {len(order)}')
        for n in order:
            if 'leaf' in n:
                lines.append(f'L {n["leaf"]!r}')
            else:
                lines.append(f'S {position[n["split"]]} {float(n["split_condition"])!r} {index[n["yes"]]} '
                             f'{index[n["no"]]}')
    Path(trees_path).write_text('\n'.join(lines) + '\n')
    d = load(rows_path)
    p = predict(d, out)
    with open(out / 'parity.csv', 'w') as f:
        f.write('source_seed,encounter,p_death\n')
        for s, e, v in zip(d['seed'], d['enc'], p):
            f.write(f'{s},{e},{float(v)!r}\n')
    print(trees_path, len(dumps), 'trees', len(used), 'features', 'base_score', base_score)


if __name__ == '__main__':
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'fit':
        fit(args[0], args[1], Path(args[2]))
    elif cmd == 'gate':
        gate(args[0], args[1], Path(args[2]))
    elif cmd == 'export':
        export(args[0], Path(args[1]), args[2])
    else:
        sys.exit(__doc__)
