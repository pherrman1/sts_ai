"""Frozen #881 root cohort: every priced root of the 16 replays, plus a core set of up to 8 roots per type
(hash order, one root per seed first). usage: freeze_roots.py OUT.jsonl PRICE_FILES..."""
import hashlib, json, sys
import numpy as np
SC = {1: 'EVENT', 2: 'CARD_REWARD', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'TREASURE', 7: 'REST', 8: 'SHOP'}
roots = []
for path in sys.argv[2:]:
    for line in open(path):
        r = json.loads(line); p = r.get('price') or {}
        acts = sorted([a for a in p.get('actions', []) if a.get('leaf')], key=lambda a: -a['prior'])
        if len(acts) < 2: continue
        v = lambda a, k: [x['value'] for x in a[k]]
        roots.append({'seed': r['seed'], 'decisionIndex': r['decisionIndex'], 'screen': SC[r['screen']], 'screenId': r['screen'],
            'act': r['act'], 'floor': r['floor'], 'hp': r['hp'], 'maxHp': r['maxHp'], 'gold': r['gold'],
            'legalActions': p.get('legalActions'), 'n': p['n'],
            'actions': [{'id': a['id'], 'key': a['key'], 'label': a.get('label'), 'prior': a['prior'],
                         'leafMean': float(np.mean(v(a, 'leaf'))), 'actEndMean': float(np.mean(v(a, 'actEnd'))),
                         'leaf': v(a, 'leaf'), 'actEnd': v(a, 'actEnd'),
                         'leafEndFloor': [x['endFloor'] for x in a['leaf']], 'actEndEndFloor': [x['endFloor'] for x in a['actEnd']]}
                        for a in acts],
            'record': r.get('record')})
for t in sorted({x['screen'] for x in roots}):
    cand = sorted([x for x in roots if x['screen'] == t], key=lambda x: hashlib.sha1(f"{x['seed']}:{x['decisionIndex']}".encode()).hexdigest())
    core, seeds = [], set()
    for x in cand:
        if len(core) < 8 and x['seed'] not in seeds: core.append(x); seeds.add(x['seed'])
    for x in cand:
        if len(core) < 8 and x not in core: core.append(x)
    for x in core: x['core'] = True
    print(t, len(cand), 'core', len(core))
with open(sys.argv[1], 'w') as f:
    for x in sorted(roots, key=lambda x: (x['seed'], x['decisionIndex'])):
        x.setdefault('core', False); f.write(json.dumps(x) + '\n')
