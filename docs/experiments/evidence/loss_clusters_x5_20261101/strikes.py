"""Cross-cutting deck signature: starter cards (Strike/Defend) left in the deck at each boss entry.
usage: strikes.py WORKDIR. Per boss stage: entries and per-fight death by number of Strikes (base or upgraded),
within entry-HP bands; plus Heart kill by Strikes at the act-3 boss entry."""
import sys, collections
import numpy as np
from common import *
G, _ = primary(load(sys.argv[1])); N = len(G)
S = {k for k, v in CARD.items() if v == 'STRIKE_RED'}; D = {k for k, v in CARD.items() if v == 'DEFEND_RED'}
dead = lambda f: f['res'] == 2 or f['post'] <= 0
t = collections.defaultdict(lambda: [0, 0])
for g in G:
    for f in g['fights']:
        if f['room'] != 'BOSS': continue
        a = 4 if f['act'] == 4 else f['act']; ns = sum(c in S for c, _ in f['deck'])
        sb = '0-1' if ns <= 1 else '2-3' if ns <= 3 else '4+'
        t[(a, sb, hpband(f))][0] += dead(f); t[(a, sb, hpband(f))][1] += 1
        t[(a, sb, 'all')][0] += dead(f); t[(a, sb, 'all')][1] += 1
print('boss fights: per-fight death % (entries) by Strikes in deck x entry HP band')
for a in (1, 2, 3, 4):
    for b in ('all', '<50%', '50-80%', '>=80%'):
        print(f'  act {a} {b:7s}', ' | '.join(f'{sb} Strikes: {t[(a,sb,b)][0]/max(1,t[(a,sb,b)][1])*100:5.1f}% ({t[(a,sb,b)][1]})' for sb in ('0-1', '2-3', '4+')))
