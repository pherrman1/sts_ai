import json, math, sys, collections
meta = json.load(open('meta.json'))
for n in sys.argv[1:]:
    vals = [1/(1+math.exp(-json.loads(l)['value'])) for l in open(f'{n}.scores.jsonl')]
    st = collections.defaultdict(dict)
    for m, v in zip(meta, vals): st[(m['seed'], m['floor'])][m['pert']] = v
    S = list(st.values())
    pos = [s for s in S if 'hp-12' in s and s['base'] > s['hp-12']]
    mhp = [s['mhp+5'] > s['base'] for s in pos if 'mhp+5' in s]
    g = [s['gold+50'] > s['base'] for s in pos if 'gold+50' in s]
    hp3 = [s['hp-3'] < s['base'] for s in S if 'hp-3' in s]
    print(f"{n:8s} maxHP+5>0 {100*sum(mhp)/len(mhp):5.1f}%  -3HP sign {100*sum(hp3)/len(hp3):5.1f}%  gold+50>0 {100*sum(g)/len(g):5.1f}%  (pos-slope states {len(pos)})")
