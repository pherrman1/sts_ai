# Per arm: REWARDS search roots (singleton bypass excluded) that offer a "Discard potion"
# candidate, split by whether a card reward is still on the screen, with the pick.
import json, sys, glob, collections as C
d = sys.argv[1]
for arm in sys.argv[2:]:
    n = C.Counter()
    for f in sorted(glob.glob(f'{d}/{arm}-*.dlog.jsonl')):
        for l in open(f):
            j = json.loads(l)
            if not j['screen'].startswith('REWARDS') or j['singletonBypass']: continue
            labs = [c['label'] for c in j['rootCandidates']]
            if not any(x.startswith('Discard potion') for x in labs): continue
            pr = [c['prior'] for c in j['rootCandidates']]
            cards = 'with_cards' if any(x.startswith('Take card') for x in labs) else 'no_cards'
            prior = 'uniform' if max(pr) - min(pr) < 1e-9 else 'prior'
            pick = 'discard' if j['selected'].startswith('Discard potion') else 'other'
            n[(cards, prior, pick)] += 1
    print(arm, sorted(n.items()))
