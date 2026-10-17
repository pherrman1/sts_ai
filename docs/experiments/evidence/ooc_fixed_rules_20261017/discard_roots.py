import json, sys, glob, collections as C
root = sys.argv[1]
n = C.Counter(); sel = C.Counter(); runs=set()
for f in glob.glob(root + '/*/seed-*.roots.jsonl'):
    for l in open(f):
        j = json.loads(l)
        if j['screen'] != 2 or j.get('singletonBypass'): continue
        acts = j["rootActions"]
        if not acts: continue
        hasDisc = any('effect=29' in a['key'] for a in acts)
        hasCard = any('effect=5:' in a['key'] for a in acts)
        pri = [a['prior'] for a in acts]
        uniform = max(pri) - min(pri) < 1e-9
        n[(hasDisc, hasCard, uniform)] += 1
        if hasDisc and uniform:
            k = j['selectedKey']
            kind = 'discard' if 'effect=29' in k else 'card' if 'effect=5:' in k else 'skipcard' if 'effect=12' in k else 'leave' if 'effect=14' in k else k[:40]
            sel[kind] += 1; runs.add(j['seed'])
print('(hasDiscard, hasCard, uniformPrior) -> roots', sorted(n.items()))
print('uniform discard screens: selected', sel.most_common(), 'runs', len(runs))
