#!/usr/bin/env python3
"""Analysis of the CRN act-end price pilot (docs/experiments/evidence/crn_act_price_pilot_20261021/PREREG.md).

  python3 tools/analyze_crn_act_price_pilot.py OUT.json PILOT_DIR [--compare REF_DIR]

PILOT_DIR / REF_DIR: extracted worker tars (searched recursively for s<seed>.csv with a matching s<seed>.done).
REF_DIR is the §537 3-fight campaign, read the same way for the noise comparison (metric 1).
A seed whose .done has rc != 0 is dropped and reported. States whose base copy is invalid or starts at 0 HP are
dropped (terminal source states). Seed bootstrap, 2,000 replicates, RNG 20261021.
"""
import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

import numpy as np

FAIRY = 'FAIRY_POTION'
BUDGET_CORE_H = 800.0
TARGET_HALF_WIDTH = 3.0   # HP-eq
N_BOOT, RNG = 2000, 20261021


def load(root):
    rows, dropped = [], []
    for path in sorted(glob.glob(f'{root}/**/s*.csv', recursive=True)):
        done = path[:-4] + '.done'
        if not os.path.exists(done):
            continue
        rc = int(re.search(r'rc=(-?\d+)', open(done).read()).group(1))
        seed = int(os.path.basename(path)[1:-4])
        if rc != 0:
            dropped.append({'seed': seed, 'rc': rc})
            continue
        rows += list(csv.DictReader(open(path)))
    states = defaultdict(dict)
    for r in rows:
        states[(int(r['seed']), int(r['battleIdx']))][r['variant']] = r
    out = []
    for (seed, idx), v in states.items():
        b = v.get('base')
        if not b or b['valid'] != '1' or int(b['curHp']) <= 0:
            continue
        out.append({'seed': seed, 'act': int(b['act']), 'v': v})
    return out, dropped, len(rows)


def delta(state, name, key='altFloor'):
    """Paired difference copy - base (positive = copy better)."""
    c = state['v'].get(name)
    if not c or c['valid'] != '1':
        return None
    return float(c[key]) - float(state['v']['base'][key])


def pairs(states, kind):
    """(seed, act, delta) for one copy kind: 'hp:-12', 'gold:-50', 'maxhp:-5', 'pot' (non-Fairy), 'fairy'."""
    out = []
    for s in states:
        for name in s['v']:
            if kind == 'pot' and not (name.startswith('pot:') and name != 'pot:' + FAIRY):
                continue
            if kind == 'fairy' and name != 'pot:' + FAIRY:
                continue
            if kind not in ('pot', 'fairy') and name != kind:
                continue
            d = delta(s, name)
            if d is not None:
                out.append((s['seed'], s['act'], d))
    return out


def noise(states):
    rep = {}
    for kind in ('hp:-12', 'pot', 'gold:-50', 'maxhp:-5'):
        d = np.array([x[2] for x in pairs(states, kind)])
        if len(d):
            rep[kind] = {'n': int(len(d)), 'mean': float(d.mean()), 'sd': float(d.std(ddof=1)) if len(d) > 1 else None,
                         'identicalShare': float(np.mean(np.abs(d) < 1e-9))}
    return rep


def ratio_price(states, kind, per, rng, acts=None):
    """HP-eq price = mean(-Δ copy) / per / (mean(-Δ hp:-12) / 12), seed bootstrap; returns estimate, CI, n."""
    sel = [s for s in states if acts is None or s['act'] in acts]
    num = pairs(sel, kind)
    den = pairs(sel, 'hp:-12')
    if not num or not den:
        return None
    seeds = sorted({s['seed'] for s in sel})
    by_num, by_den = defaultdict(list), defaultdict(list)
    for sd, _, d in num:
        by_num[sd].append(-d)
    for sd, _, d in den:
        by_den[sd].append(-d)

    def est(sample):
        a = [x for sd in sample for x in by_num.get(sd, [])]
        b = [x for sd in sample for x in by_den.get(sd, [])]
        if not a or not b or np.mean(b) <= 0:
            return math.nan
        return np.mean(a) / per / (np.mean(b) / 12)
    point = est(seeds)
    boot = np.array([est(list(rng.choice(seeds, len(seeds)))) for _ in range(N_BOOT)])
    boot = boot[np.isfinite(boot)]
    ci = [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))] if len(boot) else [math.nan] * 2
    return {'hpEq': float(point), 'ci95': ci, 'pairs': len(num), 'seeds': len(seeds),
            'bootValid': int(len(boot))}


def hp_slope(states, rng):
    seeds = sorted({s['seed'] for s in states})
    by = defaultdict(list)
    for sd, _, d in pairs(states, 'hp:-12'):
        by[sd].append(-d / 12)
    est = lambda sample: np.mean([x for sd in sample for x in by.get(sd, [])] or [math.nan])
    boot = np.array([est(list(rng.choice(seeds, len(seeds)))) for _ in range(N_BOOT)])
    boot = boot[np.isfinite(boot)]
    return {'floorsPerHp': float(est(seeds)), 'ci95': [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
            'pairs': sum(len(v) for v in by.values())}


def cost(states):
    per_state = [sum(float(c['cpuMs']) for c in s['v'].values()) / 3.6e6 for s in states]
    per_cont = [float(c['cpuMs']) / 1000 for s in states for c in s['v'].values()]
    return {'coreHoursPerState': float(np.mean(per_state)), 'cpuSecondsPerContinuation': float(np.mean(per_cont))}


def main(out, pilot, compare=None):
    rng = np.random.default_rng(RNG)
    states, dropped, nrows = load(pilot)
    rep = {'rows': nrows, 'states': len(states), 'seeds': len({s['seed'] for s in states}), 'droppedSeeds': dropped,
           'statesByAct': {a: sum(s['act'] == a for s in states) for a in (1, 2, 3)}}
    rep['noise'] = noise(states)                                                            # metric 1
    rep['hpSlope'] = hp_slope(states, rng)                                                  # metric 2
    rep['prices'] = {k: ratio_price(states, kind, per, rng) for k, kind, per in            # metric 3
                     (('potionNonFairy', 'pot', 1), ('fairy', 'fairy', 1), ('maxHpPerPoint', 'maxhp:-5', 5),
                      ('goldPerGold', 'gold:-50', 50))}
    rep['cost'] = cost(states)
    proj = {}                                                                               # metric 4
    for act in (1, 2, 3):
        p = ratio_price(states, 'pot', 1, rng, acts={act})
        sub = [s for s in states if s['act'] == act]
        if not p or not math.isfinite(p['ci95'][0]):
            proj[act] = None
            continue
        hw = (p['ci95'][1] - p['ci95'][0]) / 2
        n_star = len(sub) * (hw / TARGET_HALF_WIDTH) ** 2
        proj[act] = {'statesNow': len(sub), 'halfWidthNow': hw, 'statesNeeded': n_star,
                     'coreHours': n_star * cost(sub)['coreHoursPerState']}
    rep['projection'] = proj
    total = sum(v['coreHours'] for v in proj.values() if v)
    rep['projectedCampaignCoreHours'] = total
    slope_ok = rep['hpSlope']['ci95'][0] > 0
    rep['decision'] = ('GO' if slope_ok and all(proj.values()) and total <= BUDGET_CORE_H else 'STOP')
    if compare:
        ref, _, _ = load(compare)
        rep['compare3Fight'] = {'states': len(ref), 'noise': noise(ref), 'hpSlope': hp_slope(ref, rng)}
    json.dump(rep, open(out, 'w'), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    args = sys.argv[1:]
    ref = None
    if '--compare' in args:
        i = args.index('--compare')
        ref = args[i + 1]
        del args[i:i + 2]
    main(*args, compare=ref)
