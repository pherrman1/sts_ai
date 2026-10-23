"""Three arms on the same real fights: the deployed CTM, the CTM + calibration table, and a fine-tuned CTM.
python3 -I compare3.py TOOL.py TABLE.json SEEDS OUT.json OFF.csv,ZERO.csv,FT.csv [...]
TOOL.py is tools/ctm_calibration.py (PR #838); TABLE the calibration table fitted on the OTHER seeds (or on all A/B
rows for the held-out set); SEEDS even|odd|all; FT.csv `one_combat ctmscorerows` of the same rows with the fine-tuned
artifact (calibration unset). Prints a markdown table by act x room and per elite/boss, and writes OUT.json."""
import csv
import importlib.util
import json
import math
import random
import sys
from collections import defaultdict

spec = importlib.util.spec_from_file_location('ctm_calibration', sys.argv[1])
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
TABLE, SEEDS, OUT, SPECS = json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4], sys.argv[5:]
ARMS = ('ctm', 'table', 'ft')


def rows():
    out = []
    for s in SPECS:
        off, zero, ft = s.split(',')
        loaded = cal.load(off + ',' + zero, SEEDS)
        index = {(r['seed'], r['fight']): r for r in loaded}
        with open(ft, newline='') as stream:
            for f in csv.DictReader(stream):
                key = (int(f['source_seed']), int(f['fight_idx']))
                if key not in index:
                    continue
                assert f['scored'] == '1', ('fine-tuned arm refused a row the CTM scored', key)
                r = index.pop(key)
                r['ftp'], r['fthp'] = float(f['p_death']), float(f['expected_win_hp'])
                out.append(r)
        assert not index, 'rows missing from the fine-tuned scores'
    return out


def per_row(r):
    e = cal.lookup(TABLE, r)
    ps = {'ctm': r['p'], 'table': cal.shifted(r['p'], e['deathLogitShift']), 'ft': r['ftp']}
    hp = {'ctm': r['base'], 'table': cal.predicted_hp(r, e['hpLossScale']), 'ft': r['fthp']}
    m = {}
    for a in ARMS:
        p = min(max(ps[a], 1e-12), 1 - 1e-12)
        m[a] = {'p': ps[a], 'll': -math.log(p if r['death'] else 1 - p)}
        if not r['death']:
            m[a]['err'] = hp[a] - r['post']
    return m


def summarize(rs, ms):
    n = len(rs)
    won = [i for i, r in enumerate(rs) if not r['death']]
    line = {'rows': n, 'observedDeath': sum(r['death'] for r in rs) / n}
    for a in ARMS:
        line[a] = {'predictedDeath': sum(m[a]['p'] for m in ms) / n, 'logLoss': sum(m[a]['ll'] for m in ms) / n}
        if won:
            line[a]['winHpMae'] = sum(abs(ms[i][a]['err']) for i in won) / len(won)
            line[a]['winHpBias'] = sum(ms[i][a]['err'] for i in won) / len(won)
    return line


def bootstrap(rs, ms, a, b, reps=1000):
    per = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r, m in zip(rs, ms):
        s = per[r['seed']]
        s[0] += m[b]['ll'] - m[a]['ll']
        s[1] += 1
        if 'err' in m[a]:
            s[2] += abs(m[b]['err']) - abs(m[a]['err'])
            s[3] += 1
    seeds = sorted(per)
    rng = random.Random(20261023)
    draws = []
    for _ in range(reps):
        pick = [per[rng.choice(seeds)] for _ in seeds]
        draws.append((sum(x[0] for x in pick) / sum(x[1] for x in pick),
                      sum(x[2] for x in pick) / max(sum(x[3] for x in pick), 1)))
    point = (sum(x[0] for x in per.values()) / sum(x[1] for x in per.values()),
             sum(x[2] for x in per.values()) / max(sum(x[3] for x in per.values()), 1))
    out = {}
    for i, name in enumerate(('logLoss', 'winHpMae')):
        v = sorted(d[i] for d in draws)
        out[name] = [point[i], v[int(0.025 * reps)], v[int(0.975 * reps) - 1]]
    return out


def main():
    rs = rows()
    ms = [per_row(r) for r in rs]
    groups = defaultdict(list)
    for i, r in enumerate(rs):
        for k in ('all', r['coarse'], r['fine']):
            if k:
                groups[k].append(i)
    result = {k: summarize([rs[i] for i in idx], [ms[i] for i in idx]) for k, idx in groups.items()}
    result['all']['bootstrap95'] = {'ft-ctm': bootstrap(rs, ms, 'ctm', 'ft'), 'ft-table': bootstrap(rs, ms, 'table', 'ft'),
                                    'table-ctm': bootstrap(rs, ms, 'ctm', 'table')}
    json.dump(result, open(OUT, 'w'), indent=2, sort_keys=True)
    order = ['all'] + sorted(k for k in result if k != 'all' and k.split(':')[1] in cal.ROOMS) + \
        sorted(k for k in result if k != 'all' and k.split(':')[1] not in cal.ROOMS)
    print('| fights | rows | deaths obs | pred CTM / table / FT | log loss CTM / table / FT | won HP MAE CTM / table / FT | HP bias CTM / table / FT |')
    print('|---|---|---|---|---|---|---|')
    for k in order:
        x = result[k]
        if x['rows'] < 100:
            continue
        f = lambda key, fmt: ' / '.join(fmt.format(x[a][key]) for a in ARMS) if key in x['ctm'] else '-'
        print(f"| {k} | {x['rows']:,} | {x['observedDeath']:.3f} | {f('predictedDeath', '{:.3f}')} | "
              f"{f('logLoss', '{:.4f}')} | {f('winHpMae', '{:.2f}')} | {f('winHpBias', '{:+.1f}')} |")
    print()
    for name, v in result['all']['bootstrap95'].items():
        print(f"{name}: log loss {v['logLoss'][0]:+.4f} [{v['logLoss'][1]:+.4f}, {v['logLoss'][2]:+.4f}], "
              f"won HP MAE {v['winHpMae'][0]:+.2f} [{v['winHpMae'][1]:+.2f}, {v['winHpMae'][2]:+.2f}]")


main()
