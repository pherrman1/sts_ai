#!/usr/bin/env python3
"""Finite-difference end-state prices of a heart1-format value head on post-combat REWARDS states.

prices.py build <round2 extracted root> <out records.jsonl> <out meta.json> [max states]
prices.py analyze <meta.json> <scores.jsonl> <out.json>
"""
import copy
import glob
import json
import random
import sys

import numpy as np

EMPTY, PARASITE, STRIKE = 1, 243, 321
FAIRY, SMOKE = 21, 37


def perturbations(rec):
    fo = rec['obs.fixed_observation']
    hp, mhp, gold = fo[0], fo[1], fo[2]
    out = [('base', None)]
    for d in (1, 3, 6, 12, 24):
        if hp - d >= 1:
            out.append((f'hp-{d}', ('hp', -d)))
    if hp + 6 <= mhp:
        out.append(('hp+6', ('hp', 6)))
    for d in (-5, 5):
        if mhp + d >= hp:
            out.append((f'mhp{d:+d}', ('mhp', d)))
    for d in (-50, 50):
        if gold + d >= 0:
            out.append((f'gold{d:+d}', ('gold', d)))
    for i, p in enumerate(rec['obs.potions']):
        if p != EMPTY:
            out.append((f'pot-{i}', ('potdel', i)))
    out.append(('parasite', ('card', PARASITE)))
    if STRIKE in rec['obs.deck.cards']:
        out.append(('strike-removed', ('cardrm', STRIKE)))
    return out


def apply(rec, op):
    r = copy.deepcopy(rec)
    if op is None:
        return r
    kind, v = op
    fo = r['obs.fixed_observation']
    if kind == 'hp':
        fo[0] += v
    elif kind == 'mhp':
        fo[1] += v
    elif kind == 'gold':
        fo[2] += v
    elif kind == 'potdel':
        r['obs.potions'][v] = EMPTY
    elif kind == 'card':
        r['obs.deck.cards'].append(v)
        r['obs.deck.upgrades'].append(0)
        if 'obs.deck.misc' in r:
            r['obs.deck.misc'].append(0)
    elif kind == 'cardrm':
        i = r['obs.deck.cards'].index(v)
        for k in ('obs.deck.cards', 'obs.deck.upgrades', 'obs.deck.misc'):
            if k in r:
                del r[k][i]
    return r


def build(root, out_records, out_meta, max_states=4000):
    seen, states = set(), []
    for path in sorted(glob.glob(f'{root}/*/train/seed-*.sib.jsonl')):
        seed = int(path.split('seed-')[-1].split('.')[0])
        last = json.loads(open(path.replace('.sib.jsonl', '.states.jsonl')).readlines()[-1])
        if not last.get('complete'):
            continue
        heart = int(bool(last.get('heartKilled')))
        for raw in map(json.loads, open(path)):
            rec = raw['extra'].get('record')
            # post-combat states: REWARDS screen, acts 1-3
            if not rec or rec['screen_state'] != 2 or raw['act'] not in (1, 2, 3):
                continue
            key = (seed, raw['floor'])
            if key in seen:
                continue
            seen.add(key)
            states.append((seed, raw['act'], raw['floor'], heart, {**rec, 'obs.act': raw['act']}))
    random.Random(20261021).shuffle(states)
    states = states[:max_states]
    meta = []
    with open(out_records, 'w') as f:
        for seed, act, floor, heart, rec in states:
            for name, op in perturbations(rec):
                f.write(json.dumps(apply(rec, op)) + '\n')
                fo = rec['obs.fixed_observation']
                meta.append({'seed': seed, 'act': act, 'floor': floor, 'heart': heart, 'pert': name,
                             'hp': fo[0], 'mhp': fo[1], 'gold': fo[2],
                             'potion': rec['obs.potions'][int(name[4:])] if name.startswith('pot-') else None})
    json.dump(meta, open(out_meta, 'w'))
    print(len(states), 'states', len(meta), 'records')


def q(a):
    a = np.asarray(a, float)
    return {'n': int(len(a)), 'mean': float(a.mean()), 'p10': float(np.quantile(a, .1)),
            'p50': float(np.median(a)), 'p90': float(np.quantile(a, .9))}


def analyze(meta_path, scores_path, out):
    meta = json.load(open(meta_path))
    logits = [json.loads(l)['value'] for l in open(scores_path)]
    assert len(logits) == len(meta)
    states = {}
    for m, z in zip(meta, logits):
        s = states.setdefault((m['seed'], m['floor']), {'m': m, 'v': {}})
        s['v'][m['pert']] = 1 / (1 + np.exp(-z))
        if m['potion'] is not None:
            s.setdefault('pot', {})[m['pert']] = m['potion']
    rep = {'states': len(states)}
    # HP: per-HP slopes at several distances, monotonicity, noise of small steps
    slope = {}
    for d in (1, 3, 6, 12, 24):
        slope[d] = [(s['v']['base'] - s['v'][f'hp-{d}']) / d for s in states.values() if f'hp-{d}' in s['v']]
    rep['hpSlopePerHp'] = {str(d): q(v) for d, v in slope.items()}
    rep['fracHpLossLowersValue'] = {str(d): float(np.mean(np.array(v) > 0)) for d, v in slope.items()}
    ref = {}  # per-state HP slope used to convert to HP-equivalents (12-HP secant)
    for k, s in states.items():
        if 'hp-12' in s['v']:
            ref[k] = (s['v']['base'] - s['v']['hp-12']) / 12
    pos = {k: v for k, v in ref.items() if v > 1e-4}
    rep['statesWithPositive12HpSlope'] = [len(pos), len(ref)]
    mono = [s['v']['base'] >= s['v']['hp-6'] >= s['v']['hp-12'] >= s['v']['hp-24']
            for s in states.values() if 'hp-24' in s['v']]
    rep['fracMonotoneHp0_6_12_24'] = float(np.mean(mono))
    # value-scale differences: what a 1-HP and a potion difference look like next to the base value
    rep['baseValue'] = q([s['v']['base'] for s in states.values()])

    def hpeq(name, sign=1, per=1):
        vals = []
        for k, s in states.items():
            if k in pos and name in s['v']:
                vals.append(sign * (s['v']['base'] - s['v'][name]) / pos[k] / per)
        return vals
    rep['hpEq'] = {
        'potion (any, non-Fairy/Smoke)': q([x for k, s in states.items() if k in pos for p, pid in s.get('pot', {}).items()
                                            if pid not in (FAIRY, SMOKE)
                                            for x in [(s['v']['base'] - s['v'][p]) / pos[k]]]),
        'fairy': q([x for k, s in states.items() if k in pos for p, pid in s.get('pot', {}).items() if pid == FAIRY
                    for x in [(s['v']['base'] - s['v'][p]) / pos[k]]] or [np.nan]),
        'maxHpPerPoint(+5, hp fixed)': q([-x / 5 for x in hpeq('mhp+5')]),
        'goldPerGold(+50)': q([-x / 50 for x in hpeq('gold+50')]),
        'goldPerGold(-50)': q([x / 50 for x in hpeq('gold-50')]),
        'parasite': q([-x for x in hpeq('parasite')]),
        'strikeRemoved': q([-x for x in hpeq('strike-removed')]),
    }
    # context dependence: potion price by act and by "next boss" proximity
    by = {}
    for k, s in states.items():
        if k not in pos:
            continue
        for p, pid in s.get('pot', {}).items():
            if pid in (FAIRY, SMOKE):
                continue
            m = s['m']
            by.setdefault(f'act{m["act"]}', []).append((s['v']['base'] - s['v'][p]) / pos[k])
            by.setdefault('hpFrac<0.5' if m['hp'] < .5 * m['mhp'] else 'hpFrac>=0.5', []).append(
                (s['v']['base'] - s['v'][p]) / pos[k])
    rep['potionHpEqByContext'] = {b: q(v) for b, v in sorted(by.items())}
    sl = {}
    for k, v in ref.items():
        m = states[k]['m']
        sl.setdefault(f'act{m["act"]}', []).append(v)
        sl.setdefault('hpFrac<0.5' if m['hp'] < .5 * m['mhp'] else 'hpFrac>=0.5', []).append(v)
    rep['hp12SlopeByContext'] = {b: q(v) for b, v in sorted(sl.items())}
    json.dump(rep, open(out, 'w'), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    if sys.argv[1] == 'build':
        build(sys.argv[2], sys.argv[3], sys.argv[4], *(int(x) for x in sys.argv[5:]))
    else:
        analyze(*sys.argv[2:])
