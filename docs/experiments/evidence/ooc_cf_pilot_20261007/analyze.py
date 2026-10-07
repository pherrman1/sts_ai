#!/usr/bin/env python3
"""Counterfactual OOC pilot analysis (PLAN.md). usage: analyze.py OUT_DIR"""
import csv, glob, itertools, json, math, os, statistics as st, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
csv.field_size_limit(10**9)
out = sys.argv[1]
repo = os.popen('git rev-parse --show-toplevel').read().strip()

labels = [r for f in sorted(glob.glob(out + '/part*.labels.csv')) for r in csv.DictReader(open(f))]
options = [r for f in sorted(glob.glob(out + '/part*.options.csv')) for r in csv.DictReader(open(f))]
sources = [r for f in sorted(glob.glob(out + '/part*.sources.csv')) for r in csv.DictReader(open(f))]
print(f'sources {len(sources)}, label rows {len(labels)}, valid {sum(r["valid"]=="1" for r in labels)}')
bad = [r for r in labels if r['valid'] != '1']
for r in bad[:10]: print('  invalid', r['sourceSeed'], r['optionIdx'], r['k'], r['error'][:100])

states = defaultdict(lambda: defaultdict(dict))  # (seed,dec) -> opt -> k -> row
meta = {}
for r in labels:
    key = (r['sourceSeed'], r['decisionIdx'])
    meta[key] = (r['type'], int(r['act']), int(r['floor']))
    states[key][int(r['optionIdx'])][int(r['k'])] = r

def score(r): return float(r['hp']) if r['bossWon'] == '1' else 0.0

def pair_stats(a, b, ks):
    d = [score(a[k]) - score(b[k]) for k in ks]
    m = st.mean(d)
    se = st.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float('inf')
    sa = [score(a[k]) for k in ks]; sb = [score(b[k]) for k in ks]
    use = math.sqrt((st.variance(sa) + st.variance(sb)) / len(ks)) if len(ks) > 1 else float('inf')
    return m, se, use

# X2-B on after-option features
from_x2b = None
try:
    sys.path.insert(0, os.path.join(repo, 'docs/experiments/evidence/ooc_cf_pilot_20261007'))
    from x2b import Tree
    T = Tree(os.path.join(repo, 'models/candidates/v_win_x2b_trees.txt'))
    from_x2b = {}
    for r in options:
        x = [float(r[n]) for n in T.names]
        from_x2b[(r['sourceSeed'], r['decisionIdx'], int(r['optionIdx']))] = T.predict(x)
except Exception as e:
    print('X2-B scoring skipped:', e)

report = {'byK': {}, 'cost': {}, 'states': []}
for K in (4, 8):
    res = tot = 0; ses = []; uses = []; gaps = []; agree = disagree = 0; byType = defaultdict(lambda: [0, 0])
    for key, opts in states.items():
        ks = list(range(K))
        valid = {o: rows for o, rows in opts.items() if all(k in rows and rows[k]['valid'] == '1' for k in ks)}
        for a, b in itertools.combinations(sorted(valid), 2):
            m, se, use = pair_stats(valid[a], valid[b], ks)
            tot += 1; byType[meta[key][0]][1] += 1
            ses.append(se); uses.append(use); gaps.append(abs(m))
            if abs(m) > 2 * se and se > 0 or (se == 0 and m != 0):
                res += 1; byType[meta[key][0]][0] += 1
                if from_x2b:
                    xa = from_x2b.get((key[0], key[1], a)); xb = from_x2b.get((key[0], key[1], b))
                    if xa is not None and xb is not None and xa != xb:
                        if (xa > xb) == (m > 0): agree += 1
                        else: disagree += 1
    fin = lambda xs: [x for x in xs if math.isfinite(x)]
    report['byK'][K] = {'pairs': tot, 'resolved': res,
                        'medianAbsGapHp': st.median(gaps) if gaps else None,
                        'medianPairedSeHp': st.median(fin(ses)) if fin(ses) else None,
                        'medianUnpairedSeHp': st.median(fin(uses)) if fin(uses) else None,
                        'byType': {t: {'resolved': v[0], 'pairs': v[1]} for t, v in byType.items()},
                        'x2bOnResolved': {'agree': agree, 'disagree': disagree}}
    print(f'K={K}: resolved {res}/{tot} pairs; median |gap| {report["byK"][K]["medianAbsGapHp"]}, '
          f'paired SE {report["byK"][K]["medianPairedSeHp"]}, unpaired SE {report["byK"][K]["medianUnpairedSeHp"]}; '
          f'X2-B agrees {agree}/{agree+disagree} resolved pairs; by type {dict(report["byK"][K]["byType"])}')

cpu = defaultdict(list); perState = defaultdict(float)
for r in labels:
    cpu[r['type']].append(float(r['cpuSeconds'])); perState[(r['sourceSeed'], r['decisionIdx'])] += float(r['cpuSeconds'])
for t, v in cpu.items():
    report['cost'][t] = {'runs': len(v), 'meanCpuSecondsPerRun': st.mean(v)}
src = [float(r['sourceCpuSeconds']) for r in sources]
report['cost']['sourceMeanCpuSeconds'] = st.mean(src) if src else None
report['cost']['meanCpuSecondsPerState'] = st.mean(perState.values()) if perState else None
print('cost', json.dumps(report['cost']))

for key, opts in sorted(states.items()):
    t, act, floor = meta[key]
    row = {'seed': key[0], 'decisionIdx': key[1], 'type': t, 'act': act, 'floor': floor, 'options': []}
    for o, rows in sorted(opts.items()):
        v = [rows[k] for k in sorted(rows) if rows[k]['valid'] == '1']
        r0 = next(iter(rows.values()))
        row['options'].append({'optionIdx': o, 'key': r0['optionKey'], 'chosen': r0['chosen'] == '1', 'n': len(v),
            'bossWinRate': st.mean(int(x['bossWon']) for x in v) if v else None,
            'meanScoreHp': st.mean(score(x) for x in v) if v else None,
            'x2b': from_x2b.get((key[0], key[1], o)) if from_x2b else None})
    report['states'].append(row)
json.dump(report, open(os.path.join(out, 'report.json'), 'w'), indent=1)
print('wrote', os.path.join(out, 'report.json'))
