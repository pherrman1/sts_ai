#!/usr/bin/env python3
"""Descriptive extras for RESULT.md (not pre-registered): fight win rate per arm by room, act and the Heart (over
replicates of the fights analyze.py counts), decisions per fight, and the stall-flagged fights.

usage: python3 describe.py DIR   (DIR: extracted unit tars)
"""
import csv, glob, os, sys, collections
d = sys.argv[1]
st, arms, valid = {}, collections.defaultdict(lambda: collections.defaultdict(list)), collections.defaultdict(lambda: True)
for p in glob.glob(os.path.join(d, '**', '*.states.csv'), recursive=True):
    pre = p[:-len('.states.csv')]
    for r in csv.DictReader(open(p)): st[r['stateId']] = r
    t = open(pre + '.arms.csv').read(); t = t[:t.rfind('\n') + 1]
    for r in csv.DictReader(t.splitlines()):
        valid[r['stateId']] = valid[r['stateId']] and r['valid'] == '1'
        arms[r['stateId']][r['arm']].append(r)
ARMS = ['base10000', 'base12000', 'base15000', 'head10000']
win = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
dec = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
stalls = []
def groups(s):
    g = ['all', s['roomClass'].lower() if s['roomClass'] in ('BOSS', 'ELITE') else 'normal', 'act' + s['act']]
    enc = s.get('encounter') or ''
    if 'Heart' in enc: g.append('heart')
    return g
for sid, a in arms.items():
    if not valid[sid] or sid not in st or any(len(a[x]) != 2 for x in ARMS): continue
    s = st[sid]
    for arm in ARMS:
        for g in groups(s):
            win[g][arm][0] += sum(int(r['won']) for r in a[arm]); win[g][arm][1] += 2
            dec[g][arm][0] += sum(int(r['decisions']) for r in a[arm]); dec[g][arm][1] += 1
    dh, db = sum(int(r['decisions']) for r in a['head10000']), sum(int(r['decisions']) for r in a['base10000'])
    if dh > 2 * db:
        hp = lambda arm: '/'.join(r['terminalHp'] if r['won'] == '1' else 'X' for r in a[arm])
        stalls.append((sid, s['act'], s['roomClass'], s.get('encounter'), db, dh, hp('base10000'), hp('head10000')))
print('win rate per arm (replicates)')
for g in ['all', 'normal', 'elite', 'boss', 'act1', 'act2', 'act3', 'act4', 'heart']:
    if g in win: print(f"  {g:7} " + '  '.join(f"{arm} {100*win[g][arm][0]/win[g][arm][1]:5.1f}%" for arm in ARMS) + f"  (n={win[g]['base10000'][1]//2} fights)")
print('decisions per fight (both redraws)')
for g in ['all', 'normal', 'elite', 'boss', 'act3', 'act4']:
    if g in dec: print(f"  {g:7} " + '  '.join(f"{arm} {dec[g][arm][0]/dec[g][arm][1]:6.1f}" for arm in ARMS))
print('stall-flagged fights (head10000 > 2x base10000 decisions): state act room encounter dec_base dec_head hp_base hp_head')
for x in sorted(stalls): print('  ', *x)
