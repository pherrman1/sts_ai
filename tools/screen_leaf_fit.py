#!/usr/bin/env python3
"""Deck-fit screen features for the GBM screen leaf (offline check).

Adds, on top of tools/screen_leaf_gbm.py: the full 1,017 rich run features
(all 372 per-card deck counts, instead of X2-B's 461 selection) and computed
deck-relative features of what is offered (copies already held, type/rarity/
cost of offered cards vs the deck). Trains the same X2-B-margin residual and
reports VALIDATION NLL against the outcome. TEST is never read.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import numpy as np
import screen_leaf_data_379 as data379
from screen_leaf_gbm import SCREENS, NAMES as SF_NAMES, screen_features, x2b_margin, nll

csv.field_size_limit(10**9)
CARDS = {row[0]: row for row in json.loads((ROOT / 'tools/data/card_meta.json').read_text())}  # id,type,rarity,color,cost,costUp
ATTACK, SKILL, POWER, STATUS, CURSE = 0, 1, 2, 4, 3
FIT = ['fit_n', 'fit_held_sum', 'fit_held_max', 'fit_held_mean', 'fit_new', 'fit_attack', 'fit_skill', 'fit_power',
       'fit_curse', 'fit_common', 'fit_uncommon', 'fit_rare', 'fit_cost_min', 'fit_cost_mean', 'fit_cost_max',
       'fit_upgraded', 'fit_attack_share_minus_deck', 'fit_power_share_minus_deck', 'fit_cost_mean_minus_deck',
       'deck_size', 'deck_attack', 'deck_skill', 'deck_power', 'deck_curse', 'deck_status', 'deck_basic',
       'deck_distinct', 'deck_upgraded', 'deck_cost_mean', 'deck_attack_share', 'fit_basic', 'fit_gold_after_min']
COUNTS = {split: n for split, n in (('TRAIN', 1509014), ('VALIDATION', 329425))}


def offered_cards(c):
    s = c['screen']
    if s == 'shop': return [(i['card']['id'], i['card']['upgraded']) for i in c['cards'] if i['price'] >= 0]
    if s == 'rewards': return [(x['id'], x['upgraded']) for g in c['cardRewards'] for x in g['cards']]
    if s == 'selector': return [(i['card']['id'], i['card']['upgraded']) for i in c['cards']]
    return []


_META = None


def _meta(names_index):
    global _META
    if _META is None:
        ids = [i for i in range(372) if f'd{i}' in names_index]
        d_idx = np.asarray([names_index[f'd{i}'] for i in ids]); u_idx = np.asarray([names_index[f'u{i}'] for i in ids if f'u{i}' in names_index])
        typ = np.asarray([CARDS[i][1] if i in CARDS else -1 for i in ids]); rar = np.asarray([CARDS[i][2] if i in CARDS else -1 for i in ids])
        cost = np.asarray([CARDS[i][4] if i in CARDS else -1 for i in ids], dtype=np.float64)
        _META = (np.asarray(ids), d_idx, u_idx, typ, rar, cost)
    return _META


def fit_features(c, rich, names_index, gold, price_min):
    f = np.zeros(len(FIT), dtype=np.float32)
    ids, d_idx, u_idx, typ, rar, cost = _meta(names_index)
    counts = rich[d_idx].astype(np.float64)
    deck = dict(zip(ids.tolist(), counts.tolist()))
    size = counts.sum()
    by_type = {t: counts[typ == t].sum() for t in (ATTACK, SKILL, POWER, CURSE, STATUS)}
    valid = cost >= 0
    deck_cost_mean = float((counts[valid] * cost[valid]).sum() / counts[valid].sum()) if counts[valid].sum() else 0.
    deck_attack_share = by_type[ATTACK] / size if size else 0.
    vals = dict(deck_size=size, deck_attack=by_type[ATTACK], deck_skill=by_type[SKILL], deck_power=by_type[POWER],
                deck_curse=by_type[CURSE], deck_status=by_type[STATUS], deck_basic=counts[rar == 3].sum(),
                deck_distinct=float((counts > 0).sum()), deck_upgraded=float(rich[u_idx].sum()), deck_cost_mean=deck_cost_mean,
                deck_attack_share=deck_attack_share)
    offers = offered_cards(c)
    if offers:
        held = [deck.get(i, 0.) for i, _ in offers]
        meta = [CARDS[i] for i, _ in offers]
        costs = [m[5] if up else m[4] for m, (_, up) in zip(meta, offers) if (m[5] if up else m[4]) >= 0]
        n = len(offers)
        vals.update(fit_n=n, fit_held_sum=sum(held), fit_held_max=max(held), fit_held_mean=sum(held) / n,
                    fit_new=sum(h == 0 for h in held), fit_attack=sum(m[1] == ATTACK for m in meta),
                    fit_skill=sum(m[1] == SKILL for m in meta), fit_power=sum(m[1] == POWER for m in meta),
                    fit_curse=sum(m[1] in (CURSE, STATUS) for m in meta), fit_common=sum(m[2] == 0 for m in meta),
                    fit_uncommon=sum(m[2] == 1 for m in meta), fit_rare=sum(m[2] == 2 for m in meta),
                    fit_basic=sum(m[2] == 3 for m in meta), fit_upgraded=sum(bool(up) for _, up in offers))
        if costs:
            vals.update(fit_cost_min=min(costs), fit_cost_mean=sum(costs) / len(costs), fit_cost_max=max(costs),
                        fit_cost_mean_minus_deck=sum(costs) / len(costs) - deck_cost_mean)
        vals['fit_attack_share_minus_deck'] = vals['fit_attack'] / n - deck_attack_share
        vals['fit_power_share_minus_deck'] = vals['fit_power'] / n - (by_type[POWER] / size if size else 0.)
    if price_min > 0: vals['fit_gold_after_min'] = gold - price_min
    for k, v in vals.items(): f[FIT.index(k)] = v
    return f


def build(split, out):
    corpus = data379.DecisionCorpus()
    first = json.loads(Path(corpus.components[0]['manifest']).read_text())['stateFeatures']['header'].split(',')
    names_index = {n: i for i, n in enumerate(first)}
    gold_i, sel = names_index['gold'], [names_index[n] for n in corpus.feature_names]
    width = 1017 + len(SF_NAMES) + len(FIT)
    x = np.lib.format.open_memmap(out.with_suffix('.x.npy'), mode='w+', dtype=np.float32, shape=(COUNTS[split], width))
    y = np.empty(COUNTS[split], np.float32); screen = np.empty(COUNTS[split], np.int64); n = 0
    pmin = 461 + SF_NAMES.index('sf_price_min') - 461
    for comp in [c for c in corpus.components if c['split'] == split]:
        table = Path(str(comp['manifest']).removesuffix('.manifest.json') + '.decision.csv')
        with table.open(newline='') as stream:
            reader = csv.reader(stream); header = next(reader)
            if header[9:9 + 1017] != first: raise ValueError('rich header differs across components')
            for raw in reader:
                rich = np.asarray(raw[9:9 + 1017], dtype=np.float32)
                c, keys = json.loads(raw[-3]), json.loads(raw[-2])['optionKeys']
                sf = screen_features(c, keys, rich[gold_i])
                x[n, :1017] = rich; x[n, 1017:1017 + len(SF_NAMES)] = sf
                x[n, 1017 + len(SF_NAMES):] = fit_features(c, rich, names_index, rich[gold_i], sf[pmin])
                y[n] = float(raw[-1]); screen[n] = SCREENS.index(raw[7]); n += 1
    if n != COUNTS[split]: raise ValueError('row count differs')
    x.flush(); np.savez(out, y=y, screen=screen, sel=np.asarray(sel))
    return first


def train(cache, output, drop_card_flags):
    import xgboost as xgb
    output.mkdir(parents=True, exist_ok=False)
    corpus = data379.DecisionCorpus()
    first = json.loads(Path(corpus.components[0]['manifest']).read_text())['stateFeatures']['header'].split(',')
    names = first + SF_NAMES + FIT
    keep = [i for i, n in enumerate(names) if not (drop_card_flags and n.startswith('sf_card'))]
    x = np.load(cache / 'TRAIN.x.npy', mmap_mode='r'); t = np.load(cache / 'TRAIN.npz')
    vx = np.load(cache / 'VALIDATION.x.npy', mmap_mode='r'); v = np.load(cache / 'VALIDATION.npz')
    sel = t['sel']
    m, vm = x2b_margin(np.asarray(x[:, sel])), x2b_margin(np.asarray(vx[:, sel]))
    params = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'device': 'cpu', 'nthread': 6,
              'max_depth': 6, 'eta': 0.03, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 50,
              'lambda': 5.0, 'seed': 379}
    kn = [names[i] for i in keep]
    full = len(keep) == len(names)  # avoid copying the ~10 GB TRAIN matrix when no column is dropped
    dtrain = xgb.QuantileDMatrix(x if full else np.asarray(x[:, keep]), t['y'], base_margin=m, feature_names=kn, max_bin=256)
    dval = xgb.QuantileDMatrix(vx if full else np.asarray(vx[:, keep]), v['y'], base_margin=vm, feature_names=kn, ref=dtrain, max_bin=256)
    start = time.monotonic()
    b = xgb.train(params, dtrain, num_boost_round=4000, evals=[(dval, 'validation')], early_stopping_rounds=100, verbose_eval=100)
    b.save_model(output / 'residual.ubj')
    p = b.predict(dval, iteration_range=(0, b.best_iteration + 1))
    loss, vs = nll(v['y'], p), v['screen']
    gain = b.get_score(importance_type='total_gain')
    report = {'nll': float(loss.mean()), 'best_iteration': b.best_iteration, 'drop_card_flags': drop_card_flags,
              'by_screen': {s: float(loss[vs == i].mean()) for i, s in enumerate(SCREENS)},
              'top_gain': sorted(gain.items(), key=lambda kv: -kv[1])[:25], 'wall_seconds': time.monotonic() - start}
    (output / 'result.json').write_text(json.dumps(report, indent=1) + '\n'); print(json.dumps(report, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('--cache', type=Path, required=True)
    t = sub.add_parser('train'); t.add_argument('--cache', type=Path, required=True); t.add_argument('--output', type=Path, required=True)
    t.add_argument('--drop-card-flags', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'build':
        a.cache.mkdir(parents=True, exist_ok=True)
        for split in ('TRAIN', 'VALIDATION'): build(split, a.cache / f'{split}.npz'); print(split, 'built', flush=True)
    else:
        train(a.cache, a.output, a.drop_card_flags)
