import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:])
AOE={'CLEAVE','WHIRLWIND','THUNDERCLAP','IMMOLATE','REAPER'}
stat=collections.defaultdict(lambda:[0,0])
for g in G:
    boss={}
    for f in g['fights']:
        if f['room']=='BOSS' and f['act']<=3: boss.setdefault(f['act'], ENC[f['enc']])
    st=g['states']; seen=set()
    for k,s in enumerate(st):
        if s['screen']!=2 or not s['cards_offered'] or (s['floor'],tuple(s['cards_offered'])) in seen: continue
        seen.add((s['floor'],tuple(s['cards_offered'])))
        nx=next((t for t in st[k+1:] if t['floor']>s['floor'] or t['screen']==5), None)
        if nx is None or s['act'] not in boss: continue
        added=collections.Counter(nx['deck'])-collections.Counter(s['deck'])
        offered=s['cards_offered']; b=boss[s['act']]
        for kind,test in (('power',lambda c: CTYPE[c]=='POWER'),('aoe',lambda c: CARD[c] in AOE)):
            if any(test(c) for c in offered):
                stat[(s['act'],b,kind)][0]+=1
                stat[(s['act'],b,kind)][1]+= any(test(c) for c in added)
for k in sorted(stat):
    n,p=stat[k]
    if n>=50: print(f'act{k[0]} boss={k[1]:14s} {k[2]:5s} offered in {n:5d} rewards, picked {p/n*100:5.1f}%')
