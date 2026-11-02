#!/usr/bin/env python3
"""T1-T5 of README.md on heart1score output, per state set (postfight primary, heart secondary) and per room.
usage: gates.py <meta.json> <scores.jsonl> <§510 analysis.json> <out.json>
V = sigmoid(value) as prices.py (pre-registered); 'raw' repeats everything on the raw value as a robustness check
(heart1's value is a shaped return in about [0, 1], not a logit)."""
import json
import sys
from collections import defaultdict

import numpy as np

FAIRY, SMOKE = 21, 37
POTION_NAMES = ["INVALID", "EMPTY_POTION_SLOT", "AMBROSIA", "ANCIENT_POTION", "ATTACK_POTION", "BLESSING_OF_THE_FORGE",
                "BLOCK_POTION", "BLOOD_POTION", "BOTTLED_MIRACLE", "COLORLESS_POTION", "CULTIST_POTION", "CUNNING_POTION",
                "DEXTERITY_POTION", "DISTILLED_CHAOS", "DUPLICATION_POTION", "ELIXIR_POTION", "ENERGY_POTION",
                "ENTROPIC_BREW", "ESSENCE_OF_DARKNESS", "ESSENCE_OF_STEEL", "EXPLOSIVE_POTION", "FAIRY_POTION",
                "FEAR_POTION", "FIRE_POTION", "FLEX_POTION", "FOCUS_POTION", "FRUIT_JUICE", "GAMBLERS_BREW",
                "GHOST_IN_A_JAR", "HEART_OF_IRON", "LIQUID_BRONZE", "LIQUID_MEMORIES", "POISON_POTION",
                "POTION_OF_CAPACITY", "POWER_POTION", "REGEN_POTION", "SKILL_POTION", "SMOKE_BOMB", "SNECKO_OIL",
                "SPEED_POTION", "STANCE_POTION", "STRENGTH_POTION", "SWIFT_POTION", "WEAK_POTION"]


def q(a):
    a = np.asarray(a, float)
    if len(a) == 0:
        return {'n': 0}
    return {'n': int(len(a)), 'p10': float(np.quantile(a, .1)), 'p50': float(np.median(a)), 'p90': float(np.quantile(a, .9))}


def evaluate(states, ref510):
    r = {'states': len(states)}
    sec = {k: (s['v']['base'] - s['v']['hp-12']) / 12 for k, s in states.items() if 'hp-12' in s['v']}
    pos = {k: v for k, v in sec.items() if v > 1e-9}
    r['positive12HpSecant'] = [len(pos), len(sec)]
    for d in (1, 3, 6, 12, 24):
        x = [s['v']['base'] > s['v'][f'hp-{d}'] for s in states.values() if f'hp-{d}' in s['v']]
        r[f'hpMinus{d}LowersV'] = float(np.mean(x)) if x else None
    t1 = r['hpMinus3LowersV']
    mh = [s['v']['mhp+5'] > s['v']['base'] for s in states.values() if 'mhp+5' in s['v']]
    t2 = float(np.mean(mh))
    mhp_eq = [(s['v']['mhp+5'] - s['v']['base']) / pos[k] / 5 for k, s in states.items() if k in pos and 'mhp+5' in s['v']]
    pots = defaultdict(list)
    for k, s in states.items():
        if k in pos:
            for p, pid in s.get('pot', {}).items():
                pots[pid].append((s['v']['base'] - s['v'][p]) / pos[k])
    fairy = pots.get(FAIRY, [])
    t3 = float(np.median(fairy)) if fairy else None
    nonfairy = [x for pid, v in pots.items() if pid not in (FAIRY, SMOKE) for x in v]
    pairs = []
    for pid, v in sorted(pots.items()):
        name = POTION_NAMES[pid]
        ref = ref510.get(name)
        if ref and ref['n'] >= 100 and len(v) >= 30:
            pairs.append((name, float(np.median(v)), ref['hpEq'], len(v)))
    t4 = float(np.corrcoef([a for _, a, _, _ in pairs], [b for _, _, b, _ in pairs])[0, 1]) if len(pairs) >= 3 else None
    hp1 = [abs((s['v']['base'] - s['v']['hp-1']) / pos[k] - 1) for k, s in states.items() if k in pos and 'hp-1' in s['v']]
    t5 = float(np.median(hp1)) if hp1 else None
    r['hp1PriceInSecantUnits'] = q([(s['v']['base'] - s['v']['hp-1']) / pos[k] for k, s in states.items() if k in pos and 'hp-1' in s['v']])
    r['maxHpPerPointHpEq'] = q(mhp_eq)
    r['potionNonFairyHpEq'] = q(nonfairy)
    r['fairyHpEq'] = q(fairy)
    r['perType'] = [{'potion': n, 'heart1HpEq': a, 'sec510HpEq': b, 'n': c} for n, a, b, c in pairs]
    r['gates'] = {
        'T1_minus3HpLowersV>=0.95': [t1, t1 is not None and t1 >= 0.95],
        'T2_maxHp+5RaisesV>=0.90': [t2, t2 >= 0.90],
        'T3_fairyMedian>=30HP': [t3, t3 is not None and t3 >= 30],
        'T4_perTypeR>=0.5': [t4, t4 is not None and t4 >= 0.5],
        'T5_median|hp1-1|<=1/3': [t5, t5 is not None and t5 <= 1 / 3],
    }
    r['allPass'] = all(v[1] for v in r['gates'].values())
    return r


def main(meta_path, scores_path, ref_path, out):
    meta = json.load(open(meta_path))
    vals = [json.loads(l)['value'] for l in open(scores_path)]
    assert len(vals) == len(meta), (len(vals), len(meta))
    ref510 = json.load(open(ref_path))['altFloor']['potions']
    rep = {}
    for mode in ('sigmoid', 'raw'):
        groups = defaultdict(dict)
        for m, z in zip(meta, vals):
            v = 1 / (1 + np.exp(-z)) if mode == 'sigmoid' else z
            for g in (m['set'], f"{m['set']}:{m['room']}", f"{m['set']}:act{m['act']}"):
                s = groups[g].setdefault(m['seed'], {'v': {}})
                s['v'][m['pert']] = v
                if m['potion'] is not None:
                    s.setdefault('pot', {})[m['pert']] = m['potion']
        rep[mode] = {g: evaluate(st, ref510) for g, st in sorted(groups.items())}
    json.dump(rep, open(out, 'w'), indent=1)
    for g, r in rep['sigmoid'].items():
        print(g, r['states'], {k: (round(v[0], 3) if v[0] is not None else None, v[1]) for k, v in r['gates'].items()})


if __name__ == '__main__':
    main(*sys.argv[1:5])
