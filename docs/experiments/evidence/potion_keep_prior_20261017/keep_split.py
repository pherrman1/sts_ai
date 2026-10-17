# Per arm: REWARDS search roots (singleton bypass excluded) with a "Discard potion" candidate:
# cards on screen?, prior uniform?, pick, and whether every discard prior is below "Leave rewards".
import json, sys, glob, collections as C
d = sys.argv[1]
for arm in sys.argv[2:]:
    n = C.Counter(); below = C.Counter(); runs = 0; wins = 0; act4 = 0
    for f in sorted(glob.glob(f'{d}/{arm}-*.dlog.jsonl')):
        for l in open(f):
            j = json.loads(l)
            if not j['screen'].startswith('REWARDS') or j['singletonBypass']: continue
            cs = j['rootCandidates']; labs = [c['label'] for c in cs]
            if not any(x.startswith('Discard potion') for x in labs): continue
            pr = [c['prior'] for c in cs]
            cards = 'with_cards' if any(x.startswith('Take card') for x in labs) else 'no_cards'
            prior = 'uniform' if max(pr) - min(pr) < 1e-9 else 'prior'
            pick = 'discard' if j['selected'].startswith('Discard potion') else 'other'
            n[(cards, prior, pick)] += 1
            lv = [c['prior'] for c in cs if c['label'].startswith('Leave rewards')]
            if lv: below[all(c['prior'] < lv[0] for c in cs if c['label'].startswith('Discard potion'))] += 1
    print(arm, 'roots', sorted(n.items()), 'discards_below_leave', dict(below))
