#!/usr/bin/env python3
"""Value chooser A/B analysis (README.md, pre-registered). usage: analyze.py UNITS_DIR OUT_JSON
UNITS_DIR/<seed>/ holds A-<seed>.jsonl(.gz), B-<seed>.jsonl(.gz), B-<seed>.chooser.jsonl(.gz), games.txt, <seed>.done."""
import sys, os, json, gzip, collections
import numpy as np

SEEDS = range(111312000, 111313536)
SCREENS = {2: 'rewards', 3: 'boss_relic', 4: 'card_select'}


def lines(path):
    for p in (path, path + '.gz'):
        if os.path.exists(p):
            with (gzip.open(p, 'rt') if p.endswith('.gz') else open(p)) as f:
                return [json.loads(x) for x in f if x.strip()]
    return None


def outcome(rows):
    o = [r for r in rows or [] if r.get('type') == 'outcome']
    return o[-1] if o else None


def boot(seeds, d, n=10000, rng=np.random.default_rng(20261031)):
    d = np.asarray(d, float); idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1); return [float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))]


def main(units, out):
    rec, missing = [], []
    changed = collections.Counter(); total = collections.Counter()
    for s in SEEDS:
        u = os.path.join(units, str(s))
        done = open(os.path.join(u, f'{s}.done')).read() if os.path.exists(os.path.join(u, f'{s}.done')) else ''
        a, b = outcome(lines(os.path.join(u, f'A-{s}.jsonl'))), outcome(lines(os.path.join(u, f'B-{s}.jsonl')))
        if ' rc=0 ' not in done + ' ' or not a or not b or not a.get('complete') or not b.get('complete'):
            missing.append(s); continue
        walls = {}
        for line in open(os.path.join(u, 'games.txt')):
            t = dict(x.split('=', 1) for x in line.split()[1:] if '=' in x)
            walls[line.split()[0][0]] = int(t.get('wall', 0))
        ch = lines(os.path.join(u, f'B-{s}.chooser.jsonl')) or []
        for c in ch:
            k = (c['act'], SCREENS.get(c['screen'], str(c['screen'])))
            total[k] += 1; changed[k] += int(c['chosen'] != 0)
        first = next((c for c in ch if c['chosen'] != 0), None)   # first B choice off the prior's top (A's pick there)
        rec.append(dict(seed=s, a=a, b=b, wallA=walls.get('A', 0), wallB=walls.get('B', 0) - walls.get('A', 0),
                        first=None if first is None else f"act{first['act']}_{SCREENS.get(first['screen'], first['screen'])}"))
    seeds = [r['seed'] for r in rec]
    res = {'units': len(rec), 'missing': missing}
    def metric(name, f):
        A = np.array([f(r['a']) for r in rec], float); B = np.array([f(r['b']) for r in rec], float)
        res[name] = {'A': float(A.mean()), 'B': float(B.mean()), 'diff': float((B - A).mean()), 'ci': boot(seeds, B - A)}
    metric('heart_kill', lambda o: float(o['heartKilled']))
    metric('act4_reached', lambda o: float(o['finalAct'] >= 4))
    metric('final_floor', lambda o: float(o['finalFloor']))
    metric('heart_reached', lambda o: float(o['finalAct'] >= 4 and (o['heartKilled'] or o['finalFloor'] >= 56)))   # S&S floor 55, Heart 56
    metric('death_act4', lambda o: float(o['finalAct'] >= 4 and not o['heartKilled']))
    for k in (1, 2, 3):
        metric(f'death_act{k}', lambda o, k=k: float(o['finalAct'] == k and not o['heartKilled'] and o['finalHp'] <= 0))
    d = res['heart_kill']
    res['decision'] = 'PASS' if d['ci'][0] > 0 else 'FAIL' if d['ci'][1] < 0 else 'NOT_SHOWN'
    res['chooser'] = {f'act{k[0]}_{k[1]}': {'decisions': total[k], 'not_prior_top': changed[k]} for k in sorted(total)}
    fd = collections.defaultdict(list)
    for r in rec: fd[r['first'] or 'none'].append(float(r['b']['heartKilled']) - float(r['a']['heartKilled']))
    res['first_divergence'] = {k: {'units': len(v), 'heart_kill_diff': float(np.mean(v))} for k, v in sorted(fd.items())}
    wa = np.array([r['wallA'] for r in rec], float); wb = np.array([r['wallB'] for r in rec], float)
    res['wall_ratio_B_over_A'] = float(wb.sum() / max(wa.sum(), 1))   # CPU proxy: one game per lane, single-threaded
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('units', 'heart_kill', 'decision', 'wall_ratio_B_over_A')}, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
