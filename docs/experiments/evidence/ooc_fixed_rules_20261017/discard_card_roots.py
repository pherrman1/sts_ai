import json, sys, glob, collections as C
root = sys.argv[1]
sel = C.Counter(); why = C.Counter(); ex=[]
for f in glob.glob(root + '/*/seed-*.roots.jsonl'):
    for l in open(f):
        j = json.loads(l)
        acts = j['rootActions']
        if j['screen'] != 2 or j.get('singletonBypass') or not acts: continue
        hasDisc = any('effect=29' in a['key'] for a in acts); hasCard = any('effect=5:' in a['key'] for a in acts)
        pri = [a['prior'] for a in acts]; uniform = max(pri) - min(pri) < 1e-9
        k = j['selectedKey']
        kind = 'discard' if 'effect=29' in k else 'card' if 'effect=5:' in k else 'skipcard' if 'effect=12' in k else 'leave' if 'effect=14' in k else k.split(':')[2]
        if hasDisc and hasCard: sel[kind] += 1
        if uniform and hasCard and not hasDisc:
            effs = tuple(sorted(set(a['key'].split(':')[2] for a in acts)))
            why[effs] += 1
print('discard+card screens selected:', sel.most_common())
print('uniform card screens w/o discard, effect sets:', why.most_common(8))
