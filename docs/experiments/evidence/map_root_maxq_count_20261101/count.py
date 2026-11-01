#!/usr/bin/env python3
"""Map roots: how often would a max-Q root rule pick differently from most-visited? Offline, no seeds.

usage: count.py ARM UNITS_DIR OUT_JSON   (parsing as map_root_voc_audit_20261101/analyze.py)
Rules on the final tree (4,096) and on the 1,024 checkpoint (= a 1,024-sim search, §737):
  visits   : production visits_q_id;
  maxq_kK  : argmax q among children with >= K visits (K = 64, 256, 1024), else visits;
  lcb      : argmax q - 1.96 * 0.13 / sqrt(visits) (0.13 = one rollout3 leaf SD, rollout-cost 10-31; ignores tree
             correlation), children with >= 1 visit.
Per rule: departure rate (rule != visits), per game, by prior-top bin, mean q gap (rule child - visits child).
Persistence: for departures at the 1,024 checkpoint, is the rule's child still ahead in q at 4,096 (after PUCT
gave both more visits)? A rule chasing noise loses most of its lead (regression to the mean).
"""
import collections, gzip, json, math, os, sys, tarfile
ARM, UNITS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BINS = [0.0, 0.5, 0.8, 0.9, 0.98, 1.0000001]

def vpick(acts):
    acts = [a for a in acts if not a.get('pruned')] or acts
    return sorted(acts, key=lambda a: (-a['visits'], -a['q'], a['id']))[0]['id']

def rule(acts, name):
    acts = [a for a in acts if not a.get('pruned')] or acts
    if name == 'visits': return vpick(acts)
    if name.startswith('maxq_k'):
        k = int(name[6:]); el = [a for a in acts if a['visits'] >= k]
        return max(el, key=lambda a: (a['q'], a['visits'])) ['id'] if len(el) >= 2 else vpick(acts)
    if name == 'lcb':
        el = [a for a in acts if a['visits'] >= 1]
        return max(el, key=lambda a: a['q'] - 1.96 * 0.13 / math.sqrt(a['visits']))['id']
RULES = ['maxq_k64', 'maxq_k256', 'maxq_k1024', 'lcb']
stat = {(t, r): collections.Counter() for t in ('4096', '1024') for r in RULES}
gaps = {(t, r): [] for t in ('4096', '1024') for r in RULES}
persist = {r: [] for r in RULES}
bins = {(t, r): collections.Counter() for t in ('4096', '1024') for r in RULES}
binn = collections.Counter(); games = 0; roots = 0
for name in sorted(os.listdir(UNITS)):
    if not name.endswith('.tar'): continue
    seed = name.split('.')[0]
    with tarfile.open(os.path.join(UNITS, name)) as tf:
        try: m = tf.getmember(f'out/units/{seed}/{ARM}-{seed}.jsonl.gz')
        except KeyError: continue
        rows = [json.loads(l) for l in gzip.decompress(tf.extractfile(m).read()).decode().splitlines() if l.strip()]
    out = [r for r in rows if r.get('type') == 'outcome']
    if not out or not out[0].get('complete'): continue
    games += 1
    for r in rows:
        if r.get('type') != 'decision' or not r.get('searched') or r.get('screen') != 5: continue
        ro = r['root']
        if ro.get('singleton') or not ro.get('attempts') or ro.get('aborted'): continue
        roots += 1
        top = max(c['prior'] for c in ro['candidates'])
        b = next(i for i in range(len(BINS) - 1) if BINS[i] <= top < BINS[i + 1]); binn[b] += 1
        cps = {c['simulations']: c['actions'] for c in ro.get('checkpoints', [])}
        trees = {'4096': ro['candidates'], '1024': cps.get(1024)}
        assert vpick(ro['candidates']) == ro['selectedId'] or ro['completedSimulations'] != 4096
        for t, acts in trees.items():
            if not acts: continue
            byid = {a['id']: a for a in acts}; v = vpick(acts)
            for rn in RULES:
                x = rule(acts, rn); stat[(t, rn)]['roots'] += 1
                if x != v:
                    stat[(t, rn)]['depart'] += 1; bins[(t, rn)][b] += 1
                    gaps[(t, rn)].append(byid[x]['q'] - byid[v]['q'])
                    if t == '1024':
                        f = {a['id']: a for a in ro['candidates']}
                        persist[rn].append((byid[x]['q'] - byid[v]['q'], f[x]['q'] - f[v]['q'], f[x]['visits'], f[v]['visits']))
res = {'arm': ARM, 'games': games, 'roots': roots, 'roots_per_bin': {f'{BINS[i]}-{min(BINS[i+1],1)}': binn[i] for i in range(len(BINS) - 1)}}
for (t, rn), c in stat.items():
    g = gaps[(t, rn)]
    d = dict(depart_rate=c['depart'] / max(1, c['roots']), depart_per_game=c['depart'] / games, departs=c['depart'],
             mean_qgap=sum(g) / len(g) if g else None,
             by_bin={f'{BINS[i]}-{min(BINS[i+1],1)}': bins[(t, rn)][i] / max(1, binn[i]) for i in range(len(BINS) - 1)})
    if t == '1024' and persist[rn]:
        p = persist[rn]
        d['persist'] = dict(n=len(p), lead_at_1024=sum(a for a, _, _, _ in p) / len(p), lead_at_4096=sum(b for _, b, _, _ in p) / len(p),
                            still_ahead_at_4096=sum(1 for _, b, _, _ in p if b > 0) / len(p),
                            rule_child_visits_4096=sum(c for *_, c, _ in p) / len(p), visits_child_visits_4096=sum(v for *_, v in p) / len(p))
    res[f'{t}:{rn}'] = d
json.dump(res, open(OUT, 'w'), indent=1); print(json.dumps(res, indent=1))
