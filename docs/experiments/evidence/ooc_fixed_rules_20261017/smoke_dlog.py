import json, sys, glob, collections as C
d = sys.argv[1]
for arm in sys.argv[2:]:
    st = C.Counter(); sel = C.Counter()
    for f in glob.glob(f'{d}/{arm}-*.dlog.jsonl'):
        for l in open(f):
            j = json.loads(l)
            if not j['screen'].startswith('REWARDS') or j['singletonBypass']: continue
            cs = j['rootCandidates']; labels = [c['label'] for c in cs]
            disc = any('iscard' in x.lower() and 'potion' in x.lower() for x in labels)
            relic = any(x.lower().startswith('take relic') for x in labels)
            pr = [c['prior'] for c in cs]; uni = max(pr) - min(pr) < 1e-9
            kind = 'discard' if disc else 'relic' if relic else 'cards-only'
            st[(kind, 'uniform' if uni else 'prior')] += 1
            if disc:
                s = j['selected'].lower()
                sel['discard' if 'discard' in s else 'card' if s.startswith('take card') else s[:20]] += 1
    print(arm, sorted(st.items()), 'discard-screen picks', sel.most_common())
