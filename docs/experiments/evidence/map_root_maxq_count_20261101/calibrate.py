#!/usr/bin/env python3
"""Calibrate the LCB noise scale at map roots from logged checkpoints (offline, no seeds).

usage: calibrate.py ARM UNITS_DIR OUT_JSON
(1) sigma: for every child with n_k visits at checkpoint k < 4096 and N > n_k at 4096, iid visits would give
    E[(Q_k - Q_N)^2] = sigma^2 (1/n_k - 1/N). sigma^2 is fitted per visit bin and act (through 0); drift of the tree
    (later visits go deeper) inflates it, so it is conservative.
(2) multiplier c of LCB = Q - c * sigma / sqrt(n): for each c, departure rate at the 1,024 checkpoint and the share
    of those departures whose child is still ahead in Q at 4,096 (self-consistency; Q is search's own estimate).
"""
import collections, gzip, json, math, os, sys, tarfile
ARM, UNITS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
VB = [1, 4, 16, 64, 256, 1024, 4096]
num = collections.defaultdict(float); den = collections.defaultdict(float); cnt = collections.Counter()
roots1024 = []
def vpick(acts):
    acts = [a for a in acts if not a.get('pruned')] or acts
    return sorted(acts, key=lambda a: (-a['visits'], -a['q'], a['id']))[0]['id']
for name in sorted(os.listdir(UNITS)):
    if not name.endswith('.tar'): continue
    seed = name.split('.')[0]
    with tarfile.open(os.path.join(UNITS, name)) as tf:
        try: m = tf.getmember(f'out/units/{seed}/{ARM}-{seed}.jsonl.gz')
        except KeyError: continue
        rows = [json.loads(l) for l in gzip.decompress(tf.extractfile(m).read()).decode().splitlines() if l.strip()]
    out = [r for r in rows if r.get('type') == 'outcome']
    if not out or not out[0].get('complete'): continue
    for r in rows:
        if r.get('type') != 'decision' or not r.get('searched') or r.get('screen') != 5: continue
        ro = r['root']
        if ro.get('singleton') or not ro.get('attempts') or ro.get('aborted') or ro['completedSimulations'] != 4096: continue
        fin = {a['id']: a for a in ro['candidates']}; act = min(r['act'], 3)
        for cp in ro.get('checkpoints', []):
            if cp['simulations'] >= 4096: continue
            for a in cp['actions']:
                n, N = a['visits'], fin[a['id']]['visits']
                if n < 1 or N <= n: continue
                x = 1 / n - 1 / N; b = max(i for i in range(len(VB)) if VB[i] <= n)
                num[(act, b)] += (a['q'] - fin[a['id']]['q']) ** 2 * x; den[(act, b)] += x * x; cnt[(act, b)] += 1
                num[('all', b)] += (a['q'] - fin[a['id']]['q']) ** 2 * x; den[('all', b)] += x * x; cnt[('all', b)] += 1
        c1024 = next((c['actions'] for c in ro.get('checkpoints', []) if c['simulations'] == 1024), None)
        if c1024: roots1024.append((act, c1024, fin))
sig = {f'{k[0]}:{VB[k[1]]}+': dict(sigma=math.sqrt(num[k] / den[k]), n=cnt[k]) for k in sorted(num, key=str)}
# act-level sigma from children with >= 16 visits (where LCB decisions happen)
sa = {}
for act in (1, 2, 3, 'all'):
    nu = sum(num[(act, b)] for b in range(3, len(VB))); de = sum(den[(act, b)] for b in range(3, len(VB)))
    sa[str(act)] = math.sqrt(nu / de) if de else None
res = {'arm': ARM, 'sigma_by_act_bin': sig, 'sigma_act_ge16': sa, 'c_scan': {}}
for c in (0.0, 1.0, 1.645, 1.96, 2.576, 3.29):
    dep = keep = 0; lead = []
    for act, acts, fin in roots1024:
        s = sa[str(act)]; acts = [a for a in acts if not a.get('pruned')] or acts
        v = vpick(acts); el = [a for a in acts if a['visits'] >= 1]
        x = max(el, key=lambda a: a['q'] - c * s / math.sqrt(a['visits']))['id']
        if x != v:
            dep += 1; d = fin[x]['q'] - fin[v]['q']; keep += d > 0; lead.append(d)
    res['c_scan'][str(c)] = dict(depart_rate=dep / len(roots1024), persist=keep / max(1, dep), mean_lead_4096=sum(lead) / max(1, len(lead)))
json.dump(res, open(OUT, 'w'), indent=1); print(json.dumps(res, indent=1))
