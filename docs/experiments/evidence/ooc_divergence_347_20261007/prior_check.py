"""Root statistics of the M (OOC MCTS) decisions from STS_RUN_PROFILE rows.

Usage: python3 prior_check.py profile/*.profile.jsonl
Prints, per screen, how often the executed action is the max-prior and the
max-Q root action, then every TREASURE and REST root.
"""
import json, sys
from collections import Counter, defaultdict

SCREENS = {1: 'EVENT', 2: 'REWARDS', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP',
           6: 'TREASURE', 7: 'REST', 8: 'SHOP'}
tot = defaultdict(Counter)
detail = []
for path in sys.argv[1:]:
    for line in open(path):
        r = json.loads(line)
        if r.get('kind') != 'ooc_decision' or not r['executed'] or len(r['actions']) < 2:
            continue
        acts = r['actions']
        sel = max(acts, key=lambda a: (a['visits'], a['q']))
        best_q = max((a for a in acts if a['visits'] > 0), key=lambda a: a['q'])
        best_p = max(acts, key=lambda a: a['prior'])
        s = SCREENS.get(r['screen'], str(r['screen']))
        c = tot[s]
        c['roots'] += 1
        c['selected_is_max_prior'] += sel['id'] == best_p['id']
        c['selected_is_max_q'] += sel['id'] == best_q['id']
        if s in ('TREASURE', 'REST'):
            detail.append((r['seed'], r['floor'], s, r['selected_key'], sel['prior'], sel['visits'],
                           sel['q'], best_q['id'], best_q['prior'], best_q['visits'], best_q['q']))
for s, c in sorted(tot.items()):
    print(s, dict(c))
print('seed floor screen selected_key | sel prior visits q | maxQ id prior visits q')
for d in detail:
    print(d[0], d[1], d[2], d[3], '| %.3f %d %.4f | %d %.3f %d %.4f' % d[4:])
